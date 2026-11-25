"""Platform administrator provisioning and ownership checks."""
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import DateTime, ForeignKey, String, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import (
    AdminRegister, Base, CurrentUser, Db, User, app, audit, login_phone_number, new_user,
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


def bootstrap_admin(data: AdminRegister, db: Session, *, phone_number: str) -> None:
    data = AdminRegister.model_validate(data.model_dump())
    if db.get(AdminSetup, 1) is not None:
        raise ValueError('First administrator setup has already been completed')
    phone = login_phone_number(phone_number)
    if phone is None:
        raise ValueError('Enter a Ghanaian or international mobile phone number')
    if db.scalar(select(User.id).where(User.account_type == 'admin', User.phone_number == phone).limit(1)):
        raise ValueError('The number is already assigned to a platform administrator')
    user = new_user(data, 'admin')
    user.phone_number = phone
    db.add(user)
    try:
        db.flush()
        db.add(AdminSetup(id=1, admin_user_id=user.id))
        audit(db, user, 'bootstrap', 'platform_admin', user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError('Setup already completed or email already registered') from exc


def is_platform_owner(user: User, db: Session) -> bool:
    setup = db.get(AdminSetup, 1)
    return user.is_platform_admin and setup is not None and setup.admin_user_id == user.id


def require_platform_owner(user: User, db: Session) -> None:
    if not is_platform_owner(user, db):
        raise HTTPException(403, 'Platform owner access required')


@app.get('/admin/administrators', tags=['Platform administration'])
def list_administrators(
    user: CurrentUser, db: Db, search: str = Query('', max_length=255),
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
):
    require_platform_owner(user, db)
    filters = [User.account_type == 'admin']
    if search.strip():
        term = search.strip().lower()
        filters.append(or_(
            func.lower(User.full_name).contains(term, autoescape=True),
            func.lower(User.email).contains(term, autoescape=True),
        ))
    total = db.scalar(select(func.count(User.id)).where(*filters))
    rows = db.execute(select(
        User.id, User.full_name, User.email, User.phone_number, User.created_at, User.is_suspended,
    ).where(*filters).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit))
    return {
        'total': total,
        'items': [
            {**row._mapping, 'role': 'Platform Owner' if row.id == user.id else 'Super Admin'}
            for row in rows
        ],
    }


class AdministratorAccessChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['suspend', 'reactivate', 'revoke_sessions']
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


@app.post('/admin/administrators/{administrator_id}/access', tags=['Platform administration'])
def change_administrator_access(administrator_id: int, data: AdministratorAccessChange, user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    if administrator_id == user.id:
        raise HTTPException(403, 'Platform Owner access is protected')

    filters = [User.id == administrator_id, User.account_type == 'admin']
    if data.action == 'reactivate':
        filters.append(User.is_suspended.is_(True))
        values = {'is_suspended': False}
    else:
        values = {'session_generation': uuid4().hex, 'recovery_requested_at': None}
        if data.action == 'suspend':
            filters.append(User.is_suspended.is_(False))
            values['is_suspended'] = True

    result = db.execute(update(User).where(*filters).values(**values))
    if result.rowcount != 1:
        if not db.scalar(select(User.id).where(User.id == administrator_id, User.account_type == 'admin')):
            raise HTTPException(404, 'Administrator not found')
        raise HTTPException(409, 'Administrator status already changed. Refresh and try again.')
    audit(db, user, data.action, 'platform_admin', administrator_id, json.dumps({'reason': data.reason}))
    db.commit()
    return {'message': 'Administrator access updated.'}
