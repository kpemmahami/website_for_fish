"""Platform administrator provisioning and ownership checks."""
import json
import secrets
from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints
from sqlalchemy import DateTime, ForeignKey, String, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import (
    AdminRegister, AuditLog, Base, CurrentUser, Db, User, app, assign_phone_number, audit,
    duplicate_phone_claim, new_user, require_platform_admin,
)
from .phone_numbers import PhoneNumber, normalize_phone_number


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
    phone = normalize_phone_number(phone_number)
    if phone is None:
        raise ValueError('Enter a Ghanaian or international mobile phone number')
    user = new_user(data, 'admin')
    try:
        assign_phone_number(db, user, phone)
    except HTTPException as error:
        raise ValueError(error.detail) from None
    db.add(user)
    try:
        db.flush()
        db.add(AdminSetup(id=1, admin_user_id=user.id))
        audit(db, user, 'bootstrap', 'platform_admin', user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if duplicate_phone_claim(exc):
            raise ValueError('This phone number is already assigned to an account') from None
        raise ValueError('Setup already completed or email already registered') from exc


def is_platform_owner(user: User, db: Session) -> bool:
    setup = db.get(AdminSetup, 1)
    return user.is_platform_admin and setup is not None and setup.admin_user_id == user.id


def require_platform_owner(user: User, db: Session) -> None:
    if not is_platform_owner(user, db):
        raise HTTPException(403, 'Platform owner access required')


@app.get('/admin/farmers/pending', tags=['Platform administration'])
def pending_farmers(user: CurrentUser, db: Db, offset: int = Query(0, ge=0),
                    search: str = Query('', max_length=255)):
    require_platform_admin(user)
    query = select(User.id, User.full_name, User.email, User.phone_number, User.created_at).where(
        User.account_type == 'pending_farmer',
    )
    if term := search.strip().lower():
        query = query.where(or_(func.lower(User.full_name).contains(term, autoescape=True),
                                func.lower(User.email).contains(term, autoescape=True),
                                User.phone_number.contains(term, autoescape=True)))
    rows = db.execute(query.order_by(User.created_at, User.id).offset(offset).limit(51))
    items = [dict(row._mapping) for row in rows]
    return {'items': items[:50], 'has_more': len(items) > 50}


@app.get('/admin/farmers/approved', tags=['Platform administration'])
def approved_farmers(user: CurrentUser, db: Db, offset: int = Query(0, ge=0)):
    require_platform_admin(user)
    rows = db.execute(select(User.id, User.full_name, User.email, User.phone_number, User.created_at)
                      .where(User.account_type == 'farmer')
                      .order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(51)).all()
    return {'items': [dict(row._mapping) for row in rows[:50]], 'has_more': len(rows) > 50}


@app.post('/admin/farmers/{farmer_id}/approve', tags=['Platform administration'])
def approve_farmer(farmer_id: int, user: CurrentUser, db: Db):
    require_platform_admin(user)
    result = db.execute(update(User).where(User.id == farmer_id, User.account_type == 'pending_farmer')
                        .values(account_type='farmer'))
    if result.rowcount != 1:
        raise HTTPException(404, 'Pending farmer account not found')
    audit(db, user, 'approve', 'farmer_account', farmer_id)
    db.commit()
    return {'message': 'Farmer account approved.'}


@app.get('/admin/administrators', tags=['Platform administration'])
def list_administrators(
    user: CurrentUser, db: Db, search: str = Query('', max_length=255),
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    pending_only: bool = False,
):
    from .administrator_verification import AdministratorContactProof

    require_platform_owner(user, db)
    filters = [User.account_type == 'pending_admin' if pending_only else User.account_type.in_(('admin', 'pending_admin'))]
    if search.strip():
        term = search.strip().lower()
        filters.append(or_(
            func.lower(User.full_name).contains(term, autoescape=True),
            func.lower(User.email).contains(term, autoescape=True),
        ))
    total = db.scalar(select(func.count(User.id)).where(*filters))
    rows = db.execute(select(
        User.id, User.full_name, User.email, User.phone_number, User.created_at, User.is_suspended,
        User.account_type, AdministratorContactProof.verified_at.label('contacts_verified_at'),
    ).outerjoin(AdministratorContactProof, AdministratorContactProof.user_id == User.id)
      .where(*filters).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit))
    return {
        'total': total,
        'items': [
            {**row._mapping, 'role': 'Platform Owner' if row.id == user.id else 'Super Admin',
             'pending_activation': row.account_type == 'pending_admin'}
            for row in rows
        ],
    }


class PendingAdministratorIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    email: EmailStr
    phone_number: PhoneNumber


@app.get('/admin/administrators/{administrator_id}/activity', tags=['Platform administration'])
def administrator_activity(administrator_id: int, user: CurrentUser, db: Db, offset: int = Query(0, ge=0)):
    require_platform_owner(user, db)
    account = db.get(User, administrator_id)
    if account is None or account.account_type not in ('admin', 'pending_admin'):
        raise HTTPException(404, 'Administrator not found')
    rows = db.execute(select(AuditLog, User.full_name).join(User, User.id == AuditLog.actor_id).where(
        AuditLog.entity_type == 'platform_admin', AuditLog.entity_id == administrator_id,
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(26)).all()
    items = []
    for event, actor_name in rows[:25]:
        reason = None
        if event.action in ('suspend', 'reactivate', 'revoke_sessions'):
            try:
                details = json.loads(event.details)
            except (ValueError, TypeError):
                details = None
            if isinstance(details, dict) and isinstance(details.get('reason'), str):
                reason = details['reason']
        items.append({'id': event.id, 'actor_name': actor_name, 'action': event.action,
                      'reason': reason, 'created_at': event.created_at})
    return {'items': items, 'has_more': len(rows) > 25}


@app.post('/admin/administrators', status_code=201, tags=['Platform administration'])
def prepare_administrator(data: PendingAdministratorIn, user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    phone = data.phone_number
    db.scalar(select(AdminSetup.id).where(AdminSetup.id == 1).with_for_update())
    account = new_user(AdminRegister(
        full_name=data.full_name, email=data.email, password=secrets.token_urlsafe(32),
    ), 'pending_admin')
    assign_phone_number(db, account, phone)
    db.add(account)
    try:
        db.flush()
        audit(db, user, 'prepare_administrator', 'platform_admin', account.id)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if duplicate_phone_claim(error):
            raise HTTPException(409, 'This phone number is already assigned to an account') from None
        raise HTTPException(409, 'An account with this email already exists') from None
    return {'id': account.id, 'pending_activation': True}


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
