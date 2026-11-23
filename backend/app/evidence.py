"""Private video evidence attached to farmer daily-operation records."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import uuid
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from .main import Base, app, Db, CurrentUser, ProductionUnit, User, audit, owned_farm
from .operations import FishSample, Mortality, StockingCycle, WaterQuality, owned_cycle, has_supervisor_access
from .feeding import FeedLedger

MAX_VIDEO_BYTES = 30 * 1024 * 1024
RecordType = Literal[
    'feeding', 'mortality', 'water_quality', 'growth', 'stocking',
    'feed_delivery', 'feed_stock_count', 'fish_transfer', 'treatment',
    'inspection', 'harvest', 'sale_dispatch',
]
DEFAULT_REQUIRED_ACTIVITIES = [
    'feeding', 'growth', 'mortality', 'water_quality', 'stocking',
    'feed_delivery', 'feed_stock_count', 'fish_transfer', 'treatment',
    'inspection', 'harvest', 'sale_dispatch',
]
DEFAULT_CHALLENGE_ACTIVITIES = [
    'feeding', 'growth', 'mortality', 'stocking', 'feed_stock_count',
    'fish_transfer', 'harvest', 'treatment',
]


def now():
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evidence_directory() -> Path:
    configured = os.getenv('AQUAFARM_EVIDENCE_DIR')
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / 'private_evidence'


class RecordEvidence(Base):
    __tablename__ = 'record_evidence'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'), index=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey('stocking_cycles.id'), nullable=True, index=True)
    record_type: Mapped[str] = mapped_column(String(30))
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_name: Mapped[str] = mapped_column(String(80), unique=True)
    media_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    server_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offline_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geofence_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    activity_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    challenge_id: Mapped[int | None] = mapped_column(ForeignKey('activity_challenges.id'), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default='pending')
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvidencePolicy(Base):
    __tablename__ = 'farm_evidence_policies'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), unique=True)
    required_activities: Mapped[str] = mapped_column(Text)
    challenge_activities: Mapped[str] = mapped_column(Text)
    geofence_radius_m: Mapped[float] = mapped_column(Float, default=500)
    max_gps_accuracy_m: Mapped[float] = mapped_column(Float, default=100)
    max_offline_delay_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    updated_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActivityChallenge(Base):
    __tablename__ = 'activity_challenges'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'))
    unit_id: Mapped[int] = mapped_column(ForeignKey('production_units.id'))
    activity_type: Mapped[str] = mapped_column(String(30))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceAttach(BaseModel):
    record_id: int = Field(gt=0)


class EvidenceReviewIn(BaseModel):
    verification_status: Literal['verified', 'flagged']
    notes: str = Field(min_length=5, max_length=2000)


class CorrectionRequestIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class EvidencePolicyIn(BaseModel):
    required_activities: list[RecordType] = Field(min_length=1)
    challenge_activities: list[RecordType] = Field(default_factory=list)
    geofence_radius_m: float = Field(gt=0, le=50000)
    max_gps_accuracy_m: float = Field(gt=0, le=1000)
    max_offline_delay_seconds: int = Field(ge=0, le=604800)

    @model_validator(mode='after')
    def challenges_must_require_video(self):
        if not set(self.challenge_activities).issubset(self.required_activities):
            raise ValueError('Challenge activities must also require video evidence')
        return self


class ChallengeIn(BaseModel):
    unit_id: int = Field(gt=0)
    activity_type: RecordType


def evidence_view(item: RecordEvidence):
    return {
        'id': item.id,
        'farm_id': item.farm_id,
        'unit_id': item.unit_id,
        'cycle_id': item.cycle_id,
        'record_type': item.record_type,
        'record_id': item.record_id,
        'media_type': item.media_type,
        'size_bytes': item.size_bytes,
        'duration_seconds': item.duration_seconds,
        'latitude': item.latitude,
        'longitude': item.longitude,
        'gps_accuracy_m': item.gps_accuracy_m,
        'captured_at': item.captured_at,
        'device_recorded_at': item.device_recorded_at,
        'server_received_at': item.server_received_at or item.created_at,
        'offline_delay_seconds': item.offline_delay_seconds,
        'geofence_distance_m': item.geofence_distance_m,
        'geofence_status': item.geofence_status,
        'activity_reference': item.activity_reference,
        'sha256': item.sha256,
        'verification_status': item.verification_status,
        'verification_notes': item.verification_notes,
        'verified_by': item.verified_by,
        'verified_at': item.verified_at,
        'archived_at': item.archived_at,
        'created_at': item.created_at,
    }


def policy_for_farm(db, farm_id: int):
    policy = db.scalar(select(EvidencePolicy).where(EvidencePolicy.farm_id == farm_id))
    if policy is None:
        return {
            'required_activities': DEFAULT_REQUIRED_ACTIVITIES,
            'challenge_activities': DEFAULT_CHALLENGE_ACTIVITIES,
            'geofence_radius_m': 500.0,
            'max_gps_accuracy_m': 100.0,
            'max_offline_delay_seconds': 86400,
        }
    return {
        'required_activities': json.loads(policy.required_activities),
        'challenge_activities': json.loads(policy.challenge_activities),
        'geofence_radius_m': policy.geofence_radius_m,
        'max_gps_accuracy_m': policy.max_gps_accuracy_m,
        'max_offline_delay_seconds': policy.max_offline_delay_seconds,
    }


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def attach_record_evidence(
    db,
    evidence_id: int,
    farm_id: int,
    unit_id: int,
    cycle_id: int | None,
    record_type: str,
    record_id: int,
    user: User,
):
    item = db.scalar(select(RecordEvidence).where(
        RecordEvidence.id == evidence_id,
        RecordEvidence.farm_id == farm_id,
        RecordEvidence.unit_id == unit_id,
        RecordEvidence.record_type == record_type,
    ))
    if item is None:
        raise HTTPException(422, 'Required video evidence does not match this farm, unit, cycle, or activity')
    if item.cycle_id not in (None, cycle_id):
        raise HTTPException(422, 'Required video evidence is linked to a different stocking cycle')
    if item.record_id is not None or item.archived_at is not None:
        raise HTTPException(409, 'Video evidence has already been used or archived')
    item.cycle_id = cycle_id
    item.record_id = record_id
    audit(db, user, 'attach', 'record_evidence', item.id, json.dumps({
        'record_type': record_type,
        'record_id': record_id,
    }))
    return item


def get_evidence(farm_id: int, evidence_id: int, user, db):
    if not has_supervisor_access(farm_id, user, db):
        raise HTTPException(404, 'Farm not found')
    item = db.scalar(select(RecordEvidence).where(
        RecordEvidence.id == evidence_id, RecordEvidence.farm_id == farm_id
    ))
    if item is None:
        raise HTTPException(404, 'Video evidence not found')
    return item


@app.post('/farms/{farm_id}/evidence', status_code=201, tags=['Daily farm operations'])
async def upload_evidence(
    farm_id: int,
    request: Request,
    user: CurrentUser,
    db: Db,
    unit_id: int,
    record_type: RecordType,
    unit_tag: str,
    captured_at: datetime,
    device_recorded_at: datetime,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    gps_accuracy_m: float = Query(gt=0, le=1000),
    cycle_id: int | None = None,
    duration_seconds: int = Query(15),
    challenge_id: int | None = None,
    challenge_code: str | None = None,
):
    farm = owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit).where(
        ProductionUnit.id == unit_id,
        ProductionUnit.farm_id == farm_id,
        ProductionUnit.is_active.is_(True),
    ))
    if unit is None:
        raise HTTPException(404, 'Production unit not found')
    if not hmac.compare_digest(unit.evidence_tag, unit_tag):
        raise HTTPException(422, 'Scan or enter the correct physical unit tag')
    cycle = None
    if cycle_id is not None:
        cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
        if cycle.closed_at is not None:
            raise HTTPException(409, 'Video evidence requires an active stocking cycle')
    elif record_type not in ('stocking', 'feed_delivery', 'feed_stock_count', 'inspection'):
        raise HTTPException(422, 'This activity requires an active stocking cycle')
    if duration_seconds != 15:
        raise HTTPException(422, 'Daily-operation video must be 15 seconds')
    if captured_at.tzinfo is None or device_recorded_at.tzinfo is None:
        raise HTTPException(422, 'Capture and device timestamps must include a timezone')

    policy = policy_for_farm(db, farm_id)
    if record_type not in policy['required_activities']:
        raise HTTPException(422, 'Video evidence is not enabled for this activity')
    challenge = None
    if record_type in policy['challenge_activities']:
        if challenge_id is None or not challenge_code:
            raise HTTPException(422, 'A current one-time activity challenge is required')
        challenge = db.scalar(select(ActivityChallenge).where(
            ActivityChallenge.id == challenge_id,
            ActivityChallenge.farm_id == farm_id,
            ActivityChallenge.unit_id == unit_id,
            ActivityChallenge.activity_type == record_type,
            ActivityChallenge.consumed_at.is_(None),
        ))
        if (
            challenge is None
            or as_utc(challenge.expires_at) < now()
            or as_utc(challenge.issued_at) > as_utc(captured_at)
        ):
            raise HTTPException(422, 'Activity challenge is expired, used, or out of scope')
        supplied_hash = hashlib.sha256(challenge_code.encode('utf-8')).hexdigest()
        if not hmac.compare_digest(challenge.code_hash, supplied_hash):
            raise HTTPException(422, 'Activity challenge code does not match')

    boundary_lat = unit.latitude if unit.latitude is not None else farm.latitude
    boundary_lon = unit.longitude if unit.longitude is not None else farm.longitude
    if boundary_lat is None or boundary_lon is None:
        raise HTTPException(409, 'Set GPS coordinates for the farm or unit before recording evidence')
    measured_distance = distance_m(boundary_lat, boundary_lon, latitude, longitude)
    received_at = now()
    offline_delay = max(0, int((received_at - captured_at.astimezone(timezone.utc)).total_seconds()))
    geofence_status = 'within_radius'
    findings = []
    if gps_accuracy_m > policy['max_gps_accuracy_m']:
        geofence_status = 'poor_accuracy'
        findings.append('Reported GPS accuracy exceeds the farm policy limit.')
    if measured_distance > policy['geofence_radius_m'] + gps_accuracy_m:
        geofence_status = 'outside_radius'
        findings.append('Capture coordinates are outside the configured farm geofence.')
    if offline_delay > policy['max_offline_delay_seconds']:
        geofence_status = 'late_upload'
        findings.append('Upload delay exceeds the configured offline evidence window.')
    if captured_at.astimezone(timezone.utc) > received_at.replace(microsecond=0):
        findings.append('Device capture time is ahead of server receipt time.')
    if findings:
        geofence_status = 'flagged'

    media_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if media_type not in ('video/webm', 'video/mp4'):
        raise HTTPException(415, 'Upload a WebM or MP4 video')
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > MAX_VIDEO_BYTES:
                raise HTTPException(413, 'Video exceeds the 30 MB size limit')
        except ValueError as error:
            raise HTTPException(400, 'Invalid content length') from error

    root = evidence_directory()
    root.mkdir(parents=True, exist_ok=True)
    suffix = '.webm' if media_type == 'video/webm' else '.mp4'
    storage_name = f'{uuid.uuid4().hex}{suffix}'
    path = root / storage_name
    total = 0
    digest = hashlib.sha256()
    try:
        with path.open('xb') as video_file:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(413, 'Video exceeds the 30 MB size limit')
                digest.update(chunk)
                video_file.write(chunk)
        if total == 0:
            raise HTTPException(400, 'Video recording is empty')
        with path.open('rb') as video_file:
            header = video_file.read(12)
        valid_header = header.startswith(b'\x1a\x45\xdf\xa3') if media_type == 'video/webm' else header[4:8] == b'ftyp'
        if not valid_header:
            raise HTTPException(415, 'Video file content does not match its media type')
        sha256 = digest.hexdigest()
        if db.scalar(select(RecordEvidence.id).where(
            RecordEvidence.farm_id == farm_id,
            RecordEvidence.sha256 == sha256,
        )) is not None:
            raise HTTPException(409, 'Duplicate video evidence already exists for this farm')
        item = RecordEvidence(
            farm_id=farm_id,
            unit_id=unit_id,
            cycle_id=cycle_id,
            record_type=record_type,
            storage_name=storage_name,
            media_type=media_type,
            size_bytes=total,
            duration_seconds=15,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy_m=gps_accuracy_m,
            captured_at=captured_at.astimezone(timezone.utc),
            device_recorded_at=device_recorded_at.astimezone(timezone.utc),
            server_received_at=received_at,
            offline_delay_seconds=offline_delay,
            geofence_distance_m=round(measured_distance, 2),
            geofence_status=geofence_status,
            activity_reference=challenge_code,
            challenge_id=challenge.id if challenge is not None else None,
            sha256=sha256,
            verification_status='flagged' if findings else 'pending',
            verification_notes=' '.join(findings) or 'Duration is client-reported; supervisor must review the original clip.',
        )
        db.add(item)
        db.flush()
        if challenge is not None:
            challenge.consumed_at = received_at
        audit(db, user, 'create', 'record_evidence', item.id, json.dumps({
            'record_type': record_type,
            'cycle_id': cycle_id,
            'sha256': sha256,
            'geofence_status': geofence_status,
            'offline_delay_seconds': offline_delay,
        }))
        db.commit()
        db.refresh(item)
        return evidence_view(item)
    except Exception:
        if path.exists():
            path.unlink()
        raise


@app.post('/farms/{farm_id}/evidence-challenges', tags=['Evidence verification'])
def create_activity_challenge(farm_id: int, data: ChallengeIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    unit = db.scalar(select(ProductionUnit).where(
        ProductionUnit.id == data.unit_id,
        ProductionUnit.farm_id == farm_id,
        ProductionUnit.is_active.is_(True),
    ))
    if unit is None:
        raise HTTPException(404, 'Production unit not found')
    policy = policy_for_farm(db, farm_id)
    if data.activity_type not in policy['challenge_activities']:
        raise HTTPException(422, 'This activity does not require an activity challenge')
    code = secrets.token_hex(3).upper()
    issued_at = now()
    challenge = ActivityChallenge(
        farm_id=farm_id,
        unit_id=unit.id,
        activity_type=data.activity_type,
        code_hash=hashlib.sha256(code.encode('utf-8')).hexdigest(),
        issued_by=user.id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=1),
    )
    db.add(challenge)
    db.flush()
    audit(db, user, 'issue', 'activity_challenge', challenge.id, json.dumps({
        'unit_id': unit.id,
        'activity_type': data.activity_type,
    }))
    db.commit()
    return {
        'id': challenge.id,
        'unit_id': unit.id,
        'activity_type': challenge.activity_type,
        'code': code,
        'issued_at': challenge.issued_at,
        'expires_at': challenge.expires_at,
        'expires_in_hours': 24,
    }


@app.get('/farms/{farm_id}/evidence-policy', tags=['Evidence verification'])
def get_evidence_policy(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    return policy_for_farm(db, farm_id)


@app.put('/farms/{farm_id}/evidence-policy', tags=['Evidence verification'])
def set_evidence_policy(farm_id: int, data: EvidencePolicyIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    policy = db.scalar(select(EvidencePolicy).where(EvidencePolicy.farm_id == farm_id))
    values = data.model_dump(exclude={'required_activities', 'challenge_activities'})
    if policy is None:
        policy = EvidencePolicy(
            farm_id=farm_id,
            required_activities=json.dumps(data.required_activities),
            challenge_activities=json.dumps(data.challenge_activities),
            updated_by=user.id,
            **values,
        )
        db.add(policy)
    else:
        for key, value in values.items():
            setattr(policy, key, value)
        policy.required_activities = json.dumps(data.required_activities)
        policy.challenge_activities = json.dumps(data.challenge_activities)
        policy.updated_by = user.id
        policy.updated_at = now()
    audit(db, user, 'update', 'evidence_policy', farm_id, json.dumps({
        'geofence_radius_m': data.geofence_radius_m,
        'max_gps_accuracy_m': data.max_gps_accuracy_m,
        'max_offline_delay_seconds': data.max_offline_delay_seconds,
    }))
    db.commit()
    return policy_for_farm(db, farm_id)


@app.get('/farms/{farm_id}/evidence-review', tags=['Evidence verification'])
def evidence_review_queue(
    farm_id: int,
    user: CurrentUser,
    db: Db,
    verification_status: Literal['pending', 'flagged', 'verified'] | None = None,
):
    if not has_supervisor_access(farm_id, user, db):
        raise HTTPException(404, 'Farm not found')
    query = select(RecordEvidence).where(
        RecordEvidence.farm_id == farm_id,
        RecordEvidence.archived_at.is_(None),
    )
    if verification_status is not None:
        query = query.where(RecordEvidence.verification_status == verification_status)
    rows = db.scalars(query.order_by(
        RecordEvidence.verification_status.desc(),
        RecordEvidence.created_at.desc(),
        RecordEvidence.id.desc(),
    )).all()
    return [evidence_view(item) for item in rows]


@app.post('/farms/{farm_id}/evidence/{evidence_id}/verification', tags=['Evidence verification'])
def verify_evidence(
    farm_id: int,
    evidence_id: int,
    data: EvidenceReviewIn,
    user: CurrentUser,
    db: Db,
):
    item = get_evidence(farm_id, evidence_id, user, db)
    if item.archived_at is not None:
        raise HTTPException(404, 'Video evidence not found')
    item.verification_status = data.verification_status
    item.verification_notes = data.notes
    item.verified_by = user.id
    item.verified_at = now()
    audit(db, user, 'verify', 'record_evidence', item.id, json.dumps({
        'verification_status': item.verification_status,
        'notes': item.verification_notes,
        'record_type': item.record_type,
        'record_id': item.record_id,
    }))
    db.commit()
    return evidence_view(item)


@app.post('/farms/{farm_id}/evidence/{evidence_id}/correction-requests', tags=['Evidence verification'])
def request_evidence_correction(
    farm_id: int,
    evidence_id: int,
    data: CorrectionRequestIn,
    user: CurrentUser,
    db: Db,
):
    item = get_evidence(farm_id, evidence_id, user, db)
    if item.record_id is None:
        raise HTTPException(409, 'Correction requests require evidence linked to an operational record')
    item.verification_status = 'flagged'
    item.verification_notes = f'Correction requested: {data.reason}'
    item.verified_by = user.id
    item.verified_at = now()
    audit(db, user, 'request_correction', 'record_evidence', item.id, json.dumps({
        'record_type': item.record_type,
        'record_id': item.record_id,
        'reason': data.reason,
    }))
    db.commit()
    return evidence_view(item)


@app.post('/farms/{farm_id}/evidence/{evidence_id}/attach', tags=['Daily farm operations'])
def attach_evidence(farm_id: int, evidence_id: int, data: EvidenceAttach, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    item = get_evidence(farm_id, evidence_id, user, db)
    if item.record_id is not None:
        raise HTTPException(409, 'Video evidence is already attached to a record')

    if item.record_type == 'feeding':
        exists = db.scalar(select(FeedLedger.id).where(
            FeedLedger.id == data.record_id,
            FeedLedger.cycle_id == item.cycle_id,
            FeedLedger.event_type == 'feeding',
        ))
    elif item.record_type == 'mortality':
        exists = db.scalar(select(Mortality.id).where(
            Mortality.id == data.record_id, Mortality.cycle_id == item.cycle_id,
        ))
    elif item.record_type == 'growth':
        exists = db.scalar(select(FishSample.id).where(
            FishSample.id == data.record_id, FishSample.cycle_id == item.cycle_id,
        ))
    else:
        exists = db.scalar(select(WaterQuality.id).where(
            WaterQuality.id == data.record_id, WaterQuality.unit_id == item.unit_id,
        ))
    if exists is None:
        raise HTTPException(404, 'Record does not match the farm, unit, cycle, and evidence type')

    item.record_id = data.record_id
    db.commit()
    return evidence_view(item)


@app.get('/farms/{farm_id}/evidence', tags=['Daily farm operations'])
def list_evidence(
    farm_id: int,
    user: CurrentUser,
    db: Db,
    cycle_id: int | None = None,
    record_type: RecordType | None = None,
):
    if not has_supervisor_access(farm_id, user, db):
        raise HTTPException(404, 'Farm not found')
    query = select(RecordEvidence).where(RecordEvidence.farm_id == farm_id)
    if cycle_id is not None:
        query = query.where(RecordEvidence.cycle_id == cycle_id)
    if record_type is not None:
        query = query.where(RecordEvidence.record_type == record_type)
    rows = db.scalars(query.order_by(RecordEvidence.created_at.desc(), RecordEvidence.id.desc())).all()
    return [evidence_view(item) for item in rows]


@app.get('/farms/{farm_id}/evidence/{evidence_id}/video', tags=['Daily farm operations'])
def download_evidence(farm_id: int, evidence_id: int, user: CurrentUser, db: Db):
    item = get_evidence(farm_id, evidence_id, user, db)
    path = evidence_directory() / item.storage_name
    if not path.is_file():
        raise HTTPException(404, 'Stored video evidence is missing')
    return FileResponse(path, media_type=item.media_type, filename=f'daily-record-{item.id}{path.suffix}',
                        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@app.delete('/farms/{farm_id}/evidence/{evidence_id}', status_code=204, tags=['Daily farm operations'])
def delete_evidence(farm_id: int, evidence_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    item = get_evidence(farm_id, evidence_id, user, db)
    if item.record_id is not None:
        raise HTTPException(409, 'Linked evidence is immutable and cannot be deleted')
    item.archived_at = now()
    audit(db, user, 'delete', 'record_evidence', item.id, f'{{"record_type":"{item.record_type}","record_id":{item.record_id or "null"}}}')
    db.commit()
