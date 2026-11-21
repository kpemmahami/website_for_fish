import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pwdlib import PasswordHash
from sqlalchemy import DateTime, ForeignKey, String, Float, Text, Boolean, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./aquafarm.db')
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError('Set SECRET_KEY to a random string of at least 32 characters.')
TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_MINUTES', '60'))
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    farms: Mapped[list['Farm']] = relationship(back_populates='owner')

class Farm(Base):
    __tablename__ = 'farms'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    region: Mapped[str] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100))
    farm_type: Mapped[str] = mapped_column(String(30))
    species: Mapped[str] = mapped_column(String(100))
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
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class Login(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr

class FarmIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    region: str = Field(min_length=2, max_length=100)
    district: str = Field(min_length=2, max_length=100)
    farm_type: Literal['pond', 'cage', 'tank', 'mixed']
    species: str = Field(min_length=2, max_length=100)
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

app = FastAPI(title='AquaFarm Manager Ghana API', version='0.1.0')

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.post('/auth/register', response_model=UserOut, status_code=201)
def register(data: Register, db: Db):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail='Email already registered')
    user = User(full_name=data.full_name, email=email, password_hash=password_hash.hash(data.password))
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail='Unable to register this email')
    db.refresh(user)
    return user

@app.post('/auth/login', response_model=Token)
def login(data: Login, db: Db):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user is None or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    token = jwt.encode({'sub': str(user.id), 'exp': datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)}, SECRET_KEY, algorithm='HS256')
    return Token(access_token=token)

@app.get('/auth/me', response_model=UserOut)
def me(user: CurrentUser):
    return user

@app.post('/farms', response_model=FarmOut, status_code=201)
def create_farm(data: FarmIn, user: CurrentUser, db: Db):
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

# Run `alembic upgrade head` before starting the API. No implicit schema creation.


# Register Phase One aquaculture operations and include their models in Alembic metadata.
from . import operations  # noqa: E402,F401
