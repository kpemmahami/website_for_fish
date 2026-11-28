"""Verify a saved phone number with a short-lived SMS code."""
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, String, delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .sms_gateway import SmsDeliveryError, configured_provider, send_sms, validate_delivery_settings, sandbox_enabled
from .main import (
    DATABASE_URL, SECRET_KEY, AuthenticatedUser, Base, Db, User, app, assign_phone_number,
    audit, duplicate_phone_claim, password_binding, password_hash,
)
from .development import enabled as local_test_enabled
from .phone_numbers import PhoneNumber

CODE_LIFETIME = timedelta(minutes=5)
RESEND_DELAY = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def otp_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.getenv(name, str(default)).strip()
    if not value.isascii() or not value.isdecimal() or len(value) > 6 or not minimum <= int(value) <= maximum:
        raise HTTPException(503, 'Verification is temporarily unavailable')
    return int(value)


def lifetime_seconds() -> int:
    return otp_setting('OTP_EXPIRY_SECONDS', int(CODE_LIFETIME.total_seconds()), 60, 600)


class AccountPhoneChallenge(Base):
    __tablename__ = 'account_phone_challenges'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(16))
    nonce: Mapped[str] = mapped_column(String(43))
    code_digest: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int]
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_phone: Mapped[str | None] = mapped_column(String(16))
    previous_code_digest: Mapped[str | None] = mapped_column(String(64))
    password_proof: Mapped[str | None] = mapped_column(String(64))


class SmsOtpQuota(Base):
    __tablename__ = 'sms_otp_quotas'
    bucket: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    attempts: Mapped[int]


def reserve_otp_sends(db: Db, account: User, phones: list[str], client_address: str | None, now: datetime):
    window = now.replace(minute=0, second=0, microsecond=0)
    limits = [(f'account:{account.id}', otp_setting('OTP_SENDS_PER_ACCOUNT_HOUR', 8, 1, 30))]
    phone_limit = otp_setting('OTP_SENDS_PER_PHONE_HOUR', 8, 1, 30)
    limits.extend((f'phone:{phone}', phone_limit) for phone in sorted(set(phones)))
    if client_address:
        limits.append((f'ip:{client_address}', otp_setting('OTP_SENDS_PER_IP_HOUR', 60, 1, 300)))
    insert = postgres_insert if db.get_bind().dialect.name == 'postgresql' else sqlite_insert
    for subject, limit in sorted(limits):
        key = hmac.digest(SECRET_KEY.encode(), f'otp-quota:{subject}'.encode(), 'sha256').hex()
        statement = insert(SmsOtpQuota).values(bucket=key, window_start=window, attempts=1)
        result = db.execute(statement.on_conflict_do_update(
            index_elements=[SmsOtpQuota.bucket, SmsOtpQuota.window_start],
            set_={'attempts': SmsOtpQuota.attempts + 1},
            where=SmsOtpQuota.attempts < limit,
        ).returning(SmsOtpQuota.attempts))
        if result.scalar_one_or_none() is None:
            db.rollback()
            raise HTTPException(429, 'Too many SMS requests. Try again later')
    db.execute(delete(SmsOtpQuota).where(SmsOtpQuota.window_start < window - timedelta(days=2)))


class PhoneVerificationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(pattern=r'^[0-9]{6}$')


class PhoneReplacementStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    phone_number: PhoneNumber
    password: str = Field(min_length=1, max_length=128)


class PhoneReplacementConfirm(PhoneVerificationIn):
    previous_code: str = Field(pattern=r'^[0-9]{6}$')


def code_digest(user_id: int, phone: str, nonce: str, code: str) -> str:
    return hmac.digest(SECRET_KEY.encode(), f'phone-verification:{user_id}:{phone}:{nonce}:{code}'.encode(), 'sha256').hex()


def local_test_sms_enabled() -> bool:
    return (os.getenv('AQUAFARM_LOCAL_TEST_SMS') == '1' and local_test_enabled(DATABASE_URL)
            and os.getenv('SMS_PROVIDER', 'hubtel').strip().lower() == 'hubtel')


def validate_otp_transport():
    if os.getenv('OTP_MODE', 'local').strip().lower() != 'local':
        raise HTTPException(503, 'Verification SMS could not be sent')
    try:
        if configured_provider() == 'arkesel':
            validate_delivery_settings()
            if sandbox_enabled():
                raise SmsDeliveryError('Sandbox SMS cannot complete phone verification')
    except SmsDeliveryError:
        raise HTTPException(503, 'Verification SMS could not be sent') from None


