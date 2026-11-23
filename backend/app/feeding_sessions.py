"""Date-scoped feeding plans, skipped sessions and daily compliance summaries."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Date, ForeignKey, Text, UniqueConstraint, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .feeding import FEEDING_PROFILES, FeedLedger, FeedProduct, FeedingRecommendation, feeding_profile
from .main import Base, CurrentUser, Db, User, app, audit
from .operations import StockingCycle, owned_cycle, population

# Ghana uses UTC year-round.
GHANA = timezone.utc
ROOT = '/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding-sessions'


class OperationalFeedingSchedule(Base):
    __tablename__ = 'operational_feeding_schedules'
    __table_args__ = (UniqueConstraint('cycle_id', 'effective_on'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    effective_on: Mapped[date] = mapped_column(Date)
    windows_json: Mapped[str] = mapped_column(Text)


class DailyFeedingPlan(Base):
    __tablename__ = 'daily_feeding_plans'
    __table_args__ = (UniqueConstraint('cycle_id', 'fed_on', name='uq_daily_feeding_cycle_date'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'))
    fed_on: Mapped[date] = mapped_column(Date)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey('feeding_recommendations.id'))
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey('operational_feeding_schedules.id'))
    times_json: Mapped[str] = mapped_column(Text, default='{}')
    skipped_json: Mapped[str] = mapped_column(Text, default='{}')


class SkipSession(BaseModel):
    reason: str = Field(min_length=1, max_length=500, pattern=r'\S')


class SessionTimes(BaseModel):
    times: dict[int, time]
    ends: dict[int, time] = Field(default_factory=dict)


class ScheduleWindow(BaseModel):
    name: str = Field(min_length=1, max_length=60, pattern=r'\S')
    start: time
    end: time
    recommended_kg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    allocation_pct: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)


class ScheduleIn(BaseModel):
    effective_on: date
    sessions: list[ScheduleWindow] = Field(min_length=1, max_length=24)


class ReconcileSession(SkipSession):
    session_number: int = Field(ge=1)


def operational_schedule(db, cycle_id, day):
    return db.scalar(select(OperationalFeedingSchedule).where(
        OperationalFeedingSchedule.cycle_id == cycle_id,
        OperationalFeedingSchedule.effective_on <= day,
    ).order_by(OperationalFeedingSchedule.effective_on.desc()).limit(1))


def lock_cycle(db, cycle):
    db.execute(update(StockingCycle).where(StockingCycle.id == cycle.id).values(unit_id=StockingCycle.unit_id))


def get_plan(db, cycle_id, day):
    return db.scalar(select(DailyFeedingPlan).where(
        DailyFeedingPlan.cycle_id == cycle_id, DailyFeedingPlan.fed_on == day,
    ))


def recommended_plan(db, cycle_id, day, plan=None):
    if plan is not None:
        return db.get(FeedingRecommendation, plan.recommendation_id) if plan.recommendation_id else None
    # Prefer the recommendation already linked to this day's historical entries.
    historic = db.scalar(select(FeedLedger.recommendation_id).where(
        FeedLedger.cycle_id == cycle_id, FeedLedger.occurred_on == day,
        FeedLedger.event_type == 'feeding', FeedLedger.recommendation_id.is_not(None),
    ).order_by(FeedLedger.id).limit(1))
    if historic is not None:
        return db.get(FeedingRecommendation, historic)
    cutoff = datetime.combine(day + timedelta(days=1), time.min, GHANA)
    return db.scalar(select(FeedingRecommendation).where(
        FeedingRecommendation.cycle_id == cycle_id,
        FeedingRecommendation.status == 'approved',
        FeedingRecommendation.approved_at < cutoff,
    ).order_by(FeedingRecommendation.approved_at.desc(), FeedingRecommendation.id.desc()).limit(1))


def freeze_plan(db, cycle, day, recommendation_id=None):
    plan = get_plan(db, cycle.id, day)
    schedule = operational_schedule(db, cycle.id, day) if plan is None else None
    recommendation = recommended_plan(db, cycle.id, day, plan)
    if recommendation_id is not None and (recommendation is None or recommendation.id != recommendation_id):
        raise HTTPException(409, 'The daily recommendation changed. Refresh the session schedule.')
    if plan is None:
        if schedule is None and recommendation is None:
            raise HTTPException(409, 'Configure a feeding schedule for this date first')
        plan = DailyFeedingPlan(cycle_id=cycle.id, fed_on=day,
            recommendation_id=recommendation.id if recommendation else None,
            schedule_id=schedule.id if schedule else None,
            times_json=schedule.windows_json if schedule else '{}')
        db.add(plan)
        db.flush()
    return plan, recommendation


def frequency_advisory(db, cycle, active_count, effective_on):
    current = population(cycle, db)
    profile = feeding_profile(cycle.species, current.latest_average_weight_g)
    if profile is None:
        return None
    suggested = profile['sessions_per_day']
    next_band = next((
        (band['max_weight_g'], following['sessions_per_day'])
        for band, following in zip(FEEDING_PROFILES[profile['species']], FEEDING_PROFILES[profile['species']][1:])
        if band['max_weight_g'] >= current.latest_average_weight_g
        and band['sessions_per_day'] != following['sessions_per_day']
    ), None)
    return {
        'average_weight_g': current.latest_average_weight_g, 'sampled_on': current.latest_sampled_on,
        'active_sessions': active_count or None,
        'suggested_sessions': suggested, 'effective_on_if_approved': effective_on,
        'next_threshold_g': next_band[0] if next_band else None,
        'next_sessions': next_band[1] if next_band else None,
    }


def daily_summary(db, cycle, day, clock=None):
    current = clock or datetime.now(GHANA)
    plan = get_plan(db, cycle.id, day)
    recommendation = recommended_plan(db, cycle.id, day, plan)
    schedule = operational_schedule(db, cycle.id, day) if plan is None else None
    schedule_id = plan.schedule_id if plan else schedule.id if schedule else None
    times = json.loads(plan.times_json if plan else schedule.windows_json if schedule else '{}')
    skipped = json.loads(plan.skipped_json) if plan else {}
    from .evidence import RecordEvidence

    rows = db.execute(select(FeedLedger, FeedProduct.name, User.full_name, RecordEvidence.id, RecordEvidence.archived_at)
        .join(FeedProduct, FeedProduct.id == FeedLedger.feed_id)
        .outerjoin(User, User.id == FeedLedger.recorded_by)
        .outerjoin(RecordEvidence, (RecordEvidence.record_id == FeedLedger.id)
                   & (RecordEvidence.record_type == 'feeding') & (RecordEvidence.cycle_id == cycle.id))
        .where(FeedLedger.cycle_id == cycle.id, FeedLedger.occurred_on == day, FeedLedger.event_type == 'feeding')
        .order_by(FeedLedger.id, RecordEvidence.archived_at.desc().nulls_first(), RecordEvidence.id.desc()))
    entries = defaultdict(list)
    totals = defaultdict(Decimal)
    count = len(times) if schedule_id else recommendation.session_count if recommendation else 0
    seen = set()
    for row, product, recorder, evidence_id, archived in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        key = row.session_number if row.session_number and row.session_number <= count else None
        if not schedule_id and recommendation and row.recommendation_id != recommendation.id:
            key = None
        totals[key] -= Decimal(str(row.quantity_delta_kg))
        entries[key].append({
            'id': row.id, 'feed_name': product, 'actual_kg': -row.quantity_delta_kg,
            'recorder': recorder, 'recorded_by': row.recorded_by, 'actual_fed_at': row.actual_fed_at,
            'submitted_at': row.created_at, 'feeding_response': row.feeding_response, 'notes': row.notes,
            'on_time': None,
            'evidence_status': 'archived' if archived else 'uploaded' if evidence_id else 'missing', 'evidence_id': evidence_id,
        })
    sessions = []
    for number in range(1, count + 1):
        key = str(number)
        window = times.get(key)
        scheduled = window.get('start') if isinstance(window, dict) else window
        end_time = window.get('end') if isinstance(window, dict) else None
        deadline = datetime.combine(day + timedelta(days=1), time.min, GHANA)
        due_at = None
        if scheduled:
            due_at = datetime.combine(day, time.fromisoformat(scheduled), GHANA)
            deadline = datetime.combine(day, time.fromisoformat(end_time), GHANA) if end_time else min(deadline, due_at + timedelta(minutes=60))
        if entries[number]:
            state = 'recorded'
        elif key in skipped:
            state = 'skipped'
        elif current >= deadline:
            state = 'missed'
        elif due_at is not None and current >= due_at:
            state = 'due'
        else:
            state = 'upcoming'
        for entry in entries[number]:
            if entry['actual_fed_at'] and due_at is not None:
                actual_time = entry['actual_fed_at'].replace(tzinfo=GHANA) if entry['actual_fed_at'].tzinfo is None else entry['actual_fed_at']
                entry['on_time'] = due_at <= actual_time < deadline
        allocation = window.get('recommended_kg') if isinstance(window, dict) else None
        percentage = window.get('allocation_pct') if isinstance(window, dict) else None
        if percentage is not None and recommendation:
            allocation = round(recommendation.daily_ration_kg * percentage / 100, 6)
        elif allocation is None and recommendation and schedule_id:
            allocation = round(recommendation.daily_ration_kg / count, 6)
        elif allocation is None and recommendation:
            allocation = recommendation.session_ration_kg
        sessions.append({
            'number': number, 'name': window.get('name') if isinstance(window, dict) else None, 'scheduled_time': scheduled, 'scheduled_end': end_time,
            'deadline': deadline, 'status': state, 'skip': skipped.get(key),
            'recommended_kg': allocation,
            'entries': entries[number], 'actual_kg': float(totals[number]),
        })
    total = sum(totals.values(), Decimal(0))
    recorded = sum(row['status'] == 'recorded' for row in sessions)
    ration = Decimal(str(recommendation.daily_ration_kg)) if recommendation else None
    if sessions and all(row['recommended_kg'] is not None for row in sessions) and schedule_id:
        ration = sum(Decimal(str(row['recommended_kg'])) for row in sessions)
    return {
        'schedule_id': schedule_id, 'schedule_frozen': plan is not None,
        'due_count': sum(row['status'] == 'due' for row in sessions),
        'upcoming_count': sum(row['status'] == 'upcoming' for row in sessions),
        'unscheduled_count': len(entries[None]),
        'date': day, 'timezone': 'Africa/Accra', 'recommendation_id': recommendation.id if recommendation else None,
        'recommended_feed_id': recommendation.feed_id if recommendation else None,
        'daily_ration_kg': float(ration) if ration is not None else None, 'actual_kg': float(total),
        'difference_kg': float(total - ration) if ration is not None else None,
        'remaining_kg': float(max(Decimal(0), ration - total)) if ration is not None else None,
        'scheduled_count': count, 'recorded_count': recorded,
        'skipped_count': sum(row['status'] == 'skipped' for row in sessions),
        'missed_count': sum(row['status'] == 'missed' for row in sessions),
        'pending_count': sum(row['status'] in ('upcoming', 'due') for row in sessions),
        'completion_pct': round(recorded / count * 100, 2) if count else None,
        'sessions': sessions, 'unassigned_entries': entries[None],
        'frequency_advisory': frequency_advisory(
            db, cycle, count, day + timedelta(days=1) if plan else day,
        ) if day == current.date() and cycle.closed_at is None else None,
    }


def validate_day(cycle, day):
    if day < cycle.stocked_on or day > datetime.now(GHANA).date():
        raise HTTPException(422, 'Choose a date between stocking and today')


@app.get(ROOT, tags=['Feeding and inventory'])
def feeding_sessions(farm_id: int, unit_id: int, cycle_id: int, day: date, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    validate_day(cycle, day)
    return daily_summary(db, cycle, day)


@app.get(ROOT + '/history', tags=['Feeding and inventory'])
def feeding_session_history(farm_id: int, unit_id: int, cycle_id: int, end: date, user: CurrentUser, db: Db, days: int = 7):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    validate_day(cycle, end)
    if not 1 <= days <= 31:
        raise HTTPException(422, 'Choose a history range of 1 to 31 days')
    first = max(cycle.stocked_on, end - timedelta(days=days - 1))
    summaries = [daily_summary(db, cycle, first + timedelta(days=offset)) for offset in range((end - first).days + 1)]
    counts = {key: sum(row[key] for row in summaries) for key in ('scheduled_count', 'recorded_count', 'missed_count', 'skipped_count', 'pending_count')}
    return {
        'days': summaries, **counts,
        'actual_kg': round(sum(row['actual_kg'] for row in summaries), 6),
        'recommended_kg': round(sum(row['daily_ration_kg'] or 0 for row in summaries), 6) if any(row['daily_ration_kg'] is not None for row in summaries) else None,
        'completion_pct': round(counts['recorded_count'] / counts['scheduled_count'] * 100, 2) if counts['scheduled_count'] else None,
    }


@app.put(ROOT + '/times', tags=['Feeding and inventory'])
def set_feeding_times(farm_id: int, unit_id: int, cycle_id: int, day: date, data: SessionTimes, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    if cycle.closed_at or day != datetime.now(GHANA).date():
        raise HTTPException(409, 'Set times for today on an active cycle')
    lock_cycle(db, cycle)
    plan, recommendation = freeze_plan(db, cycle, day)
    if plan.schedule_id is not None:
        raise HTTPException(409, 'Manage operational windows in Manage Feeding Schedule')
    summary = daily_summary(db, cycle, day)
    if summary['recorded_count'] or summary['skipped_count']:
        raise HTTPException(409, 'Times cannot change after recording or skipping a session')
    if any(number < 1 or number > recommendation.session_count or value.tzinfo for number, value in data.times.items()):
        raise HTTPException(422, 'Use valid session numbers and Ghana local times')
    if any(number not in data.times or end.tzinfo or end <= data.times[number] for number, end in data.ends.items()):
        raise HTTPException(422, 'Each window end must be later than its start on the same day')
    plan.times_json = json.dumps({
        number: {'start': value.strftime('%H:%M'), 'end': data.ends[number].strftime('%H:%M') if number in data.ends else None}
        for number, value in data.times.items()
    })
    audit(db, user, 'set_session_times', 'stocking_cycle', cycle_id, json.dumps({'date': str(day), 'times': json.loads(plan.times_json)}))
    db.commit()
    return daily_summary(db, cycle, day)


@app.post(ROOT + '/{session_number}/skip', tags=['Feeding and inventory'])
def skip_feeding_session(farm_id: int, unit_id: int, cycle_id: int, session_number: int, day: date, data: SkipSession, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    validate_day(cycle, day)
    if cycle.closed_at:
        raise HTTPException(409, 'Cycle is closed')
    lock_cycle(db, cycle)
    plan, recommendation = freeze_plan(db, cycle, day)
    summary = daily_summary(db, cycle, day)
    if not 1 <= session_number <= summary['scheduled_count']:
        raise HTTPException(422, 'Choose a valid session')
    if summary['sessions'][session_number - 1]['status'] in ('recorded', 'skipped'):
        raise HTTPException(409, 'Session already recorded or skipped')
    skipped = json.loads(plan.skipped_json)
    skipped[str(session_number)] = {'reason': data.reason.strip(), 'recorder': user.full_name,
                                    'recorded_by': user.id, 'submitted_at': datetime.now(GHANA).isoformat()}
    plan.skipped_json = json.dumps(skipped)
    audit(db, user, 'skip_feeding_session', 'stocking_cycle', cycle_id,
          json.dumps({'session': session_number, 'date': str(day), 'reason': data.reason.strip()}))
    db.commit()
    return daily_summary(db, cycle, day)


@app.get(ROOT + '/schedule', tags=['Feeding and inventory'])
def list_operational_schedules(farm_id: int, unit_id: int, cycle_id: int, user: CurrentUser, db: Db):
    owned_cycle(farm_id, unit_id, cycle_id, user, db)
    return [{'id': row.id, 'effective_on': row.effective_on, 'sessions': list(json.loads(row.windows_json).values())}
            for row in db.scalars(select(OperationalFeedingSchedule).where(
                OperationalFeedingSchedule.cycle_id == cycle_id,
            ).order_by(OperationalFeedingSchedule.effective_on.desc()))]


@app.put(ROOT + '/schedule', tags=['Feeding and inventory'])
def save_operational_schedule(farm_id: int, unit_id: int, cycle_id: int, data: ScheduleIn, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    lock_cycle(db, cycle)
    db.refresh(cycle)
    if cycle.closed_at or data.effective_on < max(cycle.stocked_on, datetime.now(GHANA).date()):
        raise HTTPException(422, 'Choose today or a future date on an active cycle')
    percentages = [window.allocation_pct for window in data.sessions if window.allocation_pct is not None]
    if percentages and (len(percentages) != len(data.sessions) or abs(sum(percentages)-100) > 0.000001
                        or any(window.recommended_kg is not None for window in data.sessions)):
        raise HTTPException(422, 'Enter percentages for all sessions totaling 100, or enter optional kilograms instead')
    windows = {}
    prior_end = None
    for number, window in enumerate(data.sessions, 1):
        if (window.start.tzinfo or window.end.tzinfo or window.start >= window.end
            or window.start.second or window.end.second or window.start.microsecond or window.end.microsecond
            or (prior_end is not None and window.start < prior_end)):
            raise HTTPException(422, 'Use ordered, non-overlapping same-day windows in Ghana time')
        windows[number] = {'name': window.name.strip(), 'start': window.start.strftime('%H:%M'),
                           'end': window.end.strftime('%H:%M'), 'recommended_kg': window.recommended_kg,
                           'allocation_pct': window.allocation_pct}
        prior_end = window.end
    if get_plan(db, cycle.id, data.effective_on):
        raise HTTPException(409, 'This date already has a saved session plan. Choose a later effective date.')
    schedule = db.scalar(select(OperationalFeedingSchedule).where(
        OperationalFeedingSchedule.cycle_id == cycle.id, OperationalFeedingSchedule.effective_on == data.effective_on,
    ))
    if schedule is None:
        schedule = OperationalFeedingSchedule(cycle_id=cycle.id, effective_on=data.effective_on)
        db.add(schedule)
    schedule.windows_json = json.dumps(windows)
    db.flush()
    audit(db, user, 'save_operational_feeding_schedule', 'stocking_cycle', cycle_id,
          json.dumps({'effective_on': str(data.effective_on), 'sessions': windows}))
    db.commit()
    return {'id': schedule.id, 'effective_on': schedule.effective_on}


@app.post(ROOT + '/reconcile/{entry_id}', tags=['Feeding and inventory'])
def reconcile_feeding(farm_id: int, unit_id: int, cycle_id: int, entry_id: int,
                      data: ReconcileSession, user: CurrentUser, db: Db):
    cycle = owned_cycle(farm_id, unit_id, cycle_id, user, db)
    lock_cycle(db, cycle)
    entry = db.scalar(select(FeedLedger).where(FeedLedger.id == entry_id, FeedLedger.cycle_id == cycle.id,
                                              FeedLedger.event_type == 'feeding'))
    if entry is None:
        raise HTTPException(404, 'Feeding entry unavailable')
    if entry.session_number is not None or entry.actual_fed_at is None:
        raise HTTPException(409, 'Choose an unscheduled entry with a recorded feeding time')
    plan, _ = freeze_plan(db, cycle, entry.occurred_on)
    validate_session(db, cycle, entry.occurred_on, data.session_number, entry.actual_fed_at, plan, require_window=True)
    entry.session_number = data.session_number
    entry.recommendation_id = plan.recommendation_id
    audit(db, user, 'reconcile_feeding_session', 'feeding', entry.id,
          json.dumps({'session': data.session_number, 'date': str(entry.occurred_on), 'reason': data.reason.strip()}))
    db.commit()
    return daily_summary(db, cycle, entry.occurred_on)


def validate_session(db, cycle, day, session_number, actual, plan, require_window=False):
    sessions = daily_summary(db, cycle, day)['sessions']
    if not 1 <= session_number <= len(sessions):
        raise HTTPException(422, 'Choose a valid feeding session')
    row = sessions[session_number - 1]
    if row['status'] == 'skipped':
        raise HTTPException(409, 'This session was marked skipped')
    if plan.schedule_id is not None or require_window:
        if not row['scheduled_time']:
            raise HTTPException(422, 'Reconciliation requires a saved session window')
        if actual is None:
            raise HTTPException(422, 'Enter the actual feeding time')
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=GHANA)
        start = datetime.combine(day, time.fromisoformat(row['scheduled_time']), GHANA)
        if not start <= actual < row['deadline']:
            raise HTTPException(422, 'Actual feeding time is outside this session window. Record it as unscheduled.')
    return row


class DashboardFeedingIn(BaseModel):
    cycle_ids: list[int]
    start: date
    end: date
    forecast_days: int = Field(ge=1, le=180, default=7)
    until_harvest: bool = False


@app.post('/farms/{farm_id}/dashboard/production-feeding', tags=['Dashboard and reporting'])
def dashboard_production_feeding(farm_id: int, data: DashboardFeedingIn, user: CurrentUser, db: Db):
    from .main import ProductionUnit, owned_farm
    from .feeding import stock

    owned_farm(farm_id, user, db)
    today = datetime.now(GHANA).date()
    if data.end > today or data.end < data.start or (data.end - data.start).days > 30:
        raise HTTPException(422, 'Choose a period of up to 31 days ending today or earlier')
    cycle_ids = set(data.cycle_ids)
    cycles = db.execute(select(StockingCycle, ProductionUnit.is_active).join(
        ProductionUnit, ProductionUnit.id == StockingCycle.unit_id,
    ).where(ProductionUnit.farm_id == farm_id, StockingCycle.id.in_(cycle_ids))).all()
    if {cycle.id for cycle, _ in cycles} != cycle_ids:
        raise HTTPException(404, 'A selected cycle is unavailable')

    products = {feed.id: feed.name for feed in db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id))}
    forecasts = defaultdict(float)
    results = []
    for cycle, unit_active in cycles:
        active = unit_active and cycle.closed_at is None
        first = max(data.start, cycle.stocked_on)
        last = min(data.end, cycle.closed_at.date()) if cycle.closed_at else data.end
        days = [daily_summary(db, cycle, first + timedelta(days=offset))
                for offset in range((last - first).days + 1)]
        todays = (days[-1] if days and last == today else daily_summary(db, cycle, today)) if active else None
        latest = db.scalar(select(FeedingRecommendation).where(
            FeedingRecommendation.cycle_id == cycle.id,
        ).order_by(FeedingRecommendation.created_at.desc(), FeedingRecommendation.id.desc()).limit(1)) if active else None
        approved = db.get(FeedingRecommendation, todays['recommendation_id']) if todays and todays['recommendation_id'] else None
        period_rations = [day['daily_ration_kg'] for day in days if day['daily_ration_kg'] is not None]
        period_actual = round(sum(day['actual_kg'] for day in days), 6)
        applicable_actual = sum(day['actual_kg'] for day in days if day['daily_ration_kg'] is not None)
        counts = {key: sum(day[key] for day in days) for key in
                  ('scheduled_count', 'recorded_count', 'skipped_count', 'missed_count', 'pending_count')}
        period_recommended = round(sum(period_rations), 6) if period_rations else None
        forecast_end = cycle.expected_harvest_on if data.until_harvest else today + timedelta(days=data.forecast_days)
        horizon = (forecast_end - today).days if forecast_end else 0
        requirement = None
        if approved and horizon > 0 and (latest is None or latest.status != 'suspended'):
            requirement = round(approved.daily_ration_kg * horizon, 6)
            forecasts[approved.feed_id] += requirement
        results.append({
            'cycle_id': cycle.id, 'today': todays,
            'recommendation': {
                'status': latest.status, 'date': latest.approved_at or latest.created_at,
                'daily_kg': latest.daily_ration_kg, 'sessions': latest.session_count,
                'session_kg': latest.session_ration_kg, 'biomass_kg': latest.estimated_biomass_kg,
                'feed_name': products.get(latest.feed_id), 'warnings': json.loads(latest.warnings_json),
            } if latest else None,
            'period': {**counts, 'actual_kg': period_actual, 'recommended_kg': period_recommended,
                       'covered_days': len(period_rations), 'cycle_days': len(days),
                       'difference_kg': round(applicable_actual - period_recommended, 6) if period_recommended is not None else None,
                       'completion_pct': round(counts['recorded_count'] / counts['scheduled_count'] * 100, 2)
                       if counts['scheduled_count'] else None},
            'forecast': {'start': today + timedelta(days=1), 'end': forecast_end,
                         'quantity_kg': requirement, 'feed_id': approved.feed_id if approved else None},
        })
    balances = []
    for feed_id, required in forecasts.items():
        available = stock(feed_id, db)
        latest_stock = db.scalar(select(FeedLedger.occurred_on).where(
            FeedLedger.feed_id == feed_id,
        ).order_by(FeedLedger.occurred_on.desc(), FeedLedger.id.desc()).limit(1))
        balances.append({'feed_id': feed_id, 'feed_name': products.get(feed_id), 'stock_kg': available,
                         'required_kg': round(required, 6), 'balance_kg': round(available - required, 6),
                         'last_stock_record_on': latest_stock})
    return {'cycles': results, 'balances': balances}
