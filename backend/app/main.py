import hashlib
import hmac
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from pwdlib import PasswordHash
from sqlalchemy import DateTime, ForeignKey, Index, String, Float, Text, Boolean, create_engine, false, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .database import database_failure_reason, database_url
from .phone_numbers import PhoneNumber, normalize_phone_number

DATABASE_URL = database_url()
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError('Set SECRET_KEY to a random string of at least 32 characters.')
TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_MINUTES', '60'))
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.get_backend_name() == 'sqlite' else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
password_hash = PasswordHash.recommended()
bearer = HTTPBearer()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    __table_args__ = (Index('uq_users_phone_number_claim', 'phone_number_claim', unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone_number_claim: Mapped[str | None] = mapped_column(String(16))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_suspended: Mapped[bool] = mapped_column(Boolean, server_default=false())
    session_generation: Mapped[str | None] = mapped_column(String(32))
    initial_password_required: Mapped[bool] = mapped_column(Boolean, server_default=false())
    sms_daily_records_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sms_loan_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sms_financial_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    account_type: Mapped[str] = mapped_column(String(20), default='farmer')
    farms: Mapped[list['Farm']] = relationship(back_populates='owner')

    @property
    def is_platform_admin(self) -> bool:
        return self.account_type == 'admin'

class Farm(Base):
    __tablename__ = 'farms'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    region: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100))
    farm_type: Mapped[str] = mapped_column(String(30))
    species: Mapped[str] = mapped_column(String(100))
    farm_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    nearest_landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gps_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[User] = relationship(back_populates='farms')
    units: Mapped[list['ProductionUnit']] = relationship(back_populates='farm')

class ProductionUnit(Base):
    __tablename__ = 'production_units'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    unit_type: Mapped[str] = mapped_column(String(20))
    capacity_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_tag: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: uuid.uuid4().hex)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    farm: Mapped[Farm] = relationship(back_populates='units')

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column()
    details: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Register(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class FarmerRegister(Register):
    phone_number: PhoneNumber
    business_type: Literal['farmer','processor','integrated'] = 'farmer'


class AdminRegister(Register):
    password: str = Field(min_length=12, max_length=128)


class Login(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: str
    authenticator_code: str | None = Field(default=None, pattern=r'^[0-9]{6}$')
    recovery_code: str | None = Field(default=None, max_length=64)

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class InitialPasswordChallenge(BaseModel):
    initial_password_token: str


class InstitutionMfaChallenge(BaseModel):
    institution_mfa_token: str


class InitialPasswordProof(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=1, max_length=2048)


class InitialPasswordChange(InitialPasswordProof):
    password: str = Field(min_length=12, max_length=128)
    code: str = Field(pattern=r'^[0-9]{6}$')


INITIAL_PASSWORD_PURPOSE = 'institution_initial_password'
INSTITUTION_MFA_PURPOSE = 'institution_sign_in_mfa'

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    phone_number: str | None
    phone_verified_at: datetime | None
    sms_daily_records_enabled: bool
    sms_loan_reminders_enabled: bool
    sms_financial_alerts_enabled: bool
    account_type: Literal['legacy', 'farmer', 'pending_farmer', 'institution', 'admin']
    is_platform_admin: bool = False
    is_platform_owner: bool = False
    authenticator_enrolled: bool = False

class ContactUpdate(BaseModel):
    phone_number: PhoneNumber | None = None
    sms_daily_records_enabled: bool = False
    sms_loan_reminders_enabled: bool = False
    sms_financial_alerts_enabled: bool | None = None

    @model_validator(mode='after')
    def enabled_requires_phone(self):
        if (self.sms_daily_records_enabled or self.sms_loan_reminders_enabled or self.sms_financial_alerts_enabled) and not self.phone_number:
            raise ValueError('Add a valid international phone number before enabling SMS reminders')
        return self

class FarmIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    region: str = Field(min_length=2, max_length=100)
    district: str = Field(min_length=2, max_length=100)
    farm_type: Literal['pond', 'cage', 'tank', 'mixed']
    species: str = Field(min_length=2, max_length=100)
    farm_address: str | None = Field(default=None, max_length=500)
    nearest_landmark: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(default=None, ge=0)
    location_method: Literal['gps', 'manual'] | None = None
    gps_captured_at: datetime | None = None

    @model_validator(mode='after')
    def validate_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be provided together')
        if self.location_method == 'gps' and (self.latitude is None or self.gps_captured_at is None):
            raise ValueError('GPS method requires coordinates and capture time')
        if self.latitude is None and any(x is not None for x in (self.location_method, self.gps_accuracy_m, self.gps_captured_at)):
            raise ValueError('Location metadata requires coordinates')
        return self

class FarmOut(FarmIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    created_at: datetime
    archived_at: datetime | None = None

class UnitIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    unit_type: Literal['pond', 'cage', 'tank']
    capacity_m3: float | None = Field(default=None, gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def validate_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Latitude and longitude must be provided together')
        return self

class UnitOut(UnitIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farm_id: int
    evidence_tag: str
    is_active: bool
    created_at: datetime

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int
    action: str
    entity_type: str
    entity_id: int
    details: str
    created_at: datetime

def audit(db: Session, user: User, action: str, entity_type: str, entity_id: int, details: str = '{}'):
    db.add(AuditLog(actor_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details))

def get_db():
    with SessionLocal() as db:
        yield db

Db = Annotated[Session, Depends(get_db)]

def password_binding(user: User, purpose: str) -> str:
    message = f'{purpose}:{user.id}:{user.password_hash}'
    if user.session_generation is not None:
        message += f':{user.session_generation}'
    return hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def authenticated_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)], db: Db) -> User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=['HS256'])
        if payload.get('purpose', 'access') != 'access':
            raise ValueError('Unexpected token purpose')
        user_id = int(payload['sub'])
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail='Invalid or expired token', headers={'WWW-Authenticate': 'Bearer'})
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='User no longer exists')
    if user.is_suspended or user.initial_password_required:
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    if user.account_type == 'institution' and user.phone_verified_at is not None and payload.get('institution_mfa') is not True:
        raise HTTPException(status_code=401, detail='Institution sign-in verification is required')
    binding = payload.get('binding')
    if (
        (binding is None and (user.password_reset_at is not None or user.session_generation is not None))
        or (binding is not None and (
            not isinstance(binding, str) or not hmac.compare_digest(binding, password_binding(user, 'access'))
        ))
    ):
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    return user

