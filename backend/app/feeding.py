"""Feed stock ledger, feeding logs, configurable estimates and indicative FCR."""
from datetime import date, datetime, timezone
from math import isfinite
from typing import Literal
import json
from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, audit
from .operations import owned_farm, owned_cycle, owned_unit, StockingCycle, FishSample, population, WaterQuality


def now(): return datetime.now(timezone.utc)

class FeedProduct(Base):
    __tablename__ = 'feed_products'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    supplier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pellet_size_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FeedLedger(Base):
    __tablename__ = 'feed_ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey('feed_products.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(20))  # receipt / feeding / adjustment
    quantity_delta_kg: Mapped[float] = mapped_column(Float)
    cost_ghs: Mapped[float | None] = mapped_column(Float, nullable=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey('stocking_cycles.id'), nullable=True, index=True)
    occurred_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey('feeding_recommendations.id'), nullable=True)
    session_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FeedReconciliation(Base):
    __tablename__ = 'feed_reconciliations'
    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey('feed_products.id'), index=True)
    ledger_entry_id: Mapped[int] = mapped_column(ForeignKey('feed_ledger.id'), unique=True)
    system_stock_before_kg: Mapped[float] = mapped_column(Float)
    physical_stock_kg: Mapped[float] = mapped_column(Float)
    variance_kg: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500))
    counted_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey('record_evidence.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FarmFeedingProfileApproval(Base):
    __tablename__ = 'farm_feeding_profile_approvals'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'))
    species: Mapped[str] = mapped_column(String(20))
    profile_version: Mapped[str] = mapped_column(String(40))
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True)


