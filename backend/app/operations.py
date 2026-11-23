"""Phase One aquaculture operations. Import after the foundation's models/routes."""
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Annotated, Literal
import json
from fastapi import HTTPException, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, ForeignKey, Float, Integer, String, Text, UniqueConstraint, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session
from .main import Base, app, Db, CurrentUser, User, Farm, ProductionUnit, AuditLog, owned_farm, audit


def now():
    return datetime.now(timezone.utc)


class StockingCycle(Base):
    __tablename__ = 'stocking_cycles'
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), index=True)
    species: Mapped[str] = mapped_column(String(100))
    stocked_count: Mapped[int] = mapped_column(Integer)
    initial_average_weight_g: Mapped[float] = mapped_column(Float)
    fingerling_supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stocked_on: Mapped[date] = mapped_column(Date)
    harvest_duration_months: Mapped[int | None] = mapped_column(Integer)
    expected_harvest_on: Mapped[date | None] = mapped_column(Date)
    target_harvest_weight_g: Mapped[float | None] = mapped_column(Float)
    expected_survival_pct: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Mortality(Base):
    __tablename__ = 'mortality_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    dead_count: Mapped[int] = mapped_column(Integer)
    observed_on: Mapped[date] = mapped_column(Date)
    cause: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FishSample(Base):
    __tablename__ = 'fish_samples'
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    sampled_on: Mapped[date] = mapped_column(Date)
    weights_g_json: Mapped[str] = mapped_column(Text)
    sample_count: Mapped[int] = mapped_column(Integer)
    average_weight_g: Mapped[float] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WaterQuality(Base):
    __tablename__ = 'water_quality_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    dissolved_oxygen_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    ammonia_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrite_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FishTransfer(Base):
    __tablename__ = 'fish_transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    target_cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    fish_count: Mapped[int] = mapped_column(Integer)
    loss_count: Mapped[int] = mapped_column(Integer, default=0)
    transferred_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FishTreatment(Base):
    __tablename__ = 'fish_treatments'
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'))
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    product: Mapped[str] = mapped_column(String(160))
    dose: Mapped[float] = mapped_column(Float)
    dose_unit: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
    prescriber: Mapped[str | None] = mapped_column(String(160), nullable=True)
    withdrawal_period_days: Mapped[int] = mapped_column(Integer)
    treated_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FarmInspection(Base):
    __tablename__ = 'farm_inspections'
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), index=True)
    inspected_on: Mapped[date] = mapped_column(Date)
    checklist_json: Mapped[str] = mapped_column(Text)
    observations: Mapped[str] = mapped_column(Text)
    issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FarmSupervisor(Base):
    __tablename__ = 'farm_supervisors'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def add_calendar_months(day: date, months: int) -> date:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = month_index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


class HarvestPlanIn(BaseModel):
    harvest_duration_months: int | None = Field(default=None, ge=1, le=120)
    expected_harvest_on: date | None = None
    target_harvest_weight_g: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    expected_survival_pct: float | None = Field(default=None, ge=0, le=100)

    def harvest_date(self, stocked_on: date) -> date | None:
        expected = self.expected_harvest_on
        if expected is None and self.harvest_duration_months is not None:
            try:
                expected = add_calendar_months(stocked_on, self.harvest_duration_months)
            except ValueError as exc:
                raise HTTPException(422, 'Harvest date is out of range') from exc
        if expected is not None and expected <= stocked_on:
            raise HTTPException(422, 'Expected harvest date must be after stocking')
        return expected


class HarvestPlanUpdate(HarvestPlanIn):
    reason: str = Field(min_length=1, max_length=500, pattern=r'\S')


class CycleIn(HarvestPlanIn):
    species: str = Field(min_length=2, max_length=100)
    stocked_count: int = Field(gt=0)
    initial_average_weight_g: float = Field(gt=0)
    fingerling_supplier: str | None = Field(default=None, max_length=200)
    stocked_on: date
    notes: str | None = Field(default=None, max_length=2000)