AuthenticatedUser = Annotated[User, Depends(authenticated_user)]


def current_user(user: AuthenticatedUser) -> User:
    if user.account_type == 'pending_farmer':
        raise HTTPException(403, 'Farmer account approval is pending')
    return user


CurrentUser = Annotated[User, Depends(current_user)]

def owned_farm(farm_id: int, user: User, db: Session) -> Farm:
    farm = db.scalar(select(Farm).where(Farm.id == farm_id, Farm.owner_id == user.id, Farm.archived_at.is_(None)))
    if farm is None:
        raise HTTPException(status_code=404, detail='Farm not found')
    return farm

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    from .daily_reminders import start_daily_reminder_scheduler, stop_daily_reminder_scheduler

    start_daily_reminder_scheduler()
    try:
        yield
    finally:
        stop_daily_reminder_scheduler()


app = FastAPI(title='AquaFarm Manager Ghana API', version='0.1.0', lifespan=lifespan)

@app.get('/health')
def health():
    return {'status': 'ok'}

def new_user(data: Register, account_type: str) -> User:
    return User(full_name=data.full_name, email=str(data.email).lower(),
                password_hash=password_hash.hash(data.password), account_type=account_type)


def duplicate_phone_claim(error: IntegrityError) -> bool:
    original = error.orig
    if getattr(original, 'sqlstate', None) == '23505':
        return getattr(getattr(original, 'diag', None), 'constraint_name', None) == 'uq_users_phone_number_claim'
    return getattr(original, 'sqlite_errorname', None) == 'SQLITE_CONSTRAINT_UNIQUE' and str(original).endswith(
        'users.phone_number_claim',
    )


def assign_phone_number(db: Session, user: User, phone: str | None) -> None:
    if phone == user.phone_number:
        return
    if phone is not None:
        conflicts = select(User.id).where(User.phone_number == phone)
        if user.id is not None:
            conflicts = conflicts.where(User.id != user.id)
        if db.scalar(conflicts.limit(1)) is not None:
            raise HTTPException(409, 'This phone number is already assigned to an account')
    user.phone_number = phone
    user.phone_number_claim = phone
    user.phone_verified_at = None


FARMER_REGISTRATION_PATHS = {'/auth/register', '/auth/farmer/register'}
registration_log = logging.getLogger('aquafarm.registration')


