"""Farm-scoped activity cards derived from existing production records."""

from datetime import datetime, timedelta, timezone
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from .feeding import FeedingRecommendation
from .feeding_sessions import daily_summary
from .main import AuditLog, CurrentUser, Db, ProductionUnit, app, audit, owned_farm
from .operations import StockingCycle, FishSample, WaterQuality, owned_unit


class ReadinessIn(BaseModel):
    status: Literal['ready', 'cleaning', 'drying', 'maintenance', 'repair', 'preparation', 'temporarily_closed']
    reason: str = Field(min_length=1, max_length=500)


def unit_readiness(db, unit_ids):
    changes = db.scalars(select(AuditLog).where(
        AuditLog.entity_type == 'production_unit', AuditLog.action == 'change_stocking_readiness',
        AuditLog.entity_id.in_(unit_ids),
    ).order_by(AuditLog.id.desc()))
    result = {}
    for change in changes:
        result.setdefault(change.entity_id, json.loads(change.details))
    return result


@app.put('/farms/{farm_id}/units/{unit_id}/stocking-readiness', tags=['Aquaculture operations'])
def update_readiness(farm_id: int, unit_id: int, data: ReadinessIn, user: CurrentUser, db: Db):
    owned_unit(farm_id, unit_id, user, db)
    if not data.reason.strip():
        raise HTTPException(422, 'A readiness change requires a reason')
    previous = unit_readiness(db, [unit_id]).get(unit_id, {}).get('status', 'ready')
    info = {'status': data.status, 'previous_status': previous, 'reason': data.reason.strip()}
    audit(db, user, 'change_stocking_readiness', 'production_unit', unit_id, json.dumps(info))
    db.commit()
    return info


def farm_activity(db, farm_id, now):
    today = now.date()
    units = db.scalars(select(ProductionUnit).where(
        ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True),
    ).order_by(ProductionUnit.name, ProductionUnit.id)).all()
    by_unit = {unit.id: unit for unit in units}
    cycles = db.scalars(select(StockingCycle).where(StockingCycle.unit_id.in_(by_unit))).all()
    active = [cycle for cycle in cycles if cycle.closed_at is None]
    occupied = {cycle.unit_id for cycle in active}
    historical = {cycle.unit_id for cycle in cycles if cycle.closed_at is not None}
    readiness = unit_readiness(db, by_unit)
    open_units = [
        {'unit_id': unit.id, 'unit_name': unit.name, 'status': readiness.get(unit.id, {}).get('status', 'ready'),
         'reason': readiness.get(unit.id, {}).get('reason'), 'restocking': unit.id in historical}
        for unit in units if unit.id not in occupied
    ]
    attention, upcoming, suspended = [], [], []
    recorded = sampling_overdue = water_overdue = harvest_due = harvest_approaching = 0
    for cycle in active:
        summary = daily_summary(db, cycle, today, now)
        recorded += summary['recorded_count']
        advisory = db.scalar(select(FeedingRecommendation).where(
            FeedingRecommendation.cycle_id == cycle.id,
        ).order_by(FeedingRecommendation.created_at.desc(), FeedingRecommendation.id.desc()).limit(1))
        context = {'cycle_id': cycle.id, 'unit_id': cycle.unit_id, 'unit_name': by_unit[cycle.unit_id].name,
                   'species': cycle.species, 'date': today}
        if advisory and advisory.status == 'suspended':
            suspended.append({**context, 'warnings': json.loads(advisory.warnings_json)})
        if summary['schedule_id'] or not (advisory and advisory.status == 'suspended'):
            for session in summary['sessions']:
                item = {**context, **session, 'recommended_feed_id': summary['recommended_feed_id']}
                if session['status'] in ('due', 'missed'):
                    attention.append(item)
                elif session['status'] == 'upcoming' and session['scheduled_time']:
                    upcoming.append(item)
        latest_sample = db.scalar(select(func.max(FishSample.sampled_on)).where(FishSample.cycle_id == cycle.id))
        sampling_overdue += (today - (latest_sample or cycle.stocked_on)).days >= 7
        latest_water = db.scalar(select(func.max(WaterQuality.observed_at)).where(WaterQuality.unit_id == cycle.unit_id))
        water_overdue += now.hour >= 8 and cycle.stocked_on < today and (latest_water is None or latest_water.date() < today)
        days_remaining = (cycle.expected_harvest_on - today).days if cycle.expected_harvest_on else None
        harvest_due += days_remaining is not None and days_remaining <= 0
        harvest_approaching += days_remaining is not None and 0 < days_remaining <= 30
    attention.sort(key=lambda row: (row['status'] != 'missed', row['deadline'], row['cycle_id'], row['number']))
    upcoming.sort(key=lambda row: row['scheduled_time'])
    return {
        'date': today, 'unit_count': len(units), 'unstocked_units': open_units,
        'stocking_required': [row for row in open_units if row['status'] == 'ready'],
        'feeding_attention': attention, 'feeding_suspended': suspended,
        'feeding_recorded': recorded, 'next_feeding': upcoming[0] if upcoming else None,
        'sampling_overdue': sampling_overdue, 'water_overdue': water_overdue,
        'harvest_due': harvest_due, 'harvest_approaching': harvest_approaching,
    }


@app.get('/farms/{farm_id}/production-activity', tags=['Aquaculture operations'])
def production_activity(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    return farm_activity(db, farm_id, datetime.now(timezone.utc))