def issue_phone_code(db, account, phone, description, *, purpose=None, allow_local_test=True, client_address=None):
    local_test = allow_local_test and local_test_sms_enabled()
    if not local_test:
        validate_otp_transport()
    code = '000002' if local_test else f'{secrets.randbelow(1_000_000):06d}'
    save_challenge(db, account, phone, code, purpose=purpose, client_address=client_address)
    if not local_test:
        send_code(phone, code, description)


@app.post('/auth/me/phone-verification/request')
def request_phone_verification(user: AuthenticatedUser, db: Db, request: Request):
    account = db.scalar(select(User).where(User.id == user.id).with_for_update()
                        .execution_options(populate_existing=True))
    if account is None or account.is_suspended:
        raise HTTPException(401, 'Invalid or expired token')
    if not account.phone_number:
        raise HTTPException(422, 'Save a phone number before requesting verification')
    if account.phone_verified_at is not None:
        return {'verified': True}
    phone = account.phone_number
    issue_phone_code(db, account, phone, 'verification', allow_local_test=not account.is_platform_admin,
                     client_address=request.client.host if request.client else None)
    return {'verified': False, 'destination': f'•••{phone[-4:]}'}


def save_challenge(
    db: Db, account: User, phone: str, code: str, previous_code: str | None = None,
    *, purpose: str | None = None, client_address: str | None = None,
):
    now = datetime.now(timezone.utc)
    challenge = db.get(AccountPhoneChallenge, account.id)
    too_soon = HTTPException(429, 'Wait 60 seconds before requesting another code')
    if challenge and challenge.sent_at.replace(tzinfo=timezone.utc) > now - RESEND_DELAY:
        raise too_soon
    reserve_otp_sends(db, account, [phone, account.phone_number] if previous_code is not None else [phone],
                      client_address, now)
    nonce = secrets.token_urlsafe(32)
    values = {
        'phone_number': phone, 'nonce': nonce,
        'code_digest': code_digest(account.id, phone, nonce, code), 'sent_at': now,
        'attempts': 0, 'consumed_at': None,
        'previous_phone': account.phone_number if previous_code is not None else None,
        'previous_code_digest': code_digest(account.id, account.phone_number, nonce, previous_code)
        if previous_code is not None else None,
        'password_proof': password_binding(account, purpose) if purpose is not None else None,
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


def send_code(phone: str, code: str, description: str):
    try:
        seconds = lifetime_seconds()
        send_sms(phone, f'AquaFarm Manager Ghana {description} code: {code}. It expires in {seconds} seconds.')
    except SmsDeliveryError:
        raise HTTPException(503, 'Verification SMS could not be sent') from None


@app.post('/auth/me/phone-verification/confirm')
def confirm_phone_verification(data: PhoneVerificationIn, user: AuthenticatedUser, db: Db):
    now = datetime.now(timezone.utc)
    challenge = db.get(AccountPhoneChallenge, user.id)
    invalid = HTTPException(400, 'Invalid or expired verification code')
    if challenge is None or challenge.password_proof is not None or challenge.phone_number != user.phone_number:
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
    consume_attempt(db, challenge, now, valid, invalid)
    if valid:
        audit(db, user, 'verify_phone', 'user', user.id)
    db.commit()
    if not valid:
        raise invalid
    return {'phone_verified_at': now}


def consume_attempt(db: Db, challenge: AccountPhoneChallenge, now: datetime, valid: bool, invalid: HTTPException):
    used = db.execute(update(AccountPhoneChallenge).where(
        AccountPhoneChallenge.user_id == challenge.user_id,
        AccountPhoneChallenge.nonce == challenge.nonce,
        AccountPhoneChallenge.sent_at > now - timedelta(seconds=lifetime_seconds()),
        AccountPhoneChallenge.consumed_at.is_(None),
        AccountPhoneChallenge.attempts < otp_setting('OTP_MAX_ATTEMPTS', MAX_ATTEMPTS, 1, 5),
    ).values(attempts=AccountPhoneChallenge.attempts + 1, consumed_at=now if valid else None)
      .execution_options(synchronize_session=False))
    if used.rowcount != 1:
        raise invalid


@app.post('/auth/me/phone-replacement/request')
def request_phone_replacement(data: PhoneReplacementStart, user: AuthenticatedUser, db: Db, request: Request):
    account = db.scalar(select(User).where(User.id == user.id).with_for_update()
                        .execution_options(populate_existing=True))
    if account is None or account.is_suspended:
        raise HTTPException(401, 'Invalid or expired token')
    if account.is_platform_admin:
        raise HTTPException(403, 'Administrator phone replacement requires privileged recovery')
    if not account.phone_number or account.phone_verified_at is None:
        raise HTTPException(409, 'Verify your saved phone number before replacing it')
    old_phone = account.phone_number
    if not password_hash.verify(data.password, account.password_hash):
        raise HTTPException(403, 'The current password is incorrect')
    if data.phone_number == old_phone:
        raise HTTPException(422, 'Enter a different phone number')
    if db.scalar(select(User.id).where(User.phone_number == data.phone_number).limit(1)) is not None:
        raise HTTPException(409, 'This phone number is already assigned to an account')
    validate_otp_transport()
    code = f'{secrets.randbelow(1_000_000):06d}'
    previous_code = f'{secrets.randbelow(1_000_000):06d}'
    save_challenge(db, account, data.phone_number, code, previous_code, purpose='phone-replacement',
                   client_address=request.client.host if request.client else None)
    send_code(old_phone, previous_code, 'current phone approval')
    send_code(data.phone_number, code, 'new phone verification')
    return {'previous_destination': f'•••{old_phone[-4:]}', 'new_destination': f'•••{data.phone_number[-4:]}'}


@app.post('/auth/me/phone-replacement/confirm')
def confirm_phone_replacement(data: PhoneReplacementConfirm, user: AuthenticatedUser, db: Db):
    now = datetime.now(timezone.utc)
    account = db.scalar(select(User).where(User.id == user.id).with_for_update()
                        .execution_options(populate_existing=True))
    challenge = db.get(AccountPhoneChallenge, user.id)
    invalid = HTTPException(400, 'Invalid or expired phone replacement codes')
    if (
        account is None or account.is_suspended or account.is_platform_admin
        or challenge is None or not challenge.previous_phone or not challenge.previous_code_digest
        or account.phone_number != challenge.previous_phone or account.phone_verified_at is None
        or not challenge.password_proof
        or not hmac.compare_digest(challenge.password_proof, password_binding(account, 'phone-replacement'))
    ):
        raise invalid
    valid_new = hmac.compare_digest(challenge.code_digest, code_digest(
        account.id, challenge.phone_number, challenge.nonce, data.code,
    ))
    valid_old = hmac.compare_digest(challenge.previous_code_digest, code_digest(
        account.id, challenge.previous_phone, challenge.nonce, data.previous_code,
    ))
    consume_attempt(db, challenge, now, valid_new and valid_old, invalid)
    if not (valid_new and valid_old):
        db.commit()
        raise invalid
    assign_phone_number(db, account, challenge.phone_number)
    account.phone_verified_at = now
    account.session_generation = secrets.token_hex(16)
    account.recovery_requested_at = None
    audit(db, account, 'replace_verified_phone', 'user', account.id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if duplicate_phone_claim(error):
            raise HTTPException(409, 'This phone number is already assigned to an account') from None
        raise
    return {'message': 'Phone number changed. Sign in again with the new number or your email.'}


def send_institution_phone_code(db: Db, account: User, token: str, client_address: str | None = None):
    phone = account.phone_number
    if not phone:
        raise HTTPException(409, 'A mobile number is required for institution password setup')
    issue_phone_code(db, account, phone, 'institution account verification',
                     purpose=f'institution-phone:{token}', client_address=client_address)
    return {'destination': f'•••{phone[-4:]}'}


def verify_institution_phone_code(db: Db, account: User, code: str, token: str) -> None:
    challenge = db.get(AccountPhoneChallenge, account.id)
    invalid = HTTPException(400, 'Invalid or expired institution verification code')
    if (
        challenge is None or challenge.previous_phone is not None or challenge.phone_number != account.phone_number
        or not challenge.password_proof
        or not hmac.compare_digest(challenge.password_proof, password_binding(account, f'institution-phone:{token}'))
    ):
        raise invalid
    valid = hmac.compare_digest(challenge.code_digest, code_digest(
        account.id, challenge.phone_number, challenge.nonce, code,
    ))
    consume_attempt(db, challenge, datetime.now(timezone.utc), valid, invalid)
    if not valid:
        db.commit()
        raise invalid