@app.exception_handler(RequestValidationError)
async def safe_registration_validation(request: Request, error: RequestValidationError):
    if request.method == 'POST' and request.url.path in (
        FARMER_REGISTRATION_PATHS | {
            '/auth/institution/initial-password', '/auth/me/phone-verification/confirm',
            '/auth/institution/initial-password/verification',
            '/auth/institution/mfa/request', '/auth/institution/mfa/confirm',
            '/auth/admin/authenticator-enrollment',
            '/auth/admin/login', '/auth/admin/recovery-codes',
            '/auth/me/phone-replacement/request', '/auth/me/phone-replacement/confirm',
        }
    ):
        return JSONResponse({'detail': [{'loc': item['loc'], 'type': item['type']}
                                         for item in error.errors()]}, status_code=422)
    return await request_validation_exception_handler(request, error)


@app.get('/ready')
def ready(db: Db):
    from .processing import ProcessingBusiness

    try:
        db.execute(select(User).limit(0))
        db.execute(select(ProcessingBusiness).limit(0))
    except SQLAlchemyError as error:
        db.rollback()
        registration_log.error('Registration readiness check failed. exception=%s sqlstate=%s reason=%s',
                               type(error).__name__, getattr(getattr(error, 'orig', None), 'sqlstate', None),
                               database_failure_reason(DATABASE_URL, error))
        raise HTTPException(status_code=503, detail='Service is temporarily unavailable') from None
    return {'status': 'ok'}


def duplicate_email(error: IntegrityError) -> bool:
    original = error.orig
    if getattr(original, 'sqlstate', None) == '23505':
        return getattr(getattr(original, 'diag', None), 'constraint_name', None) in ('ix_users_email', 'users_email_key')
    return getattr(original, 'sqlite_errorname', None) == 'SQLITE_CONSTRAINT_UNIQUE' and str(original).endswith('users.email')


@app.post('/auth/register', response_model=UserOut, status_code=201)
@app.post('/auth/farmer/register', response_model=UserOut, status_code=201)
def register(data: FarmerRegister, db: Db):
    from .development import auto_approve_signup

    test_signup = auto_approve_signup(DATABASE_URL)
    user = new_user(data, 'farmer' if test_signup else 'pending_farmer')
    try:
        if db.scalar(select(User.id).where(User.email == user.email)) is not None:
            raise HTTPException(409, 'Email already registered')
        assign_phone_number(db, user, data.phone_number)
        db.add(user)
        db.flush()
        if data.business_type != 'farmer':
            from .processing import ProcessingBusiness
            db.add(ProcessingBusiness(owner_id=user.id,name=data.full_name,business_type=data.business_type))
        if test_signup:
            audit(db, user, 'auto_approve_local_test_signup', 'farmer_account', user.id)
        response = UserOut.model_validate(user)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        if isinstance(error, IntegrityError) and duplicate_email(error):
            raise HTTPException(status_code=409, detail='Email already registered') from None
        if isinstance(error, IntegrityError) and duplicate_phone_claim(error):
            raise HTTPException(409, 'This phone number is already assigned to an account') from None
        original = getattr(error, 'orig', None)
        registration_log.error('Farmer registration failed. exception=%s sqlstate=%s reason=%s',
                               type(error).__name__, getattr(original, 'sqlstate', None),
                               database_failure_reason(DATABASE_URL, error))
        raise HTTPException(status_code=503, detail='Registration is temporarily unavailable') from None
    return response


def issue_access_token(user: User, *, institution_mfa: bool = False) -> Token:
    token = jwt.encode({
        'sub': str(user.id), 'purpose': 'access', 'binding': password_binding(user, 'access'),
        'institution_mfa': institution_mfa,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES),
    }, SECRET_KEY, algorithm='HS256')
    return Token(access_token=token)


def institution_challenge(user: User, purpose: str) -> str:
    return jwt.encode({
        'sub': str(user.id), 'purpose': purpose, 'jti': uuid.uuid4().hex,
        'binding': password_binding(user, purpose),
        'exp': datetime.now(timezone.utc) + timedelta(minutes=10),
    }, SECRET_KEY, algorithm='HS256')


