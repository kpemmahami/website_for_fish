"""Institution-scoped staff provisioning and membership lifecycle."""

from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .lending import InstitutionMember, member
from .main import AuditLog, Base, CurrentUser, Db, Register, User, app, assign_phone_number, audit, duplicate_phone_claim, new_user
from .phone_numbers import PhoneNumber

StaffRole = Literal['loan_officer', 'credit_manager', 'disbursement', 'collections', 'viewer', 'officer', 'reviewer']
TAG = ['Institution staff']
ROOT = '/finance/institutions/{institution_id}/staff'


class StaffInvitation(Base):
    __tablename__ = 'institution_staff_invitations'
    __table_args__ = (UniqueConstraint('institution_id', 'email', name='uq_staff_invite_institution_email'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str | None] = mapped_column(String(16))
    department: Mapped[str | None] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreateStaffIn(Register):
    phone_number: PhoneNumber
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    role: StaffRole


class MembershipUpdate(BaseModel):
    role: StaffRole | None = None
    status: Literal['active', 'suspended', 'removed'] | None = None


def membership_for(db, institution_id, user_id):
    return db.scalar(select(InstitutionMember).where(
        InstitutionMember.institution_id == institution_id, InstitutionMember.user_id == user_id,
    ))


def staff_change(db, actor, action, institution_id, details):
    import json

    audit(db, actor, action, 'institution_staff', institution_id, json.dumps(details))


@app.get(ROOT, tags=TAG)
def list_staff(institution_id: int, user: CurrentUser, db: Db):
    institution = member(db, institution_id, user.id, 'manage_staff')
    staff = db.execute(select(InstitutionMember, User).join(User, User.id == InstitutionMember.user_id).where(
        InstitutionMember.institution_id == institution.id,
    ).order_by(User.full_name, User.id))
    activity = db.scalars(select(AuditLog).where(
        AuditLog.entity_type == 'institution_staff', AuditLog.entity_id == institution.id,
    ).order_by(AuditLog.id.desc()).limit(100))
    return {
        'staff': [{'user_id': person.id, 'full_name': person.full_name, 'email': person.email,
                   'phone_number': person.phone_number, 'role': row.role, 'status': row.status, 'branch_id': row.branch_id,
                   'department': row.department, 'job_title': row.job_title, 'created_at': row.created_at}
                  for row, person in staff],
        'activity': [{'actor_id': row.actor_id, 'action': row.action, 'details': row.details,
                      'created_at': row.created_at} for row in activity],
    }


@app.post(ROOT, status_code=201, tags=TAG)
def create_staff(institution_id: int, data: CreateStaffIn, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    staff_user = new_user(data, 'institution')
    staff_user.initial_password_required = True
    assign_phone_number(db, staff_user, data.phone_number)
    db.add(staff_user)
    try:
        db.flush()
        db.add(InstitutionMember(
            institution_id=institution_id, user_id=staff_user.id, role=data.role,
            department=data.department, job_title=data.job_title,
        ))
        staff_change(db, user, 'create_staff', institution_id, {
            'user_id': staff_user.id, 'role': data.role,
        })
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if duplicate_phone_claim(error):
            raise HTTPException(409, 'This phone number is already assigned to an account') from None
        raise HTTPException(409, 'An account with this email already exists') from None
    return {'user_id': staff_user.id, 'role': data.role, 'status': 'active'}


@app.patch(ROOT + '/{staff_user_id}', tags=TAG)
def update_staff(institution_id: int, staff_user_id: int, data: MembershipUpdate, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    row = membership_for(db, institution_id, staff_user_id)
    if row is None:
        raise HTTPException(404, 'Staff member not found')
    if row.role == 'owner' or staff_user_id == user.id:
        raise HTTPException(403, 'Institution owner access is protected')
    before = {'role': row.role, 'status': row.status}
    after = data.model_dump(exclude_none=True)
    if not after:
        raise HTTPException(422, 'Choose a role or status change')
    result = db.execute(update(InstitutionMember).where(
        InstitutionMember.id == row.id, InstitutionMember.role == before['role'],
        InstitutionMember.status == before['status'],
    ).values(**after))
    if result.rowcount != 1:
        raise HTTPException(409, 'Staff access changed. Refresh and try again.')
    staff_change(db, user, 'update_staff_access', institution_id, {'user_id': staff_user_id, 'before': before, 'after': after})
    db.commit()
    return {'user_id': staff_user_id, 'role': row.role, 'status': row.status}
