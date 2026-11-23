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
from sqlalchemy import DateTime, ForeignKey, String, Float, Text, Boolean, create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .database import database_url

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
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sms_daily_records_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sms_loan_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    business_type: Literal['farmer','processor','integrated'] = 'farmer'


class AdminRegister(Register):
    password: str = Field(min_length=12, max_length=128)


class Login(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    phone_number: str | None
    sms_daily_records_enabled: bool
    sms_loan_reminders_enabled: bool
    account_type: Literal['legacy', 'farmer', 'institution', 'admin']
    is_platform_admin: bool = False
    is_platform_owner: bool = False

class ContactUpdate(BaseModel):
    phone_number: str | None = Field(default=None, pattern=r'^\+[1-9]\d{7,14}$')
    sms_daily_records_enabled: bool = False
    sms_loan_reminders_enabled: bool = False

    @model_validator(mode='after')
    def enabled_requires_phone(self):
        if (self.sms_daily_records_enabled or self.sms_loan_reminders_enabled) and not self.phone_number:
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

def current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)], db: Db) -> User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=['HS256'])
        user_id = int(payload['sub'])
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail='Invalid or expired token', headers={'WWW-Authenticate': 'Bearer'})
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='User no longer exists')
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


FARMER_REGISTRATION_PATHS = {'/auth/register', '/auth/farmer/register'}
registration_log = logging.getLogger('aquafarm.registration')


@app.exception_handler(RequestValidationError)
async def safe_registration_validation(request: Request, error: RequestValidationError):
    if request.method == 'POST' and request.url.path in FARMER_REGISTRATION_PATHS:
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
        registration_log.error('Registration readiness check failed. exception=%s sqlstate=%s',
                               type(error).__name__, getattr(getattr(error, 'orig', None), 'sqlstate', None))
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
    user = new_user(data, 'farmer')
    db.add(user)
    try:
        db.flush()
        if data.business_type != 'farmer':
            from .processing import ProcessingBusiness
            db.add(ProcessingBusiness(owner_id=user.id,name=data.full_name,business_type=data.business_type))
        response = UserOut.model_validate(user)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        if isinstance(error, IntegrityError) and duplicate_email(error):
            raise HTTPException(status_code=409, detail='Email already registered') from None
        original = getattr(error, 'orig', None)
        registration_log.error('Farmer registration failed. exception=%s sqlstate=%s',
                               type(error).__name__, getattr(original, 'sqlstate', None))
        raise HTTPException(status_code=503, detail='Registration is temporarily unavailable') from None
    return response


def login_account(data: Login, db: Session, account_types: tuple[str, ...]) -> Token:
    from .development import DEVELOPMENT_ACCOUNTS, enabled, seeded_account

    identifier = data.email.lower()
    email = DEVELOPMENT_ACCOUNTS.get(identifier, identifier) if enabled(DATABASE_URL) else identifier
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and email in DEVELOPMENT_ACCOUNTS.values():
        if seeded_account(db, user.id) and not enabled(DATABASE_URL):
            raise HTTPException(status_code=401, detail='Invalid credentials')
        if identifier in DEVELOPMENT_ACCOUNTS and not seeded_account(db, user.id):
            raise HTTPException(status_code=401, detail='Invalid credentials')
    if user is None or user.account_type not in account_types or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)}, SECRET_KEY, algorithm='HS256')
    return Token(access_token=token)


@app.post('/auth/login', response_model=Token)
@app.post('/auth/farmer/login', response_model=Token)
def login(data: Login, db: Db):
    return login_account(data, db, ('farmer', 'legacy'))


@app.post('/auth/institution/login', response_model=Token)
def institution_login(data: Login, db: Db):
    return login_account(data, db, ('institution', 'legacy'))


@app.post('/auth/admin/login', response_model=Token)
def admin_login(data: Login, db: Db):
    return login_account(data, db, ('admin',))


def require_platform_admin(user: User):
    if not user.is_platform_admin:
        raise HTTPException(403, 'Platform administrator access required')


@app.get('/auth/me', response_model=UserOut)
def me(user: CurrentUser, db: Db):
    from .administration import is_platform_owner

    return UserOut.model_validate(user).model_copy(update={
        'is_platform_owner': is_platform_owner(user, db),
    })

@app.patch('/auth/me', response_model=UserOut)
def update_contact(data: ContactUpdate, user: CurrentUser, db: Db):
    user.phone_number = data.phone_number
    user.sms_daily_records_enabled = data.sms_daily_records_enabled
    user.sms_loan_reminders_enabled = data.sms_loan_reminders_enabled
    db.commit()
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

from . import institution_staff

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


configure_cors(app, os.getenv('CORS_ALLOWED_ORIGINS', ''))