def login_account(data: Login, db: Session, account_types: tuple[str, ...]) -> Token | InitialPasswordChallenge | InstitutionMfaChallenge:
    from .development import DEVELOPMENT_ACCOUNTS, enabled, seeded_account

    identifier = data.email.lower()
    local_test = enabled(DATABASE_URL)
    email = DEVELOPMENT_ACCOUNTS.get(identifier, identifier) if local_test else identifier
    phone = normalize_phone_number(identifier)
    if phone is not None:
        matches = db.scalars(select(User).where(
            User.phone_number == phone, User.account_type.in_(account_types),
        ).limit(2)).all()
        user = matches[0] if len(matches) == 1 else None
    else:
        user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.email in DEVELOPMENT_ACCOUNTS.values():
        if seeded_account(db, user.id) and not local_test:
            raise HTTPException(status_code=401, detail='Invalid credentials')
        if identifier in DEVELOPMENT_ACCOUNTS and not seeded_account(db, user.id):
            raise HTTPException(status_code=401, detail='Invalid credentials')
    if user is None or user.is_suspended or user.account_type not in account_types or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if user.account_type == 'institution' and user.initial_password_required:
        return InitialPasswordChallenge(initial_password_token=institution_challenge(user, INITIAL_PASSWORD_PURPOSE))
    if user.account_type == 'institution' and user.phone_verified_at is not None:
        return InstitutionMfaChallenge(institution_mfa_token=institution_challenge(user, INSTITUTION_MFA_PURPOSE))
    token = issue_access_token(user)
    if user.is_platform_admin:
        from .administrator_verification import check_administrator_authenticator, use_administrator_recovery_code

        if data.recovery_code is not None:
            if data.authenticator_code is not None:
                raise HTTPException(422, 'Use one second factor at a time')
            use_administrator_recovery_code(db, user, data.recovery_code)
        else:
            check_administrator_authenticator(db, user, data.authenticator_code)
    return token


@app.post('/auth/login', response_model=Token)
@app.post('/auth/farmer/login', response_model=Token)
def login(data: Login, db: Db):
    return login_account(data, db, ('farmer', 'legacy', 'pending_farmer'))


@app.post('/auth/institution/login', response_model=Token | InitialPasswordChallenge | InstitutionMfaChallenge)
def institution_login(data: Login, db: Db):
    return login_account(data, db, ('institution', 'legacy'))


def institution_challenge_account(token: str, db: Session, purpose: str) -> User:
    invalid = HTTPException(400, 'This institution challenge is invalid or expired')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'],
                             options={'require': ['exp', 'sub', 'purpose', 'binding']})
        account_id = int(payload['sub'])
        if payload['purpose'] != purpose or not isinstance(payload['binding'], str):
            raise invalid
    except (InvalidTokenError, TypeError, ValueError):
        raise invalid from None
    user = db.scalar(select(User).where(User.id == account_id).with_for_update())
    if (
        user is None or user.is_suspended or user.account_type != 'institution'
        or not hmac.compare_digest(payload['binding'], password_binding(user, purpose))
    ):
        raise invalid
    return user


def initial_password_account(token: str, db: Session) -> User:
    user = institution_challenge_account(token, db, INITIAL_PASSWORD_PURPOSE)
    if not user.initial_password_required:
        raise HTTPException(400, 'This password setup session is invalid or expired')
    return user


def institution_mfa_account(token: str, db: Session) -> User:
    user = institution_challenge_account(token, db, INSTITUTION_MFA_PURPOSE)
    if user.initial_password_required or user.phone_verified_at is None:
        raise HTTPException(400, 'This institution challenge is invalid or expired')
    return user


class InstitutionMfaConfirm(InitialPasswordProof):
    code: str = Field(pattern=r'^[0-9]{6}$')


@app.post('/auth/institution/mfa/request')
def send_institution_mfa(data: InitialPasswordProof, db: Db, request: Request):
    from .phone_verification import send_institution_phone_code

    return send_institution_phone_code(db, institution_mfa_account(data.token, db), data.token,
                                       request.client.host if request.client else None)


@app.post('/auth/institution/mfa/confirm', response_model=Token)
def confirm_institution_mfa(data: InstitutionMfaConfirm, db: Db):
    from .phone_verification import verify_institution_phone_code

    user = institution_mfa_account(data.token, db)
    verify_institution_phone_code(db, user, data.code, data.token)
    session = issue_access_token(user, institution_mfa=True)
    audit(db, user, 'institution_mfa_sign_in', 'user', user.id)
    db.commit()
    return session


