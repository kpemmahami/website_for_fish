"""Verify the email and phone of a pending administrator before MFA enrollment."""
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .administration import AdminSetup, require_platform_owner
from .daily_reminders import SmsDeliveryError, hubtel_send_sms
from .main import SECRET_KEY, Base, CurrentUser, Db, User, app, audit, password_binding, password_hash, require_platform_admin
from .password_recovery import recovery_mail_settings, send_account_email

TTL = timedelta(minutes=10)
RESEND_DELAY = timedelta(minutes=2)
MAX_ATTEMPTS = 5
TAGS = ['Platform administration']


class AdministratorContactProof(Base):
    __tablename__ = 'administrator_contact_proofs'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    link_digest: Mapped[str] = mapped_column(String(64), unique=True)
    code_digest: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int]
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrollment_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    authenticator_nonce: Mapped[str | None] = mapped_column(String(43))
    last_authenticator_step: Mapped[int | None] = mapped_column(BigInteger)
    authenticator_window: Mapped[int | None] = mapped_column(BigInteger)
    authenticator_attempts: Mapped[int | None]
    existing_enrollment_proof: Mapped[str | None] = mapped_column(String(64))


class VerifyAdministratorContact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code: str = Field(pattern=r'^[0-9]{6}$')


class ActivateAdministrator(VerifyAdministratorContact):
    password: str = Field(min_length=12, max_length=128)


class ExistingAdministratorEnrollment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=1, max_length=128)


def digest(label: str, value: str) -> str:
    return hmac.new(SECRET_KEY.encode(), f'administrator-contact:{label}:{value}'.encode(), hashlib.sha256).hexdigest()


def authenticator_key(user_id: int, nonce: str) -> bytes:
    key = os.getenv('AQUAFARM_ADMIN_AUTHENTICATOR_KEY', '')
    if len(key) < 32:
        raise HTTPException(503, 'Administrator authenticator service is unavailable')
    return hmac.digest(key.encode(), f'aquafarm-totp:{user_id}:{nonce}'.encode(), 'sha256')[:20]


def matching_step(key: bytes, code: str, now: datetime, last_step: int | None) -> int | None:
    current = int(now.timestamp()) // 30
    for step in (current, current - 1):
        if last_step is not None and step <= last_step:
            continue
        hashed = hmac.digest(key, step.to_bytes(8, 'big'), 'sha1')
        offset = hashed[-1] & 15
        digits = (int.from_bytes(hashed[offset:offset + 4], 'big') & 0x7fffffff) % 1_000_000
        if hmac.compare_digest(code, f'{digits:06d}'):
            return step
    return None


def account_enrollment_proof(account: User) -> str:
    return digest('existing', f'{password_binding(account, "administrator-enrollment")}:{account.email}:{account.phone_number}')


def can_enroll(account: User | None, proof: AdministratorContactProof) -> bool:
    if account is None or account.is_suspended or not account.phone_number:
        return False
    if proof.existing_enrollment_proof is None:
        return account.account_type == 'pending_admin'
    return (
        account.is_platform_admin and proof.last_authenticator_step is None
        and hmac.compare_digest(proof.existing_enrollment_proof, account_enrollment_proof(account))
    )


@app.post('/admin/administrators/{administrator_id}/contact-verification', tags=TAGS)
def start_contact_verification(administrator_id: int, owner: CurrentUser, db: Db):
    require_platform_owner(owner, db)
    db.scalar(select(AdminSetup.id).where(AdminSetup.id == 1).with_for_update())
    account = db.get(User, administrator_id)
    if account is None or account.account_type != 'pending_admin' or not account.phone_number:
        raise HTTPException(404, 'Pending administrator not found')
    return send_contact_verification(db, owner, account, None)


