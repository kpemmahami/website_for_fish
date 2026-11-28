"""Platform-owner access to SMS transport diagnostics and delivery metadata."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .administration import require_platform_owner
from .main import Base, CurrentUser, Db, SessionLocal, app
from .phone_numbers import PhoneNumber
from .sms_gateway import (
    SmsDeliveryError, arkesel_balance, arkesel_delivery, arkesel_delivery_batch,
    configured_provider, sandbox_enabled, send_sandbox_test, validate_delivery_settings,
)
from .sms_outbox import MESSAGES, SmsOutbox, notifications_enabled

ROOT = '/admin/sms'
TAG = ['SMS Management']


class SmsDelivery(Base):
    __tablename__ = 'sms_deliveries'

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(16))
    message_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message_count: Mapped[int | None]
    provider_sent_at: Mapped[str | None] = mapped_column(String(19))
    operator_id: Mapped[int | None]


def record_delivery(category: str, state: str, message_id: str | None, operator_id: int | None = None):
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        db.add(SmsDelivery(category=category, state=state, message_id=message_id,
                           created_at=now, updated_at=now, operator_id=operator_id))


def view(row: SmsDelivery):
    return {field: getattr(row, field) for field in (
        'id', 'category', 'state', 'message_id', 'created_at', 'updated_at',
        'message_count', 'provider_sent_at', 'operator_id',
    )}


def provider_failure(error: SmsDeliveryError):
    return HTTPException(503, str(error))


@app.get(ROOT+'/gateway', tags=TAG)
def gateway(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    try:
        provider = configured_provider()
        sandbox = sandbox_enabled()
        validate_delivery_settings()
    except SmsDeliveryError as error:
        return {'ready': False, 'reason': str(error)}
    return {'ready': True, 'provider': provider, 'sandbox': sandbox}


@app.get(ROOT+'/balance', tags=TAG)
def balance(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    try:
        if validate_delivery_settings() != 'arkesel':
            raise SmsDeliveryError('Arkesel is not the configured SMS provider')
        return arkesel_balance()
    except SmsDeliveryError as error:
        raise provider_failure(error) from None


class SandboxTest(BaseModel):
    phone_number: PhoneNumber


@app.post(ROOT+'/sandbox-test', tags=TAG)
def sandbox_test(data: SandboxTest, user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    recent = db.scalar(select(func.count()).select_from(SmsDelivery).where(
        SmsDelivery.category == 'test', SmsDelivery.created_at >= datetime.now(timezone.utc)-timedelta(minutes=1),
    ))
    if recent >= 5:
        raise HTTPException(429, 'Too many sandbox tests')
    try:
        message_id = send_sandbox_test(data.phone_number)
    except SmsDeliveryError as error:
        record_delivery('test', error.state, None, user.id)
        raise provider_failure(error) from None
    record_delivery('test', 'sandbox', message_id, user.id)
    return {'state': 'sandbox', 'message_id': message_id}


@app.get(ROOT+'/history', tags=TAG)
def history(user: CurrentUser, db: Db, start: date | None = None, end: date | None = None,
            state: Literal['accepted', 'delivered', 'failed', 'sandbox', 'unknown'] | None = None,
            offset: int = Query(0, ge=0)):
    require_platform_owner(user, db)
    query = select(SmsDelivery).where(*date_conditions(start, end))
    if state:
        query = query.where(SmsDelivery.state == state)
    rows = db.scalars(query.order_by(SmsDelivery.id.desc()).offset(offset).limit(51)).all()
    return {'items': [view(row) for row in rows[:50]], 'has_more': len(rows) > 50}


def date_conditions(start: date | None, end: date | None):
    if start and end and start > end:
        raise HTTPException(422, 'Start date must be on or before end date')
    conditions = []
    if start:
        conditions.append(SmsDelivery.created_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
    if end and end != date.max:
        conditions.append(SmsDelivery.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc))
    return conditions


@app.get(ROOT+'/usage', tags=TAG)
def usage(user: CurrentUser, db: Db, start: date | None = None, end: date | None = None):
    require_platform_owner(user, db)
    states, categories, rate = delivery_totals(db, date_conditions(start, end))
    return {'requests': sum(states.values()), 'states': states, 'categories': categories, 'delivery_success_pct': rate}


@app.get(ROOT+'/summary', tags=TAG)
def summary(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    monthly, categories, rate = delivery_totals(db, [SmsDelivery.created_at >= month])
    requests_today = db.scalar(select(func.count()).select_from(SmsDelivery).where(SmsDelivery.created_at >= day))
    return {'requests_today': requests_today, 'requests_this_month': sum(monthly.values()),
            'states_this_month': monthly, 'categories_this_month': categories,
            'delivery_success_pct': rate}


def delivery_totals(db, conditions):
    states = dict(db.execute(select(SmsDelivery.state, func.count()).where(
        *conditions,
    ).group_by(SmsDelivery.state)).all())
    categories = dict(db.execute(select(SmsDelivery.category, func.count()).where(
        *conditions,
    ).group_by(SmsDelivery.category)).all())
    delivery_failures = db.scalar(select(func.count()).select_from(SmsDelivery).where(
        *conditions, SmsDelivery.state == 'failed', SmsDelivery.message_id.is_not(None),
    ))
    delivered = states.get('delivered', 0)
    terminal = delivered + delivery_failures
    return states, categories, round(delivered / terminal * 100, 2) if terminal else None


@app.get(ROOT+'/templates', tags=TAG)
def templates(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    return {'templates': [{'event': key, 'text': text} for key, text in MESSAGES.items()]}


@app.get(ROOT+'/scheduled', tags=TAG)
def scheduled(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    states = dict(db.execute(select(SmsOutbox.state, func.count()).group_by(SmsOutbox.state)).all())
    return {'outbox_states': states}


@app.get(ROOT+'/settings', tags=TAG)
def settings(user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    from .sms_gateway import env_flag
    return {
        'financial_notifications': notifications_enabled(),
        'daily_reminders': env_flag('AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED', False),
        'loan_reminders': env_flag('AQUAFARM_LOAN_REMINDERS_ENABLED', False),
    }


class DeliveryPoll(BaseModel):
    message_ids: list[UUID] = Field(min_length=1, max_length=50)


@app.post(ROOT+'/delivery-reports', tags=TAG)
def poll_delivery(data: DeliveryPoll, user: CurrentUser, db: Db):
    require_platform_owner(user, db)
    ids = list(dict.fromkeys(data.message_ids))
    rows = {row.message_id: row for row in db.scalars(select(SmsDelivery).where(
        SmsDelivery.message_id.in_([str(item) for item in ids]),
    ))}
    if len(rows) != len(ids):
        raise HTTPException(404, 'SMS delivery record not found')
    eligible = [item for item in ids if rows[str(item)].state in ('accepted', 'unknown')]
    reports = []
    try:
        if eligible:
            if validate_delivery_settings() != 'arkesel':
                raise SmsDeliveryError('Arkesel is not the configured SMS provider')
            reports = [arkesel_delivery(eligible[0])] if len(eligible) == 1 else arkesel_delivery_batch(eligible)
    except SmsDeliveryError as error:
        raise provider_failure(error) from None
    for report in reports:
        updated_at = datetime.now(timezone.utc)
        db.execute(update(SmsDelivery).where(
            SmsDelivery.message_id == report['message_id'], SmsDelivery.state.in_(('accepted', 'unknown')),
        ).values(state=report['state'], message_count=report['message_count'],
                 provider_sent_at=report['provider_sent_at'], updated_at=updated_at))
        db.execute(update(SmsOutbox).where(
            SmsOutbox.message_id == report['message_id'], SmsOutbox.state.in_(('accepted', 'unknown')),
        ).values(state=report['state'], updated_at=updated_at))
    db.commit()
    return {'items': [view(rows[str(item)]) for item in ids]}
