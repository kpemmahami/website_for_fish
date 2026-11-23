"""Platform administrator provisioning and invitation redemption."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import DateTime, ForeignKey, String, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import (
    AdminRegister, Base, CurrentUser, Db, User, UserOut, app, audit, new_user,
)


class AdminSetup(Base):
    __tablename__ = 'platform_admin_setup'
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))


class AdminInvitation(Base):
    __tablename__ = 'platform_admin_invitations'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    invited_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InviteIn(BaseModel):
    email: EmailStr


class AcceptInvitation(AdminRegister):
    invitation_token: str = Field(min_length=43, max_length=43)


def bootstrap_admin(data: AdminRegister, db: Session) -> None:
    data = AdminRegister.model_validate(data.model_dump())
    if db.get(AdminSetup, 1) is not None:
        raise ValueError('First administrator setup has already been completed')
    user = new_user(data, 'admin')
    db.add(user)
    try:
        db.flush()
        db.add(AdminSetup(id=1, admin_user_id=user.id))
        audit(db, user, 'bootstrap', 'platform_admin', user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError('Setup already completed or email already registered') from exc


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_platform_owner(user: User, db: Session) -> bool:
    setup = db.get(AdminSetup, 1)
    return user.is_platform_admin and setup is not None and setup.admin_user_id == user.id


def require_platform_owner(user: User, db: Session) -> None:
    if not is_platform_owner(user, db):
        raise HTTPException(403, 'Platform owner access required')


@app.post('/auth/admin/invitations', status_code=201)
def invite_admin(data: InviteIn, user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(409, 'Use an email without an existing AquaFarm account')
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.add(AdminInvitation(token_hash=token_digest(token), email=email,
                           invited_by=user.id, expires_at=expires_at))
    audit(db, user, 'invite', 'platform_admin', user.id)
    db.commit()
    return {'invitation_token': token, 'expires_at': expires_at}


@app.post('/auth/admin/accept-invitation', response_model=UserOut, status_code=201)
def accept_invitation(data: AcceptInvitation, db: Db):
    digest = token_digest(data.invitation_token)
    email = str(data.email).lower()
    now = datetime.now(timezone.utc)
    consumed = db.execute(update(AdminInvitation).where(
        AdminInvitation.token_hash == digest,
        AdminInvitation.email == email,
        AdminInvitation.expires_at > now,
        AdminInvitation.used_at.is_(None),
    ).values(used_at=now))
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, 'Invalid, expired or used invitation')
    user = new_user(data, 'admin')
    db.add(user)
    try:
        db.flush()
        audit(db, user, 'accept_invitation', 'platform_admin', user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email already registered')
    return user