@app.post('/auth/admin/authenticator-enrollment', tags=TAGS)
def start_existing_enrollment(data: ExistingAdministratorEnrollment, user: CurrentUser, db: Db):
    require_platform_admin(user)
    account = db.scalar(select(User).where(User.id == user.id).with_for_update()
                        .execution_options(populate_existing=True))
    if account is None or account.is_suspended or not password_hash.verify(data.password, account.password_hash):
        raise HTTPException(403, 'The current password is incorrect')
    if not account.phone_number:
        raise HTTPException(409, 'A saved phone number is required for administrator enrollment')
    proof = db.get(AdministratorContactProof, account.id)
    if proof and proof.last_authenticator_step is not None:
        raise HTTPException(409, 'This account already has an authenticator')
    return send_contact_verification(db, account, account, account_enrollment_proof(account))


def send_contact_verification(db: Db, actor: User, account: User, existing_proof: str | None):
    settings = recovery_mail_settings()
    if settings is None:
        raise HTTPException(503, 'Verification email is unavailable')
    authenticator_key(account.id, 'configuration-check')
    administrator_id = account.id
    now = datetime.now(timezone.utc)
    proof = db.get(AdministratorContactProof, administrator_id)
    if proof and proof.sent_at.replace(tzinfo=timezone.utc) > now - RESEND_DELAY:
        raise HTTPException(429, 'Wait two minutes before sending another verification request')
    token = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1_000_000):06d}'
    if proof is None:
        proof = AdministratorContactProof(user_id=administrator_id)
        db.add(proof)
    proof.link_digest = digest('link', token)
    proof.code_digest = digest('sms', f'{token}:{code}')
    proof.sent_at = now
    proof.attempts = 0
    proof.verified_at = None
    proof.enrollment_digest = None
    proof.authenticator_nonce = None
    proof.existing_enrollment_proof = existing_proof
    email, phone = account.email, account.phone_number
    audit(db, actor, 'send_admin_contact_verification', 'platform_admin', administrator_id)
    db.commit()
    try:
        hubtel_send_sms(phone, f'AquaFarm Manager Ghana verification code: {code}. It expires in 10 minutes.')
    except SmsDeliveryError:
        raise HTTPException(503, 'Verification SMS could not be sent') from None
    if not send_account_email(
        settings, email, 'Verify your AquaFarm administrator account',
        'Open this link within 10 minutes and enter the code sent to your phone.',
        urlencode({'administrator-contact': token}),
    ):
        raise HTTPException(503, 'Verification email could not be sent')
    return {'message': 'Verification link and SMS code sent.'}


