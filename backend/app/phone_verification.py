"""Verify a saved phone number with a short-lived SMS code."""
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, String, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .daily_reminders import SmsDeliveryError, hubtel_send_sms
from .main import SECRET_KEY, AuthenticatedUser, Base, Db, User, app, audit

CODE_LIFETIME = timedelta(minutes=5)
RESEND_DELAY = timedelta(minutes=2)
MAX_ATTEMPTS = 5


class AccountPhoneChallenge(Base):
    __tablename__ = 'account_phone_challenges'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(16))
    nonce: Mapped[str] = mapped_column(String(43))
    code_digest: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int]
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PhoneVerificationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(pattern=r'^[0-9]{6}$')


def code_digest(user_id: int, phone: str, nonce: str, code: str) -> str:
    return hmac.digest(SECRET_KEY.encode(), f'phone-verification:{user_id}:{phone}:{nonce}:{code}'.encode(), 'sha256').hex()


@app.post('/auth/me/phone-verification/request')
def request_phone_verification(user: AuthenticatedUser, db: Db):
    account = db.scalar(select(User).where(User.id == user.id).with_for_update()
                        .execution_options(populate_existing=True))
    if account is None or account.is_suspended:
        raise HTTPException(401, 'Invalid or expired token')
    if not account.phone_number:
        raise HTTPException(422, 'Save a phone number before requesting verification')
    if account.phone_verified_at is not None:
        return {'verified': True}
    phone = account.phone_number
    now = datetime.now(timezone.utc)
    challenge = db.get(AccountPhoneChallenge, account.id)
    too_soon = HTTPException(429, 'Wait two minutes before requesting another code')
    if challenge and challenge.sent_at.replace(tzinfo=timezone.utc) > now - RESEND_DELAY:
        raise too_soon
    code = f'{secrets.randbelow(1_000_000):06d}'
    nonce = secrets.token_urlsafe(32)
    values = {
        'phone_number': phone, 'nonce': nonce,
        'code_digest': code_digest(account.id, phone, nonce, code), 'sent_at': now,
        'attempts': 0, 'consumed_at': None,
    }
    if challenge is None:
        db.add(AccountPhoneChallenge(user_id=account.id, **values))
    else:
        changed = db.execute(update(AccountPhoneChallenge).where(
            AccountPhoneChallenge.user_id == account.id,
            AccountPhoneChallenge.nonce == challenge.nonce,
        ).values(**values).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise too_soon
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise too_soon from None
    try:
        hubtel_send_sms(phone, f'AquaFarm Manager Ghana verification code: {code}. It expires in 5 minutes.')
    except SmsDeliveryError:
        raise HTTPException(503, 'Verification SMS could not be sent') from None
    return {'verified': False, 'destination': f'•••{phone[-4:]}'}


@app.post('/auth/me/phone-verification/confirm')
def confirm_phone_verification(data: PhoneVerificationIn, user: AuthenticatedUser, db: Db):
    now = datetime.now(timezone.utc)
    challenge = db.get(AccountPhoneChallenge, user.id)
    invalid = HTTPException(400, 'Invalid or expired verification code')
    if challenge is None or challenge.phone_number != user.phone_number:
        raise invalid
    valid = hmac.compare_digest(challenge.code_digest, code_digest(
        user.id, challenge.phone_number, challenge.nonce, data.code,
    ))
    if valid:
        confirmed = db.execute(update(User).where(
            User.id == user.id, User.phone_number == challenge.phone_number,
            User.phone_verified_at.is_(None), User.is_suspended.is_(False),
        ).values(phone_verified_at=now))
        if confirmed.rowcount != 1:
            raise invalid
    used = db.execute(update(AccountPhoneChallenge).where(
        AccountPhoneChallenge.user_id == user.id,
        AccountPhoneChallenge.nonce == challenge.nonce,
        AccountPhoneChallenge.sent_at > now - CODE_LIFETIME,
        AccountPhoneChallenge.consumed_at.is_(None),
        AccountPhoneChallenge.attempts < MAX_ATTEMPTS,
    ).values(attempts=AccountPhoneChallenge.attempts + 1, consumed_at=now if valid else None)
      .execution_options(synchronize_session=False))
    if used.rowcount != 1:
        raise invalid
    if valid:
        audit(db, user, 'verify_phone', 'user', user.id)
    db.commit()
    if not valid:
        raise invalid
    return {'phone_verified_at': now}