@app.post('/auth/institution/initial-password/verification')
def send_initial_password_verification(data: InitialPasswordProof, db: Db, request: Request):
    from .phone_verification import send_institution_phone_code

    return send_institution_phone_code(db, initial_password_account(data.token, db), data.token,
                                       request.client.host if request.client else None)


@app.post('/auth/institution/initial-password', response_model=Token)
def replace_initial_password(data: InitialPasswordChange, db: Db):
    from .phone_verification import verify_institution_phone_code

    user = initial_password_account(data.token, db)
    if password_hash.verify(data.password, user.password_hash):
        raise HTTPException(422, 'Choose a password different from the initial password')
    verify_institution_phone_code(db, user, data.code, data.token)
    now = datetime.now(timezone.utc)
    changed = db.execute(update(User).where(
        User.id == user.id,
        User.account_type == 'institution',
        User.initial_password_required.is_(True),
        User.is_suspended.is_(False),
        User.password_hash == user.password_hash,
        User.session_generation == user.session_generation,
    ).values(
        password_hash=password_hash.hash(data.password),
        initial_password_required=False,
        password_reset_at=now,
        phone_verified_at=now,
        recovery_requested_at=None,
    ).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(400, 'This password setup session is invalid or expired')
    audit(db, user, 'replace_initial_password', 'user', user.id)
    db.refresh(user)
    session = issue_access_token(user, institution_mfa=True)
    db.commit()
    return session


@app.post('/auth/admin/login', response_model=Token)
def admin_login(data: Login, db: Db):
    return login_account(data, db, ('admin',))


def require_platform_admin(user: User):
    if not user.is_platform_admin:
        raise HTTPException(403, 'Platform administrator access required')


@app.get('/auth/me', response_model=UserOut)
def me(user: AuthenticatedUser, db: Db):
    from .administration import is_platform_owner
    from .administrator_verification import AdministratorContactProof

    proof = db.get(AdministratorContactProof, user.id) if user.is_platform_admin else None
    return UserOut.model_validate(user).model_copy(update={
        'is_platform_owner': is_platform_owner(user, db),
        'authenticator_enrolled': proof is not None and proof.last_authenticator_step is not None,
    })

@app.patch('/auth/me', response_model=UserOut)
def update_contact(data: ContactUpdate, user: CurrentUser, db: Db):
    user = db.scalar(select(User).where(User.id == user.id).with_for_update()
                     .execution_options(populate_existing=True))
    if user is None or user.is_suspended:
        raise HTTPException(401, 'Invalid or expired token')
    if data.phone_number != user.phone_number and (user.phone_verified_at is not None or user.is_platform_admin):
        raise HTTPException(409, 'Use verified phone replacement to change this number')
    assign_phone_number(db, user, data.phone_number)
    user.sms_daily_records_enabled = data.sms_daily_records_enabled
    user.sms_loan_reminders_enabled = data.sms_loan_reminders_enabled
    if data.sms_financial_alerts_enabled is not None or not data.phone_number:
        user.sms_financial_alerts_enabled = bool(data.sms_financial_alerts_enabled)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if duplicate_phone_claim(error):
            raise HTTPException(409, 'This phone number is already assigned to an account') from None
        raise
    db.refresh(user)
    return user

@app.post('/farms', response_model=FarmOut, status_code=201)
def create_farm(data: FarmIn, user: CurrentUser, db: Db):
    if user.account_type not in ('farmer', 'legacy'):
        raise HTTPException(403, 'Farmer account required')
    farm = Farm(**data.model_dump(), owner_id=user.id)
    db.add(farm)
    db.flush()
    audit(db, user, 'create', 'farm', farm.id)
    db.commit()
    db.refresh(farm)
    return farm

@app.get('/farms', response_model=list[FarmOut])
def list_farms(user: CurrentUser, db: Db):
    return db.scalars(select(Farm).where(Farm.owner_id == user.id, Farm.archived_at.is_(None)).order_by(Farm.id)).all()

@app.get('/farms/{farm_id}', response_model=FarmOut)
def get_farm(farm_id: int, user: CurrentUser, db: Db):
    return owned_farm(farm_id, user, db)

@app.put('/farms/{farm_id}', response_model=FarmOut)
def update_farm(farm_id: int, data: FarmIn, user: CurrentUser, db: Db):
    farm = owned_farm(farm_id, user, db)
    for key, value in data.model_dump().items():
        setattr(farm, key, value)
    audit(db, user, 'update', 'farm', farm.id)
    db.commit()
    db.refresh(farm)
    return farm

@app.delete('/farms/{farm_id}', status_code=204)
def delete_farm(farm_id: int, user: CurrentUser, db: Db):
    farm = owned_farm(farm_id, user, db)
    farm.archived_at = datetime.now(timezone.utc)
    audit(db, user, 'archive', 'farm', farm.id)
    db.commit()

@app.post('/farms/{farm_id}/units', response_model=UnitOut, status_code=201)
def create_unit(farm_id: int, data: UnitIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit = ProductionUnit(farm_id=farm_id, **data.model_dump())
    db.add(unit)
    db.flush()
    audit(db, user, 'create', 'production_unit', unit.id)
    db.commit()
    db.refresh(unit)
    return unit

@app.get('/farms/{farm_id}/units', response_model=list[UnitOut])
def list_units(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    return db.scalars(select(ProductionUnit).where(ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True)).order_by(ProductionUnit.id)).all()

@app.put('/farms/{farm_id}/units/{unit_id}', response_model=UnitOut)
def update_unit(farm_id: int, unit_id: int, data: UnitIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit).where(ProductionUnit.id == unit_id, ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True)))
    if unit is None:
        raise HTTPException(status_code=404, detail='Production unit not found')
    for key, value in data.model_dump().items():
        setattr(unit, key, value)
    audit(db, user, 'update', 'production_unit', unit.id)
    db.commit()
    db.refresh(unit)
    return unit

