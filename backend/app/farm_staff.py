"""Owner-managed read access to assigned active production units."""
import json

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import Boolean, ForeignKey, Index, false, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .main import AuditLog, Base, CurrentUser, Db, Farm, ProductionUnit, User, app, audit, owned_farm
from .feeding import FeedLedger, FeedProduct
from .operations import StockingCycle


class FarmStaffUnitAccess(Base):
    __tablename__ = 'farm_staff_unit_access'
    __table_args__ = (Index('ix_farm_staff_unit_access_user_id', 'user_id'),)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean)
    can_record_feeding: Mapped[bool] = mapped_column(Boolean, server_default=false())


class UnitAccessGrant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    can_record_feeding: bool = False


def feeding_write_scope(farm_id: int, unit_id: int, user: User, db: Db):
    farm = db.scalar(select(Farm).join(ProductionUnit, ProductionUnit.farm_id == Farm.id).where(
        Farm.id == farm_id, Farm.archived_at.is_(None), ProductionUnit.id == unit_id,
        ProductionUnit.is_active.is_(True),
    ))
    if farm is None:
        raise HTTPException(404, 'Production unit not found')
    if farm.owner_id == user.id:
        return farm, False
    assignment = db.scalar(select(FarmStaffUnitAccess).where(
        FarmStaffUnitAccess.unit_id == unit_id, FarmStaffUnitAccess.user_id == user.id,
        FarmStaffUnitAccess.is_active.is_(True), FarmStaffUnitAccess.can_record_feeding.is_(True),
    ).with_for_update())
    if assignment is None:
        raise HTTPException(404, 'Production unit not found')
    return farm, True


@app.get('/farms/{farm_id}/staff-unit-access/activity')
def staff_unit_activity(farm_id: int, user: CurrentUser, db: Db, offset: int = Query(0, ge=0)):
    owned_farm(farm_id, user, db)
    rows = db.execute(select(AuditLog, User.full_name).join(User, User.id == AuditLog.actor_id).where(
        AuditLog.entity_type == 'farm_staff', AuditLog.entity_id == farm_id,
        AuditLog.action.in_(('grant_unit_view', 'revoke_unit_view')),
    ).order_by(AuditLog.id.desc()).offset(offset).limit(26)).all()
    items = []
    for event, actor_name in rows[:25]:
        details = json.loads(event.details)
        items.append({'id': event.id, 'action': event.action, 'created_at': event.created_at,
                      'unit_id': details['unit_id'], 'user_id': details['user_id'], 'actor_name': actor_name})
    return {'items': items, 'has_more': len(rows) > 25}


@app.get('/farms/{farm_id}/staff-unit-access')
def list_staff_unit_access(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    rows = db.execute(select(
        FarmStaffUnitAccess.user_id, FarmStaffUnitAccess.unit_id, FarmStaffUnitAccess.is_active,
        FarmStaffUnitAccess.can_record_feeding,
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
    if access and access.is_active and access.can_record_feeding == data.can_record_feeding:
        raise HTTPException(409, 'This user already has access to the unit')
    if access is None:
        db.add(FarmStaffUnitAccess(
            unit_id=unit_id, user_id=target.id, is_active=True, can_record_feeding=data.can_record_feeding,
        ))
    else:
        access.is_active = True
        access.can_record_feeding = data.can_record_feeding
    audit(db, user, 'grant_unit_view', 'farm_staff', farm_id,
          json.dumps({'unit_id': unit_id, 'user_id': target.id, 'can_record_feeding': data.can_record_feeding}))
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
        FarmStaffUnitAccess.can_record_feeding,
    ).join(ProductionUnit, ProductionUnit.farm_id == Farm.id)
     .join(FarmStaffUnitAccess, FarmStaffUnitAccess.unit_id == ProductionUnit.id)
     .where(FarmStaffUnitAccess.user_id == user.id, FarmStaffUnitAccess.is_active.is_(True),
            Farm.archived_at.is_(None), ProductionUnit.is_active.is_(True))
     .order_by(Farm.name, ProductionUnit.name, ProductionUnit.id))
    return [dict(row._mapping) for row in rows]


@app.get('/staff/assigned-units/{unit_id}/feeding')
def assigned_feeding_history(unit_id: int, user: CurrentUser, db: Db, offset: int = Query(0, ge=0)):
    assignment = select(FarmStaffUnitAccess.unit_id).join(ProductionUnit).join(Farm).where(
        FarmStaffUnitAccess.user_id == user.id, FarmStaffUnitAccess.unit_id == unit_id,
        FarmStaffUnitAccess.is_active.is_(True), ProductionUnit.is_active.is_(True), Farm.archived_at.is_(None),
    )
    if db.scalar(assignment) is None:
        raise HTTPException(404, 'Assigned unit not found')
    rows = db.execute(select(
        FeedLedger.id, FeedLedger.occurred_on, FeedLedger.session_number, StockingCycle.species,
        FeedProduct.name.label('feed_name'), (-FeedLedger.quantity_delta_kg).label('quantity_kg'),
    ).join(StockingCycle, StockingCycle.id == FeedLedger.cycle_id)
     .join(FeedProduct, FeedProduct.id == FeedLedger.feed_id)
     .where(StockingCycle.unit_id.in_(assignment), FeedLedger.event_type == 'feeding')
     .order_by(FeedLedger.occurred_on.desc(), FeedLedger.id.desc()).offset(offset).limit(26)).all()
    return {'items': [dict(row._mapping) for row in rows[:25]], 'has_more': len(rows) > 25}


@app.get('/farms/{farm_id}/units/{unit_id}/staff-feeding-options')
def staff_feeding_options(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    farm, _ = feeding_write_scope(farm_id, unit_id, user, db)
    unit = db.get(ProductionUnit, unit_id)
    cycles = db.execute(select(
        StockingCycle.id, StockingCycle.species, StockingCycle.stocked_on,
    ).where(StockingCycle.unit_id == unit_id, StockingCycle.closed_at.is_(None))
     .order_by(StockingCycle.stocked_on.desc(), StockingCycle.id.desc()))
    products = db.execute(select(FeedProduct.id, FeedProduct.name)
                          .where(FeedProduct.farm_id == farm_id)
                          .order_by(FeedProduct.name, FeedProduct.id))
    return {
        'location_configured': (
            (unit.latitude is not None or farm.latitude is not None)
            and (unit.longitude is not None or farm.longitude is not None)
        ),
        'cycles': [dict(row._mapping) for row in cycles],
        'feeds': [dict(row._mapping) for row in products],
    }