class FeedingRecommendation(Base):
    __tablename__ = 'feeding_recommendations'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'))
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'))
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey('feed_products.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    profile_version: Mapped[str] = mapped_column(String(40))
    profile_approval_id: Mapped[int] = mapped_column(ForeignKey('farm_feeding_profile_approvals.id'))
    sampling_id: Mapped[int | None] = mapped_column(ForeignKey('fish_samples.id'), nullable=True)
    water_quality_id: Mapped[int | None] = mapped_column(ForeignKey('water_quality_records.id'), nullable=True)
    estimated_live_count: Mapped[int] = mapped_column(Integer)
    average_weight_g: Mapped[float] = mapped_column(Float)
    estimated_biomass_kg: Mapped[float] = mapped_column(Float)
    daily_rate_pct: Mapped[float] = mapped_column(Float)
    daily_ration_kg: Mapped[float] = mapped_column(Float)
    session_count: Mapped[int] = mapped_column(Integer)
    session_ration_kg: Mapped[float] = mapped_column(Float)
    pellet_size_min_mm: Mapped[float] = mapped_column(Float)
    pellet_size_max_mm: Mapped[float] = mapped_column(Float)
    inputs_json: Mapped[str] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FeedIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    supplier: str | None = Field(default=None, max_length=120)
    pellet_size_mm: float | None = Field(default=None, gt=0)
    protein_pct: float | None = Field(default=None, ge=0, le=100)

class FeedOut(FeedIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farm_id: int
    created_at: datetime

class ReceiptIn(BaseModel):
    quantity_kg: float = Field(gt=0)
    total_cost_ghs: float = Field(ge=0)
    occurred_on: date
    notes: str | None = Field(default=None, max_length=1000)
    supplier: str | None = Field(default=None, max_length=120)
    batch_number: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)

class FeedingIn(BaseModel):
    feed_id: int
    quantity_kg: float = Field(gt=0)
    fed_on: date
    notes: str | None = Field(default=None, max_length=1000)
    recommendation_id: int | None = Field(default=None, gt=0)
    session_number: int | None = Field(default=None, ge=1)

class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    feed_id: int
    event_type: str
    quantity_delta_kg: float
    cost_ghs: float | None
    cycle_id: int | None
    occurred_on: date
    notes: str | None
    supplier: str | None
    batch_number: str | None
    expiry_date: date | None
    reference_number: str | None
    recommendation_id: int | None
    session_number: int | None
    evidence_id: int | None
    created_at: datetime

class RecommendationIn(BaseModel):
    feed_id: int = Field(gt=0)
    daily_feeding_rate_pct: float | None = Field(default=None, gt=0, le=20)
    minimum_do_mg_l: float = Field(default=4, ge=0, description='User-configured alert threshold, not a universal species limit')
    max_water_age_hours: int = Field(default=24, ge=1, le=168)
    minimum_temperature_c: float | None = Field(default=None, ge=-5, le=60)
    maximum_temperature_c: float | None = Field(default=None, ge=-5, le=60)
    minimum_ph: float | None = Field(default=None, ge=0, le=14)
    maximum_ph: float | None = Field(default=None, ge=0, le=14)
    maximum_ammonia_mg_l: float | None = Field(default=None, ge=0)
    maximum_nitrite_mg_l: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def valid_water_limits(self):
        if (self.minimum_temperature_c is None) != (self.maximum_temperature_c is None):
            raise ValueError('Set both temperature limits or neither')
        if self.minimum_temperature_c is not None and self.minimum_temperature_c >= self.maximum_temperature_c:
            raise ValueError('Minimum temperature must be below maximum temperature')
        if (self.minimum_ph is None) != (self.maximum_ph is None):
            raise ValueError('Set both pH limits or neither')
        if self.minimum_ph is not None and self.minimum_ph >= self.maximum_ph:
            raise ValueError('Minimum pH must be below maximum pH')
        return self


class InventoryAdjustmentIn(BaseModel):
    physical_stock_kg: float = Field(ge=0)
    occurred_on: date
    reason: str = Field(min_length=5, max_length=500)


def feed_for_farm(farm_id, feed_id, user, db):
    owned_farm(farm_id, user, db)
    product = db.scalar(select(FeedProduct).where(FeedProduct.id == feed_id, FeedProduct.farm_id == farm_id))
    if product is None: raise HTTPException(404, 'Feed product not found')
    return product


def stock(feed_id, db):
    return round(float(db.scalar(select(func.coalesce(func.sum(FeedLedger.quantity_delta_kg), 0)).where(FeedLedger.feed_id == feed_id)) or 0), 6)


def valid_date(value):
    if value > date.today(): raise HTTPException(422, 'Date cannot be in the future')


FEEDING_PROFILE_VERSION = 'ghana-advisory-v1'
FEEDING_PROFILES = {
    'tilapia': (
        {'max_weight_g': 5, 'minimum_rate_pct': 6.0, 'maximum_rate_pct': 10.0, 'pellet_size_mm': (0.5, 1.0), 'sessions_per_day': 4},
        {'max_weight_g': 20, 'minimum_rate_pct': 4.0, 'maximum_rate_pct': 7.0, 'pellet_size_mm': (1.0, 2.0), 'sessions_per_day': 3},
        {'max_weight_g': 100, 'minimum_rate_pct': 2.5, 'maximum_rate_pct': 5.0, 'pellet_size_mm': (2.0, 3.0), 'sessions_per_day': 2},
        {'max_weight_g': 250, 'minimum_rate_pct': 1.5, 'maximum_rate_pct': 3.0, 'pellet_size_mm': (3.0, 4.0), 'sessions_per_day': 2},
        {'max_weight_g': None, 'minimum_rate_pct': 1.0, 'maximum_rate_pct': 2.0, 'pellet_size_mm': (3.0, 5.0), 'sessions_per_day': 2},
    ),
    'catfish': (
        {'max_weight_g': 5, 'minimum_rate_pct': 8.0, 'maximum_rate_pct': 12.0, 'pellet_size_mm': (0.5, 1.0), 'sessions_per_day': 4},
        {'max_weight_g': 20, 'minimum_rate_pct': 5.0, 'maximum_rate_pct': 8.0, 'pellet_size_mm': (1.0, 2.0), 'sessions_per_day': 3},
        {'max_weight_g': 100, 'minimum_rate_pct': 3.0, 'maximum_rate_pct': 5.0, 'pellet_size_mm': (2.0, 3.0), 'sessions_per_day': 2},
        {'max_weight_g': 250, 'minimum_rate_pct': 2.0, 'maximum_rate_pct': 4.0, 'pellet_size_mm': (3.0, 4.0), 'sessions_per_day': 2},
        {'max_weight_g': None, 'minimum_rate_pct': 1.5, 'maximum_rate_pct': 3.0, 'pellet_size_mm': (3.0, 5.0), 'sessions_per_day': 2},
    ),
}


def species_key(species: str) -> str | None:
    lowered = species.lower()
    if 'tilapia' in lowered:
        return 'tilapia'
    if 'catfish' in lowered:
        return 'catfish'
    return None


def feeding_profile(species: str, average_weight_g: float):
    key = species_key(species)
    if key is None:
        return None
    for band in FEEDING_PROFILES[key]:
        if band['max_weight_g'] is None or average_weight_g <= band['max_weight_g']:
            return {
                'species': key,
                'version': FEEDING_PROFILE_VERSION,
                'basis': 'advisory starter profile; farm-owner confirmation required',
                'maximum_weight_g': band['max_weight_g'],
                'minimum_rate_pct': band['minimum_rate_pct'],
                'maximum_rate_pct': band['maximum_rate_pct'],
                'recommended_rate_pct': round((band['minimum_rate_pct'] + band['maximum_rate_pct']) / 2, 2),
                'pellet_size_min_mm': band['pellet_size_mm'][0],
                'pellet_size_max_mm': band['pellet_size_mm'][1],
                'sessions_per_day': band['sessions_per_day'],
            }
    return None


def recommendation_view(item: FeedingRecommendation):
    return {
        'id': item.id,
        'farm_id': item.farm_id,
        'unit_id': item.unit_id,
        'cycle_id': item.cycle_id,
        'feed_id': item.feed_id,
        'profile_version': item.profile_version,
        'profile_approval_id': item.profile_approval_id,
        'sampling_id': item.sampling_id,
        'water_quality_id': item.water_quality_id,
        'estimated_live_count': item.estimated_live_count,
        'average_weight_g': item.average_weight_g,
        'estimated_biomass_kg': item.estimated_biomass_kg,
        'daily_rate_pct': item.daily_rate_pct,
        'daily_ration_kg': item.daily_ration_kg,
        'session_count': item.session_count,
        'session_ration_kg': item.session_ration_kg,
        'pellet_size_min_mm': item.pellet_size_min_mm,
        'pellet_size_max_mm': item.pellet_size_max_mm,
        'inputs': json.loads(item.inputs_json),
        'warnings': json.loads(item.warnings_json),
        'status': item.status,
        'approved_by': item.approved_by,
        'approved_at': item.approved_at,
        'created_at': item.created_at,
    }


@app.get('/farms/{farm_id}/feeding-profiles', tags=['Feeding and inventory'])
def list_feeding_profiles(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    approvals = db.scalars(select(FarmFeedingProfileApproval).where(
        FarmFeedingProfileApproval.farm_id == farm_id,
        FarmFeedingProfileApproval.active.is_(True),
    )).all()
    approved = {item.species: item for item in approvals}
    profiles = []
    for species, bands in FEEDING_PROFILES.items():
        profiles.append({
            'species': species,
            'version': FEEDING_PROFILE_VERSION,
            'basis': 'advisory starter profile; not a locally certified ration',
            'approved': species in approved and approved[species].profile_version == FEEDING_PROFILE_VERSION,
            'approved_at': approved[species].approved_at if species in approved else None,
            'bands': list(bands),
        })
    return profiles


@app.post('/farms/{farm_id}/feeding-profiles/{species}/approve', tags=['Feeding and inventory'])
def approve_feeding_profile(farm_id: int, species: str, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    key = species_key(species)
    if key is None:
        raise HTTPException(422, 'Only tilapia and catfish profiles are available')
    db.query(FarmFeedingProfileApproval).filter(
        FarmFeedingProfileApproval.farm_id == farm_id,
        FarmFeedingProfileApproval.species == key,
        FarmFeedingProfileApproval.active.is_(True),
    ).update({'active': False})
    approval = FarmFeedingProfileApproval(
        farm_id=farm_id,
        species=key,
        profile_version=FEEDING_PROFILE_VERSION,
        approved_by=user.id,
        approved_at=now(),
        active=True,
    )
    db.add(approval)
    db.flush()
    audit(db, user, 'approve', 'feeding_profile', approval.id, json.dumps({
        'species': key,
        'profile_version': FEEDING_PROFILE_VERSION,
    }))
    db.commit()
    return {'species': key, 'profile_version': FEEDING_PROFILE_VERSION, 'approved_by': user.id, 'approved_at': approval.approved_at}

@app.post('/farms/{farm_id}/feeds', response_model=FeedOut, status_code=201, tags=['Feeding and inventory'])
def create_feed(farm_id: int, data: FeedIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    feed = FeedProduct(farm_id=farm_id, **data.model_dump())
    db.add(feed); db.flush(); audit(db, user, 'create', 'feed_product', feed.id, json.dumps({'farm_id': farm_id}))
    db.commit(); db.refresh(feed)
    return feed

@app.get('/farms/{farm_id}/feeds', tags=['Feeding and inventory'])
def list_feeds(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    feeds = db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id).order_by(FeedProduct.id)).all()
    return [{'id': f.id, 'name': f.name, 'supplier': f.supplier, 'pellet_size_mm': f.pellet_size_mm,
             'protein_pct': f.protein_pct, 'stock_kg': stock(f.id, db)} for f in feeds]

@app.post('/farms/{farm_id}/feeds/{feed_id}/receipts', response_model=LedgerOut, status_code=201, tags=['Feeding and inventory'])
def receive_feed(
    farm_id: int,
    feed_id: int,
    data: ReceiptIn,
    user: CurrentUser,
    db: Db,
    unit_id: int = Query(gt=0),
    evidence_id: int = Query(gt=0),
):
    feed = feed_for_farm(farm_id, feed_id, user, db); valid_date(data.occurred_on)
    if data.expiry_date is not None and data.expiry_date < data.occurred_on:
        raise HTTPException(422, 'Feed expiry date cannot be before its receipt date')
    entry = FeedLedger(feed_id=feed_id, event_type='receipt', quantity_delta_kg=data.quantity_kg,
                       cost_ghs=data.total_cost_ghs, occurred_on=data.occurred_on, notes=data.notes,
                       supplier=data.supplier or feed.supplier, batch_number=data.batch_number,
                       expiry_date=data.expiry_date, reference_number=data.reference_number)
    db.add(entry); db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, None, 'feed_delivery', entry.id, user)
    entry.evidence_id = evidence_id
    audit(db, user, 'create', 'feed_receipt', entry.id, json.dumps({'feed_id': feed_id, 'quantity_kg': data.quantity_kg}))
    db.commit(); db.refresh(entry); return entry

@app.get('/farms/{farm_id}/feeds/{feed_id}/ledger', response_model=list[LedgerOut], tags=['Feeding and inventory'])
def feed_ledger(farm_id: int, feed_id: int, user: CurrentUser, db: Db):
    feed_for_farm(farm_id, feed_id, user, db)
    return db.scalars(select(FeedLedger).where(FeedLedger.feed_id == feed_id).order_by(FeedLedger.id)).all()


@app.post('/farms/{farm_id}/feeds/{feed_id}/reconciliations', status_code=201, tags=['Feeding and inventory'])
def reconcile_feed_stock(
    farm_id: int,
    feed_id: int,
    data: InventoryAdjustmentIn,
    user: CurrentUser,
    db: Db,
    unit_id: int = Query(gt=0),
    evidence_id: int = Query(gt=0),
):
    feed_for_farm(farm_id, feed_id, user, db)
    valid_date(data.occurred_on)
    system_stock = stock(feed_id, db)
    if system_stock < -1e-8:
        raise HTTPException(409, 'Recorded inventory is already negative; resolve the ledger discrepancy first')
    variance = round(data.physical_stock_kg - system_stock, 6)
    entry = FeedLedger(
        feed_id=feed_id,
        event_type='adjustment',
        quantity_delta_kg=variance,
        occurred_on=data.occurred_on,
        notes=data.reason,
        evidence_id=evidence_id,
    )
    db.add(entry)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, None, 'feed_stock_count', entry.id, user)
    reconciliation = FeedReconciliation(
        feed_id=feed_id,
        ledger_entry_id=entry.id,
        system_stock_before_kg=system_stock,
        physical_stock_kg=data.physical_stock_kg,
        variance_kg=variance,
        reason=data.reason,
        counted_by=user.id,
        evidence_id=evidence_id,
    )
    db.add(reconciliation)
    audit(db, user, 'reconcile', 'feed_inventory', feed_id, json.dumps({
        'system_stock_before_kg': system_stock,
        'physical_stock_kg': data.physical_stock_kg,
        'variance_kg': variance,
        'ledger_entry_id': entry.id,
        'evidence_id': evidence_id,
    }))
    db.commit()
    return {
        'id': reconciliation.id,
        'feed_id': feed_id,
        'system_stock_before_kg': system_stock,
        'physical_stock_kg': data.physical_stock_kg,
        'variance_kg': variance,
        'stock_after_kg': stock(feed_id, db),
        'reason': data.reason,
        'evidence_id': evidence_id,
    }


@app.get('/farms/{farm_id}/feeds/{feed_id}/reconciliations', tags=['Feeding and inventory'])
def feed_reconciliations(farm_id: int, feed_id: int, user: CurrentUser, db: Db):
    feed_for_farm(farm_id, feed_id, user, db)
    rows = db.scalars(select(FeedReconciliation).where(
        FeedReconciliation.feed_id == feed_id
    ).order_by(FeedReconciliation.id.desc())).all()
    return [{
        'id': row.id,
        'feed_id': row.feed_id,
        'ledger_entry_id': row.ledger_entry_id,
        'system_stock_before_kg': row.system_stock_before_kg,
        'physical_stock_kg': row.physical_stock_kg,
        'variance_kg': row.variance_kg,
        'reason': row.reason,
        'counted_by': row.counted_by,
        'evidence_id': row.evidence_id,
        'created_at': row.created_at,
    } for row in rows]

@app.post('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding', response_model=LedgerOut, status_code=201, tags=['Feeding and inventory'])
def record_feeding(
    farm_id: int,
    unit_id: int,
    cycle_id: int,
    data: FeedingIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    feed_for_farm(farm_id, data.feed_id, user, db)
    if cycle.closed_at is not None: raise HTTPException(409, 'Cycle is closed')
    valid_date(data.fed_on)
    if data.fed_on < cycle.stocked_on: raise HTTPException(422, 'Feeding cannot predate stocking')
    recommendation = None
    if data.recommendation_id is not None:
        recommendation = db.get(FeedingRecommendation, data.recommendation_id)
        if recommendation is None or recommendation.farm_id != farm_id or recommendation.cycle_id != cycle_id or recommendation.feed_id != data.feed_id:
            raise HTTPException(404, 'Feeding recommendation not found for this farm, cycle, and feed')
        if recommendation.status != 'approved':
            raise HTTPException(409, 'Feeding recommendation must be approved before use')
        if data.session_number is None or data.session_number > recommendation.session_count:
            raise HTTPException(422, 'Choose a valid feeding session from the approved recommendation')
        if db.scalar(select(FeedLedger.id).where(
            FeedLedger.recommendation_id == recommendation.id,
            FeedLedger.session_number == data.session_number,
        )) is not None:
            raise HTTPException(409, 'This recommended feeding session is already recorded')
    elif data.session_number is not None:
        raise HTTPException(422, 'A feeding session number requires an approved recommendation')
    if stock(data.feed_id, db) + 1e-8 < data.quantity_kg: raise HTTPException(409, 'Insufficient feed stock')
    entry = FeedLedger(feed_id=data.feed_id, event_type='feeding', quantity_delta_kg=-data.quantity_kg,
                       cycle_id=cycle_id, occurred_on=data.fed_on, notes=data.notes,
                       recommendation_id=recommendation.id if recommendation else None,
                       session_number=data.session_number)
    db.add(entry); db.flush(); audit(db, user, 'create', 'feeding', entry.id, json.dumps({'cycle_id': cycle_id, 'quantity_kg': data.quantity_kg}))
    from .evidence import attach_record_evidence
    attach_record_evidence(db, evidence_id, farm_id, unit_id, cycle_id, 'feeding', entry.id, user)
    db.commit(); db.refresh(entry); return entry

@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding', response_model=list[LedgerOut], tags=['Feeding and inventory'])
def list_feeding(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    return db.scalars(select(FeedLedger).where(FeedLedger.cycle_id == cycle_id, FeedLedger.event_type == 'feeding').order_by(FeedLedger.id)).all()

@app.post('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding-estimate', tags=['Feeding and inventory'])
def feeding_estimate(farm_id: int, unit_id: int, cycle_id: int, data: RecommendationIn, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    feed = feed_for_farm(farm_id, data.feed_id, user, db)
    pop = population(cycle, db)
    from .evidence import RecordEvidence
    sampling = db.scalar(
        select(FishSample)
        .join(RecordEvidence, (RecordEvidence.record_id == FishSample.id) & (RecordEvidence.record_type == 'growth'))
        .where(
            FishSample.cycle_id == cycle_id,
            RecordEvidence.verification_status == 'verified',
            RecordEvidence.archived_at.is_(None),
        )
        .order_by(FishSample.sampled_on.desc(), FishSample.id.desc())
    )
    average_weight_g = sampling.average_weight_g if sampling else cycle.initial_average_weight_g
    biomass_kg = round(pop.estimated_live_count * average_weight_g / 1000, 4)
    key = species_key(cycle.species)
    if key is None:
        raise HTTPException(422, 'Advisory feeding profiles are available only for tilapia and catfish')
    approval = db.scalar(select(FarmFeedingProfileApproval).where(
        FarmFeedingProfileApproval.farm_id == farm_id,
        FarmFeedingProfileApproval.species == key,
        FarmFeedingProfileApproval.profile_version == FEEDING_PROFILE_VERSION,
        FarmFeedingProfileApproval.active.is_(True),
    ))
    if approval is None:
        raise HTTPException(409, 'The farm owner must confirm the advisory species profile before calculating a ration')
    profile = feeding_profile(cycle.species, average_weight_g)
    if profile is None:
        raise HTTPException(422, 'Advisory feeding profiles are available only for tilapia and catfish')
    rate = data.daily_feeding_rate_pct or profile['recommended_rate_pct']
    if not profile['minimum_rate_pct'] <= rate <= profile['maximum_rate_pct']:
        raise HTTPException(422, 'Selected feeding rate is outside the species and size profile range')
    warnings = [
        'Advisory starting profile only; confirm feed rates with the feed label and a qualified local aquaculture adviser.',
        'Feed is divided into scheduled sessions; record each actual session to deduct inventory.',
    ]
    latest = db.scalar(
        select(WaterQuality)
        .join(RecordEvidence, (RecordEvidence.record_id == WaterQuality.id) & (RecordEvidence.record_type == 'water_quality'))
        .where(
            WaterQuality.unit_id == unit_id,
            RecordEvidence.cycle_id == cycle_id,
            RecordEvidence.verification_status == 'verified',
            RecordEvidence.archived_at.is_(None),
        )
        .order_by(WaterQuality.observed_at.desc(), WaterQuality.id.desc())
    )
    recommendation_suspended = False
    if sampling is None:
        warnings.append('No verified fish sample is available; stocking weight is used only for a provisional estimate.')
        recommendation_suspended = True
    if latest is None or latest.dissolved_oxygen_mg_l is None:
        warnings.append('No dissolved oxygen reading available: check water quality before feeding.')
        recommendation_suspended = True
    else:
        observed_at = latest.observed_at.replace(tzinfo=latest.observed_at.tzinfo or timezone.utc)
        age = (now() - observed_at.astimezone(timezone.utc)).total_seconds()/3600
        if age > data.max_water_age_hours:
            warnings.append('Latest water-quality reading is older than the configured freshness limit.')
            recommendation_suspended = True
        if latest.dissolved_oxygen_mg_l < data.minimum_do_mg_l:
            warnings.append('Dissolved oxygen below your configured alert threshold: assess conditions before feeding.')
            recommendation_suspended = True
        if data.minimum_temperature_c is not None and latest.temperature_c is not None:
            if not data.minimum_temperature_c <= latest.temperature_c <= data.maximum_temperature_c:
                warnings.append('Temperature is outside the farm-configured feeding range.')
                recommendation_suspended = True
        if data.minimum_ph is not None and latest.ph is not None:
            if not data.minimum_ph <= latest.ph <= data.maximum_ph:
                warnings.append('pH is outside the farm-configured feeding range.')
                recommendation_suspended = True
        if data.maximum_ammonia_mg_l is not None and latest.ammonia_mg_l is not None and latest.ammonia_mg_l > data.maximum_ammonia_mg_l:
            warnings.append('Ammonia exceeds the farm-configured limit; pause the recommendation and investigate.')
            recommendation_suspended = True
        if data.maximum_nitrite_mg_l is not None and latest.nitrite_mg_l is not None and latest.nitrite_mg_l > data.maximum_nitrite_mg_l:
            warnings.append('Nitrite exceeds the farm-configured limit; pause the recommendation and investigate.')
            recommendation_suspended = True
    daily_ration = round(biomass_kg * rate / 100, 4)
    session_ration = round(daily_ration / profile['sessions_per_day'], 4)
    snapshot = {
        'feed_product': {'id': feed.id, 'name': feed.name, 'pellet_size_mm': feed.pellet_size_mm,
                         'protein_pct': feed.protein_pct, 'stock_kg': stock(feed.id, db)},
        'profile': profile,
        'estimated_population': pop.estimated_live_count,
        'average_weight_g': average_weight_g,
        'sampling_id': sampling.id if sampling else None,
        'water_quality_id': latest.id if latest else None,
        'water_limits': data.model_dump(exclude={'feed_id', 'daily_feeding_rate_pct'}),
        'calculated_at': now().isoformat(),
    }
    recommendation = FeedingRecommendation(
        farm_id=farm_id,
        unit_id=unit_id,
        cycle_id=cycle_id,
        feed_id=feed.id,
        created_by=user.id,
        profile_version=FEEDING_PROFILE_VERSION,
        profile_approval_id=approval.id,
        sampling_id=sampling.id if sampling else None,
        water_quality_id=latest.id if latest else None,
        estimated_live_count=pop.estimated_live_count,
        average_weight_g=average_weight_g,
        estimated_biomass_kg=biomass_kg,
        daily_rate_pct=rate,
        daily_ration_kg=daily_ration,
        session_count=profile['sessions_per_day'],
        session_ration_kg=session_ration,
        pellet_size_min_mm=profile['pellet_size_min_mm'],
        pellet_size_max_mm=profile['pellet_size_max_mm'],
        inputs_json=json.dumps(snapshot, default=str),
        warnings_json=json.dumps(warnings),
        status='suspended' if recommendation_suspended else 'pending_approval',
    )
    db.add(recommendation)
    db.flush()
    audit(db, user, 'calculate', 'feeding_recommendation', recommendation.id, json.dumps({
        'cycle_id': cycle_id, 'feed_id': feed.id, 'profile_version': FEEDING_PROFILE_VERSION,
        'status': recommendation.status,
    }))
    db.commit()
    return {'recommendation_id': recommendation.id, 'species': cycle.species,
            'estimated_live_count': pop.estimated_live_count,
            'average_weight_g': average_weight_g,
            'estimated_biomass_kg': biomass_kg,
            'profile': profile,
            'daily_feeding_rate_pct': rate,
            'estimated_daily_feed_kg': daily_ration,
            'session_count': profile['sessions_per_day'],
            'feed_per_session_kg': session_ration,
            'pellet_size_min_mm': profile['pellet_size_min_mm'],
            'pellet_size_max_mm': profile['pellet_size_max_mm'],
            'warnings': warnings,
            'automatic_recommendation_suspended': recommendation_suspended,
            'status': recommendation.status,
            'estimate_only': True}


@app.post('/farms/{farm_id}/feeding-recommendations/{recommendation_id}/approve', tags=['Feeding and inventory'])
def approve_feeding_recommendation(
    farm_id: int,
    recommendation_id: int,
    user: CurrentUser,
    db: Db,
):
    owned_farm(farm_id, user, db)
    item = db.scalar(select(FeedingRecommendation).where(
        FeedingRecommendation.id == recommendation_id,
        FeedingRecommendation.farm_id == farm_id,
    ))
    if item is None:
        raise HTTPException(404, 'Feeding recommendation not found')
    if item.status == 'suspended':
        raise HTTPException(409, 'Resolve the safety and data warnings before approving this recommendation')
    if item.status == 'approved':
        raise HTTPException(409, 'Feeding recommendation is already approved')
    item.status = 'approved'
    item.approved_by = user.id
    item.approved_at = now()
    audit(db, user, 'approve', 'feeding_recommendation', item.id, json.dumps({
        'profile_version': item.profile_version,
        'daily_ration_kg': item.daily_ration_kg,
    }))
    db.commit()
    return recommendation_view(item)


@app.get('/farms/{farm_id}/feeding-recommendations', tags=['Feeding and inventory'])
def list_feeding_recommendations(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    rows = db.scalars(select(FeedingRecommendation).where(
        FeedingRecommendation.farm_id == farm_id
    ).order_by(FeedingRecommendation.created_at.desc(), FeedingRecommendation.id.desc())).all()
    result = []
    for row in rows:
        sessions = db.scalars(select(FeedLedger).where(
            FeedLedger.recommendation_id == row.id,
            FeedLedger.event_type == 'feeding',
        ).order_by(FeedLedger.session_number, FeedLedger.id)).all()
        item = recommendation_view(row)
        item['actual_sessions'] = [{
            'session_number': entry.session_number,
            'actual_quantity_kg': round(abs(entry.quantity_delta_kg), 4),
            'occurred_on': entry.occurred_on,
            'evidence_id': entry.evidence_id,
        } for entry in sessions]
        item['actual_total_kg'] = round(sum(abs(entry.quantity_delta_kg) for entry in sessions), 4)
        result.append(item)
    return result


@app.get('/farms/{farm_id}/feed-forecast', tags=['Feeding and inventory'])
def feed_forecast(
    farm_id: int,
    user: CurrentUser,
    db: Db,
    forecast_days: int = Query(default=30, ge=1, le=180),
):
    owned_farm(farm_id, user, db)
    from .operations import StockingCycle
    from .main import ProductionUnit
    active_ids = db.scalars(select(StockingCycle.id).join(
        ProductionUnit, StockingCycle.unit_id == ProductionUnit.id
    ).where(ProductionUnit.farm_id == farm_id, StockingCycle.closed_at.is_(None))).all()
    active_cycle_ids = select(StockingCycle.id).join(
        ProductionUnit, StockingCycle.unit_id == ProductionUnit.id
    ).where(ProductionUnit.farm_id == farm_id, StockingCycle.closed_at.is_(None))
    recommendations = db.scalars(select(FeedingRecommendation).where(
        FeedingRecommendation.cycle_id.in_(active_cycle_ids),
        FeedingRecommendation.status == 'approved',
    ).order_by(FeedingRecommendation.created_at.desc(), FeedingRecommendation.id.desc())).all()
    latest_by_cycle = {}
    for item in recommendations:
        latest_by_cycle.setdefault(item.cycle_id, item)
    demand_by_feed: dict[int, float] = {}
    for cycle_id, item in latest_by_cycle.items():
        daily = item.daily_ration_kg
        demand_by_feed[item.feed_id] = demand_by_feed.get(item.feed_id, 0) + daily
    feeds = db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id)).all()
    projections = []
    for feed in feeds:
        daily_demand = demand_by_feed.get(feed.id, 0)
        current = stock(feed.id, db)
        projected = daily_demand * forecast_days
        projections.append({
            'feed_id': feed.id,
            'feed_name': feed.name,
            'current_stock_kg': current,
            'approved_daily_demand_kg': round(daily_demand, 4),
            'forecast_days': forecast_days,
            'expected_usage_kg': round(projected, 4),
            'projected_stock_kg': round(current - projected, 4),
            'days_until_shortage': round(current / daily_demand, 1) if daily_demand > 0 else None,
            'shortage_expected': daily_demand > 0 and current < projected,
        })
    return {
        'farm_id': farm_id,
        'forecast_days': forecast_days,
        'basis': 'Approved advisory recommendations; assumes current daily rations remain constant.',
        'feeds': projections,
        'cycles_without_approved_recommendation': [
            cycle_id for cycle_id in active_ids
            if cycle_id not in latest_by_cycle
        ],
    }


@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/fcr', tags=['Feeding and inventory'])
def cycle_fcr(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    total_feed = float(db.scalar(select(func.coalesce(func.sum(-FeedLedger.quantity_delta_kg), 0)).where(
        FeedLedger.cycle_id == cycle_id, FeedLedger.event_type == 'feeding')) or 0)
    pop = population(cycle, db)
    initial = cycle.stocked_count * cycle.initial_average_weight_g / 1000
    gain = pop.estimated_biomass_kg - initial
    return {'cycle_id': cycle_id, 'feed_consumed_kg': round(total_feed, 4),
            'initial_estimated_biomass_kg': round(initial, 4), 'current_estimated_biomass_kg': pop.estimated_biomass_kg,
            'estimated_biomass_gain_kg': round(gain, 4),
            'indicative_fcr': round(total_feed/gain, 4) if gain > 0 else None,
            'note': 'Indicative only: biomass uses latest sample and mortality estimates; not a verified harvest FCR.'}

@app.get('/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding-costs', tags=['Feeding and inventory'])
def feeding_costs(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    """Indicative historical purchase-average costs, not FIFO or lot-accurate costing."""
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    entries = db.scalars(select(FeedLedger).where(FeedLedger.cycle_id == cycle_id,
                         FeedLedger.event_type == 'feeding')).all()
    lines = []
    for feed_id in sorted({e.feed_id for e in entries}):
        feed_for_farm(farm_id, feed_id, user, db)
        receipts = db.scalars(select(FeedLedger).where(FeedLedger.feed_id == feed_id,
                              FeedLedger.event_type == 'receipt')).all()
        priced = [r for r in receipts if r.cost_ghs is not None]
        purchased_kg = sum(r.quantity_delta_kg for r in priced)
        avg_cost = sum(r.cost_ghs for r in priced) / purchased_kg if purchased_kg > 0 else None
        consumed = sum(-e.quantity_delta_kg for e in entries if e.feed_id == feed_id)
        lines.append({'feed_id': feed_id, 'consumed_kg': round(consumed, 4),
                      'average_purchase_cost_ghs_per_kg': round(avg_cost, 4) if avg_cost is not None else None,
                      'indicative_cost_ghs': round(consumed * avg_cost, 2) if avg_cost is not None else None})
    return {'cycle_id': cycle_id, 'currency': 'GHS', 'lines': lines,
            'total_indicative_cost_ghs': round(sum(x['indicative_cost_ghs'] for x in lines), 2) if all(x['indicative_cost_ghs'] is not None for x in lines) else None,
            'note': 'Historical purchase-average estimate; not lot-accurate, FIFO or a final financial statement.'}