@app.post('/auth/admin/contact-verification', tags=TAGS)
def verify_contact(data: VerifyAdministratorContact, db: Db):
    now = datetime.now(timezone.utc)
    proof = db.scalar(select(AdministratorContactProof).where(
        AdministratorContactProof.link_digest == digest('link', data.token),
        AdministratorContactProof.sent_at > now - TTL,
        AdministratorContactProof.verified_at.is_(None),
        AdministratorContactProof.attempts < MAX_ATTEMPTS,
    ))
    invalid = HTTPException(400, 'Invalid or expired verification request')
    if proof is None:
        raise invalid
    account = db.get(User, proof.user_id)
    if not can_enroll(account, proof):
        raise invalid
    valid = hmac.compare_digest(proof.code_digest, digest('sms', f'{data.token}:{data.code}'))
    if valid:
        enrollment_token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        key = authenticator_key(account.id, nonce)
    claimed = db.execute(update(AdministratorContactProof).where(
        AdministratorContactProof.user_id == proof.user_id,
        AdministratorContactProof.link_digest == proof.link_digest,
        AdministratorContactProof.sent_at > now - TTL,
        AdministratorContactProof.verified_at.is_(None),
        AdministratorContactProof.attempts < MAX_ATTEMPTS,
    ).values(
        attempts=0 if valid else AdministratorContactProof.attempts + 1,
        verified_at=now if valid else None,
        enrollment_digest=digest('enrollment', enrollment_token) if valid else None,
        authenticator_nonce=nonce if valid else None,
    ).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise invalid
    if valid:
        audit(db, account, 'verify_admin_contacts', 'platform_admin', account.id)
    db.commit()
    if not valid:
        raise invalid
    return {
        'enrollment_token': enrollment_token,
        'setup_key': base64.b32encode(key).decode(),
        'account_email': account.email,
        'existing_account': proof.existing_enrollment_proof is not None,
    }


@app.post('/auth/admin/activate', tags=TAGS)
def activate_administrator(data: ActivateAdministrator, db: Db):
    now = datetime.now(timezone.utc)
    enrollment = digest('enrollment', data.token)
    proof = db.scalar(select(AdministratorContactProof).where(
        AdministratorContactProof.enrollment_digest == enrollment,
        AdministratorContactProof.verified_at > now - TTL,
        AdministratorContactProof.attempts < MAX_ATTEMPTS,
    ))
    invalid = HTTPException(400, 'Invalid or expired administrator activation')
    if proof is None or not proof.authenticator_nonce:
        raise invalid
    db.scalar(select(AdminSetup.id).where(AdminSetup.id == 1).with_for_update())
    account = db.scalar(select(User).where(User.id == proof.user_id).with_for_update())
    if not can_enroll(account, proof):
        raise invalid
    existing = proof.existing_enrollment_proof is not None
    step = matching_step(authenticator_key(proof.user_id, proof.authenticator_nonce), data.code, now, None)
    values = {'attempts': AdministratorContactProof.attempts + 1}
    if step is not None:
        values.update(enrollment_digest=None, last_authenticator_step=step, existing_enrollment_proof=None)
    claimed = db.execute(update(AdministratorContactProof).where(
        AdministratorContactProof.user_id == proof.user_id,
        AdministratorContactProof.enrollment_digest == enrollment,
        AdministratorContactProof.verified_at > now - TTL,
        AdministratorContactProof.attempts < MAX_ATTEMPTS,
    ).values(**values).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise invalid
    if step is None:
        db.commit()
        raise invalid
    account.password_hash = password_hash.hash(data.password)
    account.phone_verified_at = proof.verified_at
    account.account_type = 'admin'
    if existing:
        account.session_generation = secrets.token_hex(16)
        account.recovery_requested_at = None
    audit(db, account, 'enroll_existing_authenticator' if existing else 'activate_administrator', 'platform_admin', account.id)
    db.commit()
    return {'message': 'Administrator account activated. Sign in with your new credentials.'}


def check_administrator_authenticator(db, user: User, code: str | None) -> None:
    proof = db.get(AdministratorContactProof, user.id)
    if proof is None or (proof.last_authenticator_step is None and proof.existing_enrollment_proof is not None):
        return  # Preserve accounts created before authenticator enrollment was introduced.
    if proof.last_authenticator_step is None or not proof.authenticator_nonce:
        raise HTTPException(403, 'Administrator authenticator enrollment is incomplete')
    if code is None:
        raise HTTPException(428, 'Enter the code from your authenticator app.')
    now = datetime.now(timezone.utc)
    window = int(now.timestamp()) // 120
    attempts = (proof.authenticator_attempts or 0) if proof.authenticator_window == window else 0
    if attempts >= MAX_ATTEMPTS:
        raise HTTPException(429, 'Too many authenticator attempts. Try again shortly.')
    step = matching_step(authenticator_key(user.id, proof.authenticator_nonce), code, now, proof.last_authenticator_step)
    values = {'authenticator_window': window, 'authenticator_attempts': attempts + 1}
    if step is not None:
        values['last_authenticator_step'] = step
    claimed = db.execute(update(AdministratorContactProof).where(
        AdministratorContactProof.user_id == user.id,
        AdministratorContactProof.authenticator_window == proof.authenticator_window,
        AdministratorContactProof.authenticator_attempts == proof.authenticator_attempts,
        AdministratorContactProof.last_authenticator_step == proof.last_authenticator_step,
    ).values(**values).execution_options(synchronize_session=False))
    db.commit()
    if claimed.rowcount != 1 or step is None:
        raise HTTPException(401, 'Invalid or already used authenticator code')
