"""Owner-managed read access to assigned active production units."""
import json

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import Boolean, ForeignKey, Index, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .main import Base, CurrentUser, Db, Farm, ProductionUnit, User, app, audit, owned_farm


class FarmStaffUnitAccess(Base):
    __tablename__ = 'farm_staff_unit_access'
    __table_args__ = (Index('ix_farm_staff_unit_access_user_id', 'user_id'),)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean)


class UnitAccessGrant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr


@app.get('/farms/{farm_id}/staff-unit-access')
def list_staff_unit_access(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    rows = db.execute(select(
        FarmStaffUnitAccess.user_id, FarmStaffUnitAccess.unit_id, FarmStaffUnitAccess.is_active,
        User.full_name, User.email, ProductionUnit.name.label('unit_name'),
    ).join(User, User.id == FarmStaffUnitAccess.user_id)
     .join(ProductionUnit, ProductionUnit.id == FarmStaffUnitAccess.unit_id)
     .where(ProductionUnit.farm_id == farm_id)
     .order_by(User.full_name, ProductionUnit.name, ProductionUnit.id))
    return [dict(row._mapping) for row in rows]


@app.post('/farms/{farm_id}/units/{unit_id}/staff-access', status_code=201)
def grant_unit_access(farm_id: int, unit_id: int, data: UnitAccessGrant, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit.id).where(
        ProductionUnit.id == unit_id, ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True),
    ))
    if unit is None:
        raise HTTPException(404, 'Production unit not found')
    target = db.scalar(select(User).where(
        User.email == str(data.email).lower(), User.account_type.in_(('farmer', 'legacy')),
        User.is_suspended.is_(False),
    ))
    if target is None or target.id == user.id:
        raise HTTPException(404, 'Eligible staff account not found')
    access = db.get(FarmStaffUnitAccess, (unit_id, target.id))
    if access and access.is_active:
        raise HTTPException(409, 'This user already has access to the unit')
    if access is None:
        db.add(FarmStaffUnitAccess(unit_id=unit_id, user_id=target.id, is_active=True))
    else:
        access.is_active = True
    audit(db, user, 'grant_unit_view', 'farm_staff', farm_id,
          json.dumps({'unit_id': unit_id, 'user_id': target.id}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'The unit assignment changed. Refresh and try again.') from None
    return {'user_id': target.id, 'unit_id': unit_id}


@app.delete('/farms/{farm_id}/units/{unit_id}/staff-access/{staff_user_id}', status_code=204)
def revoke_unit_access(farm_id: int, unit_id: int, staff_user_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    access = db.scalar(select(FarmStaffUnitAccess).join(ProductionUnit).where(
        ProductionUnit.farm_id == farm_id, FarmStaffUnitAccess.unit_id == unit_id,
        FarmStaffUnitAccess.user_id == staff_user_id, FarmStaffUnitAccess.is_active.is_(True),
    ).with_for_update())
    if access is None:
        raise HTTPException(404, 'Active unit assignment not found')
    access.is_active = False
    audit(db, user, 'revoke_unit_view', 'farm_staff', farm_id,
          json.dumps({'unit_id': unit_id, 'user_id': staff_user_id}))
    db.commit()


@app.get('/staff/assigned-units')
def assigned_units(user: CurrentUser, db: Db):
    rows = db.execute(select(
        Farm.id.label('farm_id'), Farm.name.label('farm_name'), ProductionUnit.id.label('unit_id'),
        ProductionUnit.name.label('unit_name'), ProductionUnit.unit_type,
    ).join(ProductionUnit, ProductionUnit.farm_id == Farm.id)
     .join(FarmStaffUnitAccess, FarmStaffUnitAccess.unit_id == ProductionUnit.id)
     .where(FarmStaffUnitAccess.user_id == user.id, FarmStaffUnitAccess.is_active.is_(True),
            Farm.archived_at.is_(None), ProductionUnit.is_active.is_(True))
     .order_by(Farm.name, ProductionUnit.name, ProductionUnit.id))
    return [dict(row._mapping) for row in rows]
