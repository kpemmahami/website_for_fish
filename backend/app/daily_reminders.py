"""Daily feeding-record status and opt-in SMS reminders."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
import logging
import os
from typing import Callable
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import HTTPException
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .feeding import FeedLedger
from .main import Base, CurrentUser, Db, Farm, SessionLocal, User, app, owned_farm
from .operations import ProductionUnit, StockingCycle
from .sms_gateway import SmsDeliveryError, configured_provider, env_flag, sandbox_enabled, send_sms, validate_delivery_settings

GHANA_TZ = ZoneInfo('Africa/Accra')
HUBTEL_URL = 'https://smsc.hubtel.com/v1/messages/send'
logger = logging.getLogger(__name__)


def send_farm_reminder(phone_number: str, message: str) -> str | None:
    return send_sms(phone_number, message, category='farm')


def send_loan_reminder(phone_number: str, message: str) -> str | None:
    return send_sms(phone_number, message, category='financial')


class DailyRecordReminder(Base):
    __tablename__ = 'daily_record_reminders'
    __table_args__ = (UniqueConstraint('user_id', 'reminder_date', name='uq_daily_reminder_user_date'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)
    missing_cycle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoanSmsReminder(Base):
    __tablename__ = 'loan_sms_reminders'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    loan_id: Mapped[int] = mapped_column(ForeignKey('loan_accounts.id'), index=True, nullable=False)
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def reminder_time() -> time:
    value = os.getenv('AQUAFARM_DAILY_RECORD_REMINDER_TIME', '08:00')
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError('AQUAFARM_DAILY_RECORD_REMINDER_TIME must use HH:MM') from error
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise RuntimeError('AQUAFARM_DAILY_RECORD_REMINDER_TIME must use HH:MM')
    return parsed


def local_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(GHANA_TZ)
    if current.tzinfo is None:
        return current.replace(tzinfo=GHANA_TZ)
    return current.astimezone(GHANA_TZ)


def daily_status(db, farm_id: int, at: datetime | None = None):
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, 'Farm not found')
    current = local_now(at)
    today = current.date()
    cutoff = reminder_time()
    cycles = db.execute(
        select(StockingCycle, ProductionUnit.name)
        .join(ProductionUnit, ProductionUnit.id == StockingCycle.unit_id)
        .where(
            ProductionUnit.farm_id == farm_id,
            ProductionUnit.is_active.is_(True),
            StockingCycle.closed_at.is_(None),
        )
        .order_by(StockingCycle.id)
    ).all()
    results = []
    for cycle, unit_name in cycles:
        has_record = db.scalar(
            select(FeedLedger.id).where(
                FeedLedger.cycle_id == cycle.id,
                FeedLedger.event_type == 'feeding',
                FeedLedger.occurred_on == today,
            ).limit(1)
        ) is not None
        is_overdue = not has_record and current.time().replace(tzinfo=None) >= cutoff
        results.append({
            'cycle_id': cycle.id,
            'unit_id': cycle.unit_id,
            'unit_name': unit_name,
            'species': cycle.species,
            'has_feeding_record': has_record,
            'is_overdue': is_overdue,
            'status': 'recorded' if has_record else 'missing' if is_overdue else 'due',
        })
    return {
        'farm_id': farm_id,
        'record_date': today,
        'required_record': 'feeding',
        'reminder_time': cutoff.strftime('%H:%M'),
        'timezone': 'Africa/Accra',
        'cycles': results,
    }


@app.get('/farms/{farm_id}/daily-record-status', tags=['Daily farm reminders'])
def get_daily_record_status(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    return daily_status(db, farm_id)


def hubtel_send_sms(phone_number: str, message: str) -> str | None:
    client_id = os.getenv('HUBTEL_CLIENT_ID', '').strip()
    client_secret = os.getenv('HUBTEL_CLIENT_SECRET', '').strip()
    sender_id = os.getenv('HUBTEL_SMS_SENDER_ID', '').strip()
    if not client_id or not client_secret or not sender_id:
        raise SmsDeliveryError('Hubtel credentials or sender ID are not configured')
    try:
        response = httpx.get(
            HUBTEL_URL,
            params={
                'clientid': client_id,
                'clientsecret': client_secret,
                'from': sender_id,
                'to': phone_number.lstrip('+'),
                'content': message,
            },
            timeout=15,
        )
    except httpx.HTTPError as error:
        raise SmsDeliveryError(f'Hubtel request failed ({type(error).__name__})') from None
    if not response.is_success:
        raise SmsDeliveryError(f'Hubtel returned HTTP {response.status_code}')
    try:
        result = response.json()
    except ValueError:
        raise SmsDeliveryError('Hubtel returned an invalid response') from None
    if not isinstance(result, dict):
        raise SmsDeliveryError('Hubtel returned an invalid response')
    provider_status = result.get('Status', result.get('status'))
    if provider_status is not None and str(provider_status).lower() not in ('0', 'success', 'accepted', 'ok', 'true'):
        raise SmsDeliveryError('Hubtel rejected the SMS request')
    message_id = result.get('MessageId', result.get('messageId', result.get('message_id')))
    return str(message_id)[:120] if message_id else None


def missing_cycle_ids(db, user_id: int, today: date) -> list[int]:
    feeding_exists = select(FeedLedger.id).where(
        FeedLedger.cycle_id == StockingCycle.id,
        FeedLedger.event_type == 'feeding',
        FeedLedger.occurred_on == today,
    ).exists()
    return list(db.scalars(
        select(StockingCycle.id)
        .join(ProductionUnit, ProductionUnit.id == StockingCycle.unit_id)
        .join(Farm, Farm.id == ProductionUnit.farm_id)
        .where(
            Farm.owner_id == user_id,
            Farm.archived_at.is_(None),
            ProductionUnit.is_active.is_(True),
            StockingCycle.closed_at.is_(None),
            ~feeding_exists,
        )
        .order_by(StockingCycle.id)
    ).all())


def reserve_reminder(db, user_id: int, today: date, count: int, at: datetime):
    reminder = db.scalar(select(DailyRecordReminder).where(
        DailyRecordReminder.user_id == user_id,
        DailyRecordReminder.reminder_date == today,
    ))
    if reminder is not None:
        if reminder.status != 'failed':
            return None
        reminder.status = 'sending'
        reminder.missing_cycle_count = count
        reminder.last_error = None
        reminder.created_at = at
    else:
        reminder = DailyRecordReminder(
            user_id=user_id,
            reminder_date=today,
            missing_cycle_count=count,
            status='sending',
            created_at=at,
        )
        db.add(reminder)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(DailyRecordReminder.id).where(
            DailyRecordReminder.user_id == user_id,
            DailyRecordReminder.reminder_date == today,
        ))
        if existing is not None:
            return None
        raise
    return reminder


def deliver_daily_record_reminders(
    db,
    at: datetime | None = None,
    sender: Callable[[str, str], str | None] = send_farm_reminder,
) -> int:
    current = local_now(at)
    cutoff = reminder_time()
    if current.time().replace(tzinfo=None) < cutoff:
        return 0
    today = current.date()
    users = db.scalars(select(User).where(
        User.sms_daily_records_enabled.is_(True),
        User.phone_number.is_not(None),
    ).order_by(User.id)).all()
    sent_count = 0
    for user in users:
        missing = missing_cycle_ids(db, user.id, today)
        if not missing:
            continue
        reminder = reserve_reminder(db, user.id, today, len(missing), current)
        if reminder is None:
            continue
        message = (
            f'AquaFarm reminder: no feeding record was entered today for '
            f'{len(missing)} active production cycle(s). Please record today\'s feeding.'
        )
        if not user.phone_number:
            reminder.status = 'failed'
            reminder.last_error = 'Opted-in user has no phone number'
            db.commit()
            logger.error('Daily SMS skipped for user_id=%s date=%s: opted-in user has no phone number', user.id, today)
            continue
        try:
            provider_id = sender(user.phone_number, message)
        except SmsDeliveryError as error:
            reminder.status = error.state
            reminder.last_error = str(error)[:120]
            db.commit()
            logger.error('Daily SMS failed for user_id=%s date=%s: %s', user.id, today, error)
            continue
        reminder.status = 'sent'
        reminder.provider_message_id = provider_id
        reminder.sent_at = current.astimezone(timezone.utc)
        reminder.last_error = None
        db.commit()
        sent_count += 1
    return sent_count


def reserve_loan_reminder(db, user_id: int, loan_id: int, installment_number: int,
                          reminder_key: str, reminder_type: str, today: date, at: datetime):
    reminder = db.scalar(select(LoanSmsReminder).where(LoanSmsReminder.reminder_key == reminder_key))
    if reminder is not None:
        claimed = db.execute(update(LoanSmsReminder).where(
            LoanSmsReminder.id == reminder.id, LoanSmsReminder.status == 'failed',
        ).values(status='sending', last_error=None, created_at=at))
        if claimed.rowcount != 1:
            return None
    else:
        reminder = LoanSmsReminder(
            user_id=user_id,
            loan_id=loan_id,
            installment_number=installment_number,
            reminder_key=reminder_key,
            reminder_type=reminder_type,
            reminder_date=today,
            status='sending',
            created_at=at,
        )
        db.add(reminder)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(LoanSmsReminder.id).where(LoanSmsReminder.reminder_key == reminder_key)) is not None:
            return None
        raise
    return reminder


def deliver_loan_sms_reminders(
    db,
    at: datetime | None = None,
    sender: Callable[[str, str], str | None] = send_loan_reminder,
    *, monthly: bool = False,
) -> int:
    from .loan_servicing import LoanAccount, LoanInstallment, LoanRepayment

    current = local_now(at)
    today = current.date()
    upcoming_cutoff = (today.replace(day=monthrange(today.year, today.month)[1])
                       if monthly else today + timedelta(days=7))
    eligibility = (User.phone_verified_at.is_not(None), User.is_suspended.is_(False)) if monthly else ()
    users = db.scalars(select(User).where(
        User.sms_loan_reminders_enabled.is_(True),
        User.phone_number.is_not(None),
        *eligibility,
    ).order_by(User.id)).all()
    sent_count = 0
    for user in users:
        loans = db.scalars(
            select(LoanAccount)
            .join(Farm, Farm.id == LoanAccount.farm_id)
            .where(
                Farm.owner_id == user.id,
                Farm.archived_at.is_(None),
                LoanAccount.status == 'active',
            )
            .order_by(LoanAccount.id)
        ).all()
        for loan in loans:
            paid = db.scalar(select(
                func.coalesce(func.sum(LoanRepayment.amount_pesewas), 0)
            ).where(LoanRepayment.loan_id == loan.id)) or 0
            cumulative_due = 0
            previous_unpaid = 0
            installments = db.scalars(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.number)
            ).all()
            for installment in installments:
                cumulative_due += (
                    installment.principal_pesewas
                    + installment.interest_pesewas
                    + installment.fees_pesewas
                )
                unpaid_to_date = max(0, cumulative_due - paid)
                installment_unpaid = max(0, unpaid_to_date - previous_unpaid)
                previous_unpaid = unpaid_to_date
                if installment_unpaid <= 0:
                    continue
                if monthly and installment.due_on <= upcoming_cutoff:
                    reminder_type = 'monthly'
                    key = f'monthly:{user.id}:{today:%Y-%m}'
                elif monthly:
                    continue
                elif installment.due_on < today:
                    reminder_type = 'overdue'
                    key = f'overdue:{loan.id}:{installment.number}:{today.isoformat()}'
                elif installment.due_on <= upcoming_cutoff:
                    reminder_type = 'upcoming'
                    key = f'upcoming:{loan.id}:{installment.number}'
                else:
                    continue
                reminder = reserve_loan_reminder(
                    db, user.id, loan.id, installment.number, key,
                    reminder_type, today, current,
                )
                if reminder is None:
                    continue
                if not user.phone_number:
                    reminder.status = 'failed'
                    reminder.last_error = 'Opted-in user has no phone number'
                    db.commit()
                    continue
                if monthly:
                    message = ('AquaFarm monthly loan reminder: please review your repayment schedule '
                               'in AquaFarm or contact your financial institution about payments due.')
                elif reminder_type == 'overdue':
                    message = (
                        f'AquaFarm loan reminder: instalment {installment.number} on loan '
                        f'{loan.id} was due {installment.due_on.isoformat()} and is overdue. '
                        'Please contact your financial institution.'
                    )
                else:
                    message = (
                        f'AquaFarm loan reminder: instalment {installment.number} on loan '
                        f'{loan.id} is due {installment.due_on.isoformat()}. Please plan your payment.'
                    )
                try:
                    provider_id = sender(user.phone_number, message)
                except SmsDeliveryError as error:
                    reminder.status = error.state
                    reminder.last_error = str(error)[:120]
                    db.commit()
                    logger.error('Loan SMS failed for user_id=%s loan_id=%s: %s', user.id, loan.id, error)
                    continue
                reminder.status = 'sent'
                reminder.provider_message_id = provider_id
                reminder.sent_at = current.astimezone(timezone.utc)
                reminder.last_error = None
                db.commit()
                sent_count += 1
                if monthly:
                    break
    return sent_count


def scheduled_delivery():
    daily_enabled = os.getenv('AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    loans_enabled = os.getenv('AQUAFARM_LOAN_REMINDERS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    with SessionLocal() as db:
        if daily_enabled:
            deliver_daily_record_reminders(db)
        if loans_enabled:
            mode = os.getenv('AQUAFARM_LOAN_REMINDER_MODE', 'installment').strip().lower()
            deliver_loan_sms_reminders(db, monthly=mode == 'monthly')


_scheduler: BackgroundScheduler | None = None


def start_daily_reminder_scheduler():
    from .sms_outbox import deliver_outbox, notifications_enabled

    global _scheduler
    daily_enabled = os.getenv('AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    loans_enabled = os.getenv('AQUAFARM_LOAN_REMINDERS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    financial_enabled = notifications_enabled()
    if not daily_enabled and not loans_enabled and not financial_enabled:
        logger.info('Scheduled SMS reminders are disabled; in-app reminders remain available.')
        return
    if not env_flag('SMS_ENABLED', configured_provider() == 'hubtel') or sandbox_enabled():
        logger.info('Scheduled SMS reminders are paused by gateway configuration.')
        return
    validate_delivery_settings()
    if loans_enabled and os.getenv('AQUAFARM_LOAN_REMINDER_MODE', 'installment').strip().lower() not in ('installment', 'monthly'):
        raise RuntimeError('AQUAFARM_LOAN_REMINDER_MODE must be installment or monthly')
    cutoff = reminder_time()
    _scheduler = BackgroundScheduler(timezone=GHANA_TZ)
    if financial_enabled:
        _scheduler.add_job(deliver_outbox, 'interval', minutes=1,
                           id='financial-sms-outbox', coalesce=True, max_instances=1)
    _scheduler.add_job(
        scheduled_delivery,
        CronTrigger(hour=cutoff.hour, minute=cutoff.minute, timezone=GHANA_TZ),
        id='farm-and-loan-sms-reminders',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    if local_now().time().replace(tzinfo=None) >= cutoff:
        _scheduler.add_job(
            scheduled_delivery,
            'date',
            run_date=local_now() + timedelta(seconds=5),
            id='farm-and-loan-sms-reminders-startup-catchup',
            replace_existing=True,
        )


def stop_daily_reminder_scheduler():
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