class CycleOut(CycleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit_id: int
    closed_at: datetime | None
    created_at: datetime


class MortalityIn(BaseModel):
    dead_count: int = Field(ge=0)
    observed_on: date
    cause: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class MortalityOut(MortalityIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_id: int
    created_at: datetime


class SampleIn(BaseModel):
    sampled_on: date
    weights_g: list[float] = Field(min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def valid_weights(self):
        import math
        if any(not math.isfinite(w) or w <= 0 for w in self.weights_g):
            raise ValueError('Each fish weight must be a positive finite number')
        return self


class SampleOut(BaseModel):
    id: int
    cycle_id: int
    sampled_on: date
    weights_g: list[float]
    sample_count: int
    average_weight_g: float
    notes: str | None
    created_at: datetime


def sample_out(s: FishSample):
    return SampleOut(id=s.id, cycle_id=s.cycle_id, sampled_on=s.sampled_on,
                     weights_g=json.loads(s.weights_g_json), sample_count=s.sample_count,
                     average_weight_g=s.average_weight_g, notes=s.notes, created_at=s.created_at)


class WaterIn(BaseModel):
    observed_at: datetime
    temperature_c: float | None = Field(default=None, ge=-5, le=60)
    dissolved_oxygen_mg_l: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    ammonia_mg_l: float | None = Field(default=None, ge=0)
    nitrite_mg_l: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def has_measurement(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError('observed_at must include a timezone offset (e.g. Z)')
        if all(getattr(self, key) is None for key in ('temperature_c', 'dissolved_oxygen_mg_l', 'ph', 'ammonia_mg_l', 'nitrite_mg_l')):
            raise ValueError('Provide at least one water-quality measurement')
        return self


class WaterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit_id: int
    observed_at: datetime
    temperature_c: float | None
    dissolved_oxygen_mg_l: float | None
    ph: float | None
    ammonia_mg_l: float | None
    nitrite_mg_l: float | None
    notes: str | None
    created_at: datetime


class PopulationOut(BaseModel):
    cycle_id: int
    stocked_count: int
    total_mortality: int
    total_harvested: int
    transfer_in_count: int
    transfer_out_count: int
    transfer_loss_count: int
    estimated_live_count: int
    estimated_survival_pct: float
    latest_average_weight_g: float
    estimated_biomass_kg: float
    latest_sampled_on: date | None


def owned_unit(farm_id: int, unit_id: int, user: User, db: Session):
    owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit).where(ProductionUnit.id == unit_id,
                ProductionUnit.farm_id == farm_id, ProductionUnit.is_active.is_(True)))
    if unit is None:
        raise HTTPException(404, 'Production unit not found')
    return unit


def owned_cycle(farm_id: int, unit_id: int, cycle_id: int, user: User, db: Session):
    owned_unit(farm_id, unit_id, user, db)
    cycle = db.scalar(select(StockingCycle).where(StockingCycle.id == cycle_id, StockingCycle.unit_id == unit_id))
    if cycle is None:
        raise HTTPException(404, 'Stocking cycle not found')
    return cycle


def population(cycle: StockingCycle, db: Session):
    dead = db.scalar(select(func.coalesce(func.sum(Mortality.dead_count), 0)).where(Mortality.cycle_id == cycle.id)) or 0
    transfer_in = db.scalar(select(func.coalesce(func.sum(FishTransfer.fish_count), 0)).where(FishTransfer.target_cycle_id == cycle.id)) or 0
    transfer_out = db.scalar(select(func.coalesce(func.sum(FishTransfer.fish_count), 0)).where(FishTransfer.source_cycle_id == cycle.id)) or 0
    transfer_losses = db.scalar(select(func.coalesce(func.sum(FishTransfer.loss_count), 0)).where(FishTransfer.source_cycle_id == cycle.id)) or 0
    from .sales import HarvestLot
    harvested = db.scalar(select(func.coalesce(func.sum(HarvestLot.fish_count), 0)).where(HarvestLot.cycle_id == cycle.id)) or 0
    latest = db.scalar(select(FishSample).where(FishSample.cycle_id == cycle.id).order_by(FishSample.sampled_on.desc(), FishSample.id.desc()))
    live = cycle.stocked_count + transfer_in - transfer_out - dead - transfer_losses - harvested
    weight = latest.average_weight_g if latest else cycle.initial_average_weight_g
    return PopulationOut(cycle_id=cycle.id, stocked_count=cycle.stocked_count,
                         total_mortality=dead, total_harvested=harvested,
                         transfer_in_count=transfer_in, transfer_out_count=transfer_out,
                         transfer_loss_count=transfer_losses,
                         estimated_live_count=live,
                         estimated_survival_pct=round(
                             100 * max(0, cycle.stocked_count + transfer_in - dead - transfer_losses)
                             / (cycle.stocked_count + transfer_in), 2
                         ) if cycle.stocked_count + transfer_in else 0,
                         latest_average_weight_g=weight,
                         estimated_biomass_kg=round(live * weight / 1000, 4),
                         latest_sampled_on=latest.sampled_on if latest else None)


@app.get('/harvest-schedule', tags=['Aquaculture operations'])
def harvest_schedule(user: CurrentUser, db: Db, warning_days: int = Query(default=30, ge=0, le=365)):
    from .sales import HarvestLot

    actuals = select(
        HarvestLot.cycle_id.label('cycle_id'),
        func.max(HarvestLot.harvested_on).label('last_harvest_on'),
        func.sum(HarvestLot.quantity_kg).label('harvested_kg'),
    ).group_by(HarvestLot.cycle_id).subquery()
    cycles = db.execute(
        select(StockingCycle, ProductionUnit, Farm, actuals.c.last_harvest_on, actuals.c.harvested_kg)
        .join(ProductionUnit, ProductionUnit.id == StockingCycle.unit_id)
        .join(Farm, Farm.id == ProductionUnit.farm_id)
        .outerjoin(actuals, actuals.c.cycle_id == StockingCycle.id)
        .where(Farm.owner_id == user.id, Farm.archived_at.is_(None))
        .order_by(StockingCycle.expected_harvest_on.asc().nulls_last(), StockingCycle.id)
    )
    today = date.today()
    result = []
    for cycle, unit, farm, last_harvest, harvested_kg in cycles:
        expected = cycle.expected_harvest_on
        days_remaining = (expected - today).days if expected else None
        if cycle.closed_at is not None:
            status = 'Completed'
        elif last_harvest is not None:
            status = 'Partially harvested'
        elif days_remaining is None:
            status = 'Not scheduled'
        elif days_remaining < 0:
            status = 'Harvest overdue'
        elif days_remaining == 0:
            status = 'Harvest due'
        elif days_remaining <= warning_days:
            status = 'Harvest approaching'
        else:
            status = 'Growing'
        projected_count = None
        if expected and cycle.closed_at is None:
            counts = population(cycle, db)
            projected_count = max(0, counts.estimated_live_count)
            if cycle.expected_survival_pct is not None:
                assumed_total = int(cycle.stocked_count * cycle.expected_survival_pct / 100)
                projected_count = min(projected_count, max(0, assumed_total - counts.total_harvested))
        result.append({
            'cycle_id': cycle.id, 'farm_id': farm.id, 'farm_name': farm.name,
            'unit_id': unit.id, 'unit_name': unit.name, 'species': cycle.species,
            'stocked_on': cycle.stocked_on, 'expected_harvest_on': expected,
            'days_remaining': days_remaining, 'status': status,
            'target_harvest_weight_g': cycle.target_harvest_weight_g,
            'expected_survival_pct': cycle.expected_survival_pct,
            'estimated_harvest_count': projected_count,
            'estimated_harvest_kg': round(projected_count * cycle.target_harvest_weight_g / 1000, 4)
            if projected_count is not None and cycle.target_harvest_weight_g is not None else None,
            'last_harvest_on': last_harvest, 'actual_harvest_kg': harvested_kg,
        })
    return result


@app.post('/farms/{farm_id}/units/{unit_id}/cycles', response_model=CycleOut, status_code=201, tags=['Aquaculture operations'])
def create_cycle(
    farm_id: int,
    unit_id: int,
    data: CycleIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    owned_unit(farm_id, unit_id, user, db)
    from .production_alerts import unit_readiness

    if unit_readiness(db, [unit_id]).get(unit_id, {}).get('status', 'ready') != 'ready':
        raise HTTPException(409, 'Mark this unit ready before recording stocking')
    if data.stocked_on > date.today():
        raise HTTPException(422, 'Stocking date cannot be in the future')
    active = db.scalar(select(StockingCycle.id).where(StockingCycle.unit_id == unit_id, StockingCycle.closed_at.is_(None)))
    if active is not None:
        raise HTTPException(409, 'Unit already has an open stocking cycle')
    values = data.model_dump()
    values['expected_harvest_on'] = data.harvest_date(data.stocked_on)
    cycle = StockingCycle(unit_id=unit_id, **values)
    db.add(cycle); db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, cycle.id, 'stocking', cycle.id, user)
    audit(db, user, 'create', 'stocking_cycle', cycle.id, json.dumps({'unit_id': unit_id, 'stocked_count': cycle.stocked_count}))
    db.commit(); db.refresh(cycle)
    return cycle


@app.get('/farms/{farm_id}/units/{unit_id}/cycles', response_model=list[CycleOut], tags=['Aquaculture operations'])
def list_cycles(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    owned_unit(farm_id, unit_id, user, db)
    return db.scalars(select(StockingCycle).where(StockingCycle.unit_id == unit_id).order_by(StockingCycle.id)).all()


@app.put('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/harvest-plan', response_model=CycleOut, tags=['Aquaculture operations'])
def update_harvest_plan(farm_id: int, unit_id: int, cycle_id: int, data: HarvestPlanUpdate, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Cycle already closed')
    previous = cycle.expected_harvest_on
    changes = data.model_dump(exclude_unset=True, exclude={'reason'})
    if 'expected_harvest_on' in changes or 'harvest_duration_months' in changes:
        changes['expected_harvest_on'] = data.harvest_date(cycle.stocked_on)
        changes.setdefault('harvest_duration_months', None)
    for field, value in changes.items():
        setattr(cycle, field, value)
    audit(db, user, 'reschedule', 'stocking_cycle', cycle.id, json.dumps({
        'previous_date': previous.isoformat() if previous else None,
        'new_date': cycle.expected_harvest_on.isoformat() if cycle.expected_harvest_on else None,
        'reason': data.reason.strip(),
    }))
    db.commit()
    db.refresh(cycle)
    return cycle


@app.post('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/close', response_model=CycleOut, tags=['Aquaculture operations'])
def close_cycle(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Cycle already closed')
    cycle.closed_at = now()
    audit(db, user, 'close', 'stocking_cycle', cycle.id, json.dumps({'unit_id': unit_id}))
    db.commit(); db.refresh(cycle)
    return cycle


@app.post('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/mortality', response_model=MortalityOut, status_code=201, tags=['Aquaculture operations'])
def record_mortality(
    farm_id: int,
    unit_id: int,
    cycle_id: int,
    data: MortalityIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Cycle is closed')
    if data.observed_on < cycle.stocked_on or data.observed_on > date.today():
        raise HTTPException(422, 'Mortality date must be between stocking date and today')
    if data.dead_count > population(cycle, db).estimated_live_count:
        raise HTTPException(409, 'Mortality exceeds estimated live fish count')
    record = Mortality(cycle_id=cycle_id, **data.model_dump())
    db.add(record); db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, cycle_id, 'mortality', record.id, user)
    audit(db, user, 'create', 'mortality_record', record.id, json.dumps({'cycle_id': cycle_id, 'dead_count': data.dead_count}))
    db.commit(); db.refresh(record)
    return record


@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/mortality', response_model=list[MortalityOut], tags=['Aquaculture operations'])
def list_mortality(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    return db.scalars(select(Mortality).where(Mortality.cycle_id == cycle_id).order_by(Mortality.id)).all()


@app.post('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/samples', response_model=SampleOut, status_code=201, tags=['Aquaculture operations'])
def record_sample(
    farm_id: int,
    unit_id: int,
    cycle_id: int,
    data: SampleIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Cycle is closed')
    if data.sampled_on < cycle.stocked_on or data.sampled_on > date.today():
        raise HTTPException(422, 'Sample date must be between stocking date and today')
    if population(cycle, db).estimated_live_count == 0:
        raise HTTPException(409, 'No live fish remain in cycle')
    weights = data.weights_g
    record = FishSample(cycle_id=cycle_id, sampled_on=data.sampled_on,
                        weights_g_json=json.dumps(weights), sample_count=len(weights),
                        average_weight_g=sum(weights)/len(weights), notes=data.notes)
    db.add(record); db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, cycle_id, 'growth', record.id, user)
    audit(db, user, 'create', 'fish_sample', record.id, json.dumps({'cycle_id': cycle_id, 'sample_count': len(weights)}))
    db.commit(); db.refresh(record)
    return sample_out(record)


@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/samples', response_model=list[SampleOut], tags=['Aquaculture operations'])
def list_samples(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    return [sample_out(s) for s in db.scalars(select(FishSample).where(FishSample.cycle_id == cycle_id).order_by(FishSample.id)).all()]


@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/population', response_model=PopulationOut, tags=['Aquaculture operations'])
def get_population(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    return population(owned_cycle(farm_id, unit_id, cycle_id, user, db), db)


@app.post('/farms/{farm_id}/units/{unit_id}/water-quality', response_model=WaterOut, status_code=201, tags=['Aquaculture operations'])
def record_water(
    farm_id: int,
    unit_id: int,
    data: WaterIn,
    user: CurrentUser,
    db: Db,
    cycle_id: int = Query(gt=0),
    evidence_id: int = Query(gt=0),
):
    owned_unit(farm_id, unit_id, user, db)
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Water-quality evidence requires an active stocking cycle')
    if data.observed_at > now():
        raise HTTPException(422, 'Observation time cannot be in the future')
    record = WaterQuality(unit_id=unit_id, **data.model_dump())
    db.add(record); db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, cycle_id, 'water_quality', record.id, user)
    audit(db, user, 'create', 'water_quality_record', record.id, json.dumps({'unit_id': unit_id}))
    db.commit(); db.refresh(record)
    return record


class FishTransferIn(BaseModel):
    source_cycle_id: int = Field(gt=0)
    target_cycle_id: int = Field(gt=0)
    fish_count: int = Field(gt=0)
    loss_count: int = Field(default=0, ge=0)
    transferred_on: date
    notes: str | None = Field(default=None, max_length=2000)


class FishTreatmentIn(BaseModel):
    product: str = Field(min_length=2, max_length=160)
    dose: float = Field(gt=0)
    dose_unit: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=3, max_length=500)
    prescriber: str | None = Field(default=None, max_length=160)
    withdrawal_period_days: int = Field(ge=0, le=3650)
    treated_on: date
    notes: str | None = Field(default=None, max_length=2000)


class FarmInspectionIn(BaseModel):
    inspected_on: date
    checklist: dict[str, bool] = Field(min_length=1)
    observations: str = Field(min_length=3, max_length=4000)
    issues: str | None = Field(default=None, max_length=4000)
    corrective_actions: str | None = Field(default=None, max_length=4000)


class SupervisorIn(BaseModel):
    user_id: int = Field(gt=0)


def has_supervisor_access(farm_id: int, user: User, db: Session) -> bool:
    farm = db.get(Farm, farm_id)
    if farm is None or farm.archived_at is not None:
        raise HTTPException(404, 'Farm not found')
    if farm.owner_id == user.id:
        return True
    return db.scalar(select(FarmSupervisor.id).where(
        FarmSupervisor.farm_id == farm_id,
        FarmSupervisor.user_id == user.id,
    )) is not None


@app.get('/farms/{farm_id}/supervisors', tags=['Evidence verification'])
def list_farm_supervisors(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    rows = db.scalars(select(FarmSupervisor).where(
        FarmSupervisor.farm_id == farm_id
    ).order_by(FarmSupervisor.id)).all()
    return [{
        'id': row.id,
        'farm_id': row.farm_id,
        'user_id': row.user_id,
        'full_name': db.get(User, row.user_id).full_name,
        'email': db.get(User, row.user_id).email,
        'assigned_by': row.assigned_by,
        'created_at': row.created_at,
    } for row in rows]


@app.post('/farms/{farm_id}/supervisors', status_code=201, tags=['Evidence verification'])
def assign_farm_supervisor(farm_id: int, data: SupervisorIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    supervisor_user = db.get(User, data.user_id)
    if supervisor_user is None:
        raise HTTPException(404, 'User account not found')
    if supervisor_user.id == user.id:
        raise HTTPException(422, 'The farm owner is already authorized and cannot be assigned as supervisor')
    existing = db.scalar(select(FarmSupervisor).where(
        FarmSupervisor.farm_id == farm_id,
        FarmSupervisor.user_id == supervisor_user.id,
    ))
    if existing is not None:
        raise HTTPException(409, 'This user is already a supervisor for the farm')
    record = FarmSupervisor(
        farm_id=farm_id,
        user_id=supervisor_user.id,
        assigned_by=user.id,
    )
    db.add(record)
    db.flush()
    audit(db, user, 'assign', 'farm_supervisor', record.id, json.dumps({
        'farm_id': farm_id,
        'supervisor_user_id': supervisor_user.id,
    }))
    db.commit()
    db.refresh(record)
    return {
        'id': record.id,
        'farm_id': farm_id,
        'user_id': supervisor_user.id,
        'full_name': supervisor_user.full_name,
        'email': supervisor_user.email,
        'assigned_by': user.id,
        'created_at': record.created_at,
    }


@app.delete('/farms/{farm_id}/supervisors/{supervisor_user_id}', status_code=204, tags=['Evidence verification'])
def remove_farm_supervisor(farm_id: int, supervisor_user_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    record = db.scalar(select(FarmSupervisor).where(
        FarmSupervisor.farm_id == farm_id,
        FarmSupervisor.user_id == supervisor_user_id,
    ))
    if record is None:
        raise HTTPException(404, 'Farm supervisor not found')
    audit(db, user, 'remove', 'farm_supervisor', record.id, json.dumps({
        'farm_id': farm_id,
        'supervisor_user_id': supervisor_user_id,
    }))
    db.delete(record)
    db.commit()


@app.post('/farms/{farm_id}/fish-transfers', status_code=201, tags=['Aquaculture operations'])
def create_fish_transfer(
    farm_id: int,
    data: FishTransferIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    farm = owned_farm(farm_id, user, db)
    if data.source_cycle_id == data.target_cycle_id:
        raise HTTPException(422, 'Source and destination cycles must be different')
    cycles = db.scalars(
        select(StockingCycle).join(ProductionUnit, StockingCycle.unit_id == ProductionUnit.id).where(
            StockingCycle.id.in_([data.source_cycle_id, data.target_cycle_id]),
            ProductionUnit.farm_id == farm.id,
        )
    ).all()
    by_id = {cycle.id: cycle for cycle in cycles}
    source = by_id.get(data.source_cycle_id)
    target = by_id.get(data.target_cycle_id)
    if source is None or target is None:
        raise HTTPException(404, 'Both production cycles must belong to this farm')
    if source.closed_at is not None or target.closed_at is not None:
        raise HTTPException(409, 'Fish can only be transferred between active cycles')
    if data.transferred_on < max(source.stocked_on, target.stocked_on) or data.transferred_on > date.today():
        raise HTTPException(422, 'Transfer date must be between both stocking dates and today')
    if data.fish_count + data.loss_count > population(source, db).estimated_live_count:
        raise HTTPException(409, 'Transfer and losses exceed the source cycle live fish estimate')
    transfer = FishTransfer(**data.model_dump(), created_by=user.id)
    db.add(transfer)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(
        db, evidence_id, farm_id, source.unit_id, source.id,
        'fish_transfer', transfer.id, user,
    )
    audit(db, user, 'transfer', 'fish_transfer', transfer.id, json.dumps({
        'source_cycle_id': source.id,
        'target_cycle_id': target.id,
        'fish_count': transfer.fish_count,
        'loss_count': transfer.loss_count,
    }))
    db.commit()
    return {
        'id': transfer.id,
        'source_cycle_id': source.id,
        'target_cycle_id': target.id,
        'fish_count': transfer.fish_count,
        'loss_count': transfer.loss_count,
        'transferred_on': transfer.transferred_on,
        'notes': transfer.notes,
        'evidence_id': evidence_id,
    }


@app.get('/farms/{farm_id}/fish-transfers', tags=['Aquaculture operations'])
def list_fish_transfers(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    from .evidence import RecordEvidence
    cycle_ids = select(StockingCycle.id).join(
        ProductionUnit, StockingCycle.unit_id == ProductionUnit.id
    ).where(ProductionUnit.farm_id == farm_id)
    rows = db.scalars(select(FishTransfer).where(
        FishTransfer.source_cycle_id.in_(cycle_ids) | FishTransfer.target_cycle_id.in_(cycle_ids)
    ).order_by(FishTransfer.transferred_on, FishTransfer.id)).all()
    return [{
        'id': row.id,
        'source_cycle_id': row.source_cycle_id,
        'target_cycle_id': row.target_cycle_id,
        'fish_count': row.fish_count,
        'loss_count': row.loss_count,
        'transferred_on': row.transferred_on,
        'notes': row.notes,
        'evidence_id': db.scalar(select(RecordEvidence.id).where(
            RecordEvidence.record_type == 'fish_transfer',
            RecordEvidence.record_id == row.id,
        )),
    } for row in rows]


@app.post(
    '/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/treatments',
    status_code=201,
    tags=['Aquaculture operations'],
)
def create_treatment(
    farm_id: int,
    unit_id: int,
    cycle_id: int,
    data: FishTreatmentIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at is not None:
        raise HTTPException(409, 'Cannot record a treatment on a closed cycle')
    if data.treated_on < cycle.stocked_on or data.treated_on > date.today():
        raise HTTPException(422, 'Treatment date must be between stocking date and today')
    record = FishTreatment(unit_id=unit_id, cycle_id=cycle_id, created_by=user.id, **data.model_dump())
    db.add(record)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(
        db, evidence_id, farm_id, unit_id, cycle_id,
        'treatment', record.id, user,
    )
    audit(db, user, 'create', 'fish_treatment', record.id, json.dumps({
        'cycle_id': cycle_id,
        'product': record.product,
        'withdrawal_period_days': record.withdrawal_period_days,
    }))
    db.commit()
    return {
        'id': record.id,
        'unit_id': record.unit_id,
        'cycle_id': record.cycle_id,
        **data.model_dump(),
        'evidence_id': evidence_id,
        'created_by': record.created_by,
        'created_at': record.created_at,
    }


@app.get(
    '/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/treatments',
    tags=['Aquaculture operations'],
)
def list_treatments(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    rows = db.scalars(select(FishTreatment).where(
        FishTreatment.cycle_id == cycle_id
    ).order_by(FishTreatment.treated_on.desc(), FishTreatment.id.desc())).all()
    from .evidence import RecordEvidence
    return [{
        'id': row.id,
        'unit_id': row.unit_id,
        'cycle_id': row.cycle_id,
        'product': row.product,
        'dose': row.dose,
        'dose_unit': row.dose_unit,
        'reason': row.reason,
        'prescriber': row.prescriber,
        'withdrawal_period_days': row.withdrawal_period_days,
        'treated_on': row.treated_on,
        'notes': row.notes,
        'evidence_id': db.scalar(select(RecordEvidence.id).where(
            RecordEvidence.record_type == 'treatment',
            RecordEvidence.record_id == row.id,
        )),
        'created_by': row.created_by,
        'created_at': row.created_at,
    } for row in rows]


@app.post(
    '/farms/{farm_id}/units/{unit_id}/inspections',
    status_code=201,
    tags=['Aquaculture operations'],
)
def create_inspection(
    farm_id: int,
    unit_id: int,
    data: FarmInspectionIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    owned_unit(farm_id, unit_id, user, db)
    if data.inspected_on > date.today():
        raise HTTPException(422, 'Inspection date cannot be in the future')
    record = FarmInspection(
        unit_id=unit_id,
        inspected_on=data.inspected_on,
        checklist_json=json.dumps(data.checklist, sort_keys=True),
        observations=data.observations,
        issues=data.issues,
        corrective_actions=data.corrective_actions,
        created_by=user.id,
    )
    db.add(record)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(
        db, evidence_id, farm_id, unit_id, None,
        'inspection', record.id, user,
    )
    audit(db, user, 'create', 'farm_inspection', record.id, json.dumps({
        'unit_id': unit_id,
        'issues_reported': bool(record.issues),
    }))
    db.commit()
    return {
        'id': record.id,
        'unit_id': record.unit_id,
        'inspected_on': record.inspected_on,
        'checklist': data.checklist,
        'observations': record.observations,
        'issues': record.issues,
        'corrective_actions': record.corrective_actions,
        'evidence_id': evidence_id,
        'created_by': record.created_by,
        'created_at': record.created_at,
    }


@app.get('/farms/{farm_id}/units/{unit_id}/inspections', tags=['Aquaculture operations'])
def list_inspections(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    owned_unit(farm_id, unit_id, user, db)
    from .evidence import RecordEvidence
    rows = db.scalars(select(FarmInspection).where(
        FarmInspection.unit_id == unit_id
    ).order_by(FarmInspection.inspected_on.desc(), FarmInspection.id.desc())).all()
    return [{
        'id': row.id,
        'unit_id': row.unit_id,
        'inspected_on': row.inspected_on,
        'checklist': json.loads(row.checklist_json),
        'observations': row.observations,
        'issues': row.issues,
        'corrective_actions': row.corrective_actions,
        'evidence_id': db.scalar(select(RecordEvidence.id).where(
            RecordEvidence.record_type == 'inspection',
            RecordEvidence.record_id == row.id,
        )),
        'created_by': row.created_by,
        'created_at': row.created_at,
    } for row in rows]


@app.get('/farms/{farm_id}/units/{unit_id}/water-quality', response_model=list[WaterOut], tags=['Aquaculture operations'])
def list_water(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    owned_unit(farm_id, unit_id, user, db)
    return db.scalars(select(WaterQuality).where(WaterQuality.unit_id == unit_id).order_by(WaterQuality.observed_at.desc(), WaterQuality.id.desc())).all()


@app.get('/farms/{farm_id}/units/{unit_id}/activity', tags=['Aquaculture operations'])
def unit_activity(farm_id: int, unit_id: int, user: CurrentUser, db: Db):
    """Return audit events for this unit and its cycles, including their child records."""
    owned_unit(farm_id, unit_id, user, db)
    cycle_ids = select(StockingCycle.id).where(StockingCycle.unit_id == unit_id)
    mortality_ids = select(Mortality.id).where(Mortality.cycle_id.in_(cycle_ids))
    sample_ids = select(FishSample.id).where(FishSample.cycle_id.in_(cycle_ids))
    water_ids = select(WaterQuality.id).where(WaterQuality.unit_id == unit_id)
    records = db.scalars(select(AuditLog).where(
        ((AuditLog.entity_type == 'production_unit') & (AuditLog.entity_id == unit_id)) |
        ((AuditLog.entity_type == 'stocking_cycle') & (AuditLog.entity_id.in_(cycle_ids))) |
        ((AuditLog.entity_type == 'mortality_record') & (AuditLog.entity_id.in_(mortality_ids))) |
        ((AuditLog.entity_type == 'fish_sample') & (AuditLog.entity_id.in_(sample_ids))) |
        ((AuditLog.entity_type == 'water_quality_record') & (AuditLog.entity_id.in_(water_ids)))
    ).order_by(AuditLog.id)).all()
    return [{'id': r.id, 'actor_id': r.actor_id, 'action': r.action,
             'entity_type': r.entity_type, 'entity_id': r.entity_id,
             'details': json.loads(r.details), 'created_at': r.created_at} for r in records]
