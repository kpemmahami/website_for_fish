"""Platform administrator provisioning and ownership checks."""
import hashlib
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import (
    AdminRegister, Base, User, audit, new_user,
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
