"""Owner-managed branch directory for verified financial institutions."""

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .lending import InstitutionMember, LoanApplication, member
from .main import Base, CurrentUser, Db, app, audit

ROOT = '/finance/institutions/{institution_id}/branches'
TAG = ['Institution branches']


class InstitutionBranch(Base):
    __tablename__ = 'institution_branches'
    __table_args__ = (UniqueConstraint('institution_id', 'code', name='uq_institution_branch_code'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    code: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(260))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BranchDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=260)]


class BranchCreate(BranchDetails):
    code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                           min_length=2, max_length=24, pattern=r'^[A-Za-z0-9-]+$')]


class BranchEdit(BranchDetails):
    active: bool


def branch_view(branch: InstitutionBranch):
    return {key: getattr(branch, key) for key in ('id', 'code', 'name', 'address', 'active')}


@app.get(ROOT, tags=TAG)
def list_branches(institution_id: int, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    rows = db.scalars(select(InstitutionBranch).where(
        InstitutionBranch.institution_id == institution_id,
    ).order_by(InstitutionBranch.name, InstitutionBranch.id))
    return [branch_view(branch) for branch in rows]


@app.post(ROOT, status_code=201, tags=TAG)
def create_branch(institution_id: int, data: BranchCreate, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    branch = InstitutionBranch(institution_id=institution_id, **data.model_dump(),
                               created_at=datetime.now(timezone.utc))
    db.add(branch)
    try:
        db.flush()
        audit(db, user, 'create', 'institution_branch', branch.id,
              json.dumps({'institution_id': institution_id, 'branch': branch_view(branch)}))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'That branch code is already in use') from None
    return branch_view(branch)


@app.patch(ROOT + '/{branch_id}', tags=TAG)
def edit_branch(institution_id: int, branch_id: int, data: BranchEdit, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    branch = db.scalar(select(InstitutionBranch).where(
        InstitutionBranch.institution_id == institution_id, InstitutionBranch.id == branch_id,
    ).with_for_update())
    if branch is None:
        raise HTTPException(404, 'Branch not found')
    previous = branch_view(branch)
    for field, value in data.model_dump().items():
        setattr(branch, field, value)
    audit(db, user, 'update', 'institution_branch', branch.id,
          json.dumps({'institution_id': institution_id, 'previous': previous, 'branch': branch_view(branch)}))
    db.commit()
    return branch_view(branch)


class BranchAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    branch_id: int | None = Field(gt=0)


def validate_branch(db, institution_id, branch_id):
    if branch_id is None:
        return
    branch = db.scalar(select(InstitutionBranch).where(
        InstitutionBranch.id == branch_id, InstitutionBranch.institution_id == institution_id,
        InstitutionBranch.active.is_(True),
    ))
    if branch is None:
        raise HTTPException(404, 'Active branch not found')


@app.put('/finance/institutions/{institution_id}/staff/{staff_user_id}/branch', tags=TAG)
def assign_staff_branch(institution_id: int, staff_user_id: int, data: BranchAssignment, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    staff = db.scalar(select(InstitutionMember).where(
        InstitutionMember.institution_id == institution_id, InstitutionMember.user_id == staff_user_id,
    ).with_for_update())
    if staff is None:
        raise HTTPException(404, 'Staff member not found')
    if staff.role == 'owner':
        raise HTTPException(403, 'Institution owner access is protected')
    validate_branch(db, institution_id, data.branch_id)
    previous = staff.branch_id
    staff.branch_id = data.branch_id
    audit(db, user, 'assign_staff_branch', 'institution_staff', institution_id,
          json.dumps({'staff_user_id': staff_user_id, 'previous_branch_id': previous, 'branch_id': data.branch_id}))
    db.commit()
    return {'user_id': staff_user_id, 'branch_id': staff.branch_id}


@app.put('/finance/institutions/{institution_id}/applications/{application_id}/branch', tags=TAG)
def assign_application_branch(institution_id: int, application_id: int, data: BranchAssignment,
                              user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    application = db.scalar(select(LoanApplication).where(
        LoanApplication.institution_id == institution_id, LoanApplication.id == application_id,
    ).with_for_update())
    if application is None:
        raise HTTPException(404, 'Application not found')
    validate_branch(db, institution_id, data.branch_id)
    previous = application.branch_id
    application.branch_id = data.branch_id
    audit(db, user, 'assign_application_branch', 'loan_application', application.id,
          json.dumps({'institution_id': institution_id, 'previous_branch_id': previous, 'branch_id': data.branch_id}))
    db.commit()
    return {'id': application.id, 'branch_id': application.branch_id}