@app.delete('/farms/{farm_id}/units/{unit_id}', status_code=204)
def archive_unit(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit).where(ProductionUnit.id == unit_id, ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True)))
    if unit is None:
        raise HTTPException(status_code=404, detail='Production unit not found')
    unit.is_active = False
    audit(db, user, 'archive', 'production_unit', unit.id)
    db.commit()

@app.get('/farms/{farm_id}/audit', response_model=list[AuditOut])
def farm_audit(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit_ids = select(ProductionUnit.id).where(ProductionUnit.farm_id == farm_id)
    return db.scalars(select(AuditLog).where(
        ((AuditLog.entity_type == 'farm') & (AuditLog.entity_id == farm_id)) |
        ((AuditLog.entity_type == 'production_unit') & (AuditLog.entity_id.in_(unit_ids)))
    ).order_by(AuditLog.id)).all()
# Import these modules to register their routers with FastAPI.
from . import operations
# Run `alembic upgrade head` before starting the API. No implicit schema creation.

from . import feeding
from . import forecasting
from . import automated_costing
from . import sales
from . import dashboard
from . import reports
from . import lending
from . import loan_servicing
from . import evidence
from . import daily_reminders

from . import administration
from . import password_recovery
from . import administrator_verification
from . import phone_verification
from . import sms_management
from . import farm_staff

from . import institution_staff
from . import institution_branches
from . import institution_accounting

from . import feeding_sessions

from . import production_alerts
from . import request_diagnostics
from . import farm_expenses
from . import pricing_advisor
from . import farm_report_views

from . import feed_outlook

from . import activity_history

from . import processing


def configure_cors(api: FastAPI, configured: str) -> None:
    origins = []
    for raw in configured.split(','):
        origin = raw.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment or '*' in origin):
            raise RuntimeError('CORS_ALLOWED_ORIGINS must contain exact HTTP(S) origins.')
        origins.append(origin)
    if origins:
        api.add_middleware(CORSMiddleware, allow_origins=origins,
                           allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'],
                           allow_headers=['Authorization', 'Content-Type'],
                           expose_headers=['X-Request-ID', 'Content-Disposition'])


DEPLOYED_FRONTEND_ORIGIN = 'https://aquafarm-ghana-frontend.onrender.com'
LOCAL_VITE_ORIGINS = tuple(
    f'http://{host}:{port}'
    for host in ('localhost', '127.0.0.1')
    for port in (5173, 5174)
)

# Register last so preflights are handled before diagnostics and routing.
allowed_origins = [DEPLOYED_FRONTEND_ORIGIN]
if os.getenv('RENDER', '').lower() != 'true':
    allowed_origins.extend(LOCAL_VITE_ORIGINS)
allowed_origins.append(os.getenv('CORS_ALLOWED_ORIGINS', ''))
configure_cors(app, ','.join(allowed_origins))
