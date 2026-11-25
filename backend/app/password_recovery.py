"""Email-based password recovery for the three sign-in portals."""
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import jwt
from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select, update

from .development import DEVELOPMENT_ACCOUNTS, enabled, seeded_account
from .main import DATABASE_URL, SECRET_KEY, Db, User, app, audit, password_binding, password_hash

log = logging.getLogger(__name__)
PORTALS = {'farmer': ('farmer', 'legacy'), 'institution': ('institution', 'legacy'), 'admin': ('admin',)}
PURPOSE = 'password_recovery'
GENERIC_RESPONSE = {'message': 'If the email is eligible for recovery, you will receive a password reset link.'}


class RecoveryRequest(BaseModel):
    email: EmailStr
    portal: Literal['farmer', 'institution', 'admin']


class RecoveryReset(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    password: str = Field(min_length=8, max_length=128)


def recovery_mail_settings():
    key = os.getenv('AQUAFARM_RECOVERY_RESEND_API_KEY')
    sender = os.getenv('AQUAFARM_RECOVERY_FROM')
    try:
        origin = urlsplit(os.getenv('AQUAFARM_RECOVERY_ORIGIN', ''))
    except ValueError:
        return None
    if not key or not sender or origin.scheme != 'https' or not origin.hostname:
        return None
    if origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
        return None
    return key, sender, f'{origin.scheme}://{origin.netloc}'


def send_recovery_email(settings, email: str, token: str, portal: str) -> None:
    fragment = urlencode({'password-reset': token, 'portal': portal})
    send_account_email(settings, email, 'Reset your AquaFarm Manager Ghana password',
                       'Open this link to reset your password within 15 minutes:', fragment)


def send_account_email(settings, email: str, subject: str, instruction: str, fragment: str) -> bool:
    key, sender, origin = settings
    request = Request('https://api.resend.com/emails', method='POST', headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
        'User-Agent': 'AquaFarm-Password-Recovery/1.0',
    }, data=json.dumps({
        'from': sender, 'to': [email], 'subject': subject,
        'text': (
            f'{instruction}\n{origin}/#{fragment}\n\n'
            'If you did not request this, ignore this email.'
        ),
    }).encode())
    try:
        with urlopen(request, timeout=10):
            pass
    except (OSError, ValueError):
        log.warning('Account security email delivery failed')
        return False
    return True


@app.post('/auth/password-recovery/request', status_code=202)
def request_recovery(data: RecoveryRequest, db: Db, background: BackgroundTasks):
    settings = recovery_mail_settings()
    if settings is None:
        raise HTTPException(503, 'Password recovery email is unavailable. Contact support.')
    email = str(data.email).lower()
    user = db.scalar(select(User).where(
        User.email == email, User.account_type.in_(PORTALS[data.portal]), User.is_suspended.is_(False),
    ))
    if user is None or (
        email in DEVELOPMENT_ACCOUNTS.values() and seeded_account(db, user.id) and not enabled(DATABASE_URL)
    ):
        return GENERIC_RESPONSE
    now = datetime.now(timezone.utc).replace(microsecond=0)
    reserved = db.execute(update(User).where(
        User.id == user.id,
        User.is_suspended.is_(False),
        User.session_generation == user.session_generation,
        or_(User.recovery_requested_at.is_(None), User.recovery_requested_at <= now - timedelta(minutes=5)),
    ).values(recovery_requested_at=now).execution_options(synchronize_session=False))
    if reserved.rowcount == 1:
        token = jwt.encode({
            'sub': str(user.id), 'purpose': PURPOSE, 'binding': password_binding(user, PURPOSE),
            'iat': now, 'exp': now + timedelta(minutes=15),
        }, SECRET_KEY, algorithm='HS256')
        db.commit()
        background.add_task(send_recovery_email, settings, email, token, data.portal)
    return GENERIC_RESPONSE


@app.post('/auth/password-recovery/reset')
def reset_password(data: RecoveryReset, db: Db):
    invalid = HTTPException(400, 'This password reset link is invalid or expired.')
    try:
        payload = jwt.decode(data.token, SECRET_KEY, algorithms=['HS256'],
                             options={'require': ['iat', 'exp', 'sub', 'purpose', 'binding']})
        user_id = int(payload['sub'])
        if payload['purpose'] != PURPOSE or not isinstance(payload['binding'], str):
            raise invalid
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise invalid from None
    user = db.get(User, user_id)
    if user is None or user.is_suspended or user.recovery_requested_at is None or not hmac.compare_digest(
        payload['binding'], password_binding(user, PURPOSE),
    ):
        raise invalid
    requested_at = user.recovery_requested_at
    if int(requested_at.replace(tzinfo=timezone.utc).timestamp()) != payload['iat']:
        raise invalid
    if user.is_platform_admin and len(data.password) < 12:
        raise HTTPException(422, 'Use at least 12 characters for an administrator password.')
    changed = db.execute(update(User).where(
        User.id == user_id, User.password_hash == user.password_hash,
        User.is_suspended.is_(False), User.session_generation == user.session_generation,
        User.recovery_requested_at == requested_at,
    ).values(
        password_hash=password_hash.hash(data.password),
        password_reset_at=datetime.now(timezone.utc),
        recovery_requested_at=None,
    ).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise invalid
    audit(db, user, 'reset_password', 'user', user_id)
    db.commit()
    return {'message': 'Password updated. Sign in with your new password.'}
