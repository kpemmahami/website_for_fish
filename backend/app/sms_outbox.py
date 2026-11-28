"""Transactional opt-in alerts for posted loan activity."""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, String, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from .main import Base, SessionLocal, User
from .sms_gateway import SmsDeliveryError, env_flag, send_sms

MESSAGES = {
    'loan-approved': 'A loan application was approved.',
    'loan-rejected': 'A decision was recorded on a loan application.',
    'disbursement': 'A loan disbursement was recorded.',
    'repayment': 'A loan repayment was recorded.',
    'deposit': 'A deposit was recorded.',
    'settlement': 'A loan was marked fully repaid.',
}


class SmsOutbox(Base):
    __tablename__ = 'sms_outbox'

    event_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    template: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message_id: Mapped[str | None] = mapped_column(String(120))
    attempts: Mapped[int]


def notifications_enabled():
    return os.getenv('AQUAFARM_FINANCIAL_SMS_ENABLED', 'false').strip().lower() in ('1', 'true')


def enqueue_financial_sms(db, user_id: int, event: str, entity_id: int | str):
    if not notifications_enabled():
        return
    if event not in MESSAGES:
        raise ValueError('Unknown financial notification template')
    recipient = db.get(User, user_id)
    if not eligible(recipient):
        return
    now = datetime.now(timezone.utc)
    insert = postgres_insert if db.get_bind().dialect.name == 'postgresql' else sqlite_insert
    db.execute(insert(SmsOutbox).values(
        event_key=f'{event}:{entity_id}', user_id=user_id, template=event,
        state='pending', created_at=now, updated_at=now, attempts=0,
    ).on_conflict_do_nothing(index_elements=[SmsOutbox.event_key]))


def eligible(user):
    return user and user.phone_number and user.phone_verified_at and user.sms_financial_alerts_enabled and not user.is_suspended


def deliver_outbox(sender=send_sms):
    if not notifications_enabled():
        return
    personalize = env_flag('AQUAFARM_SMS_PERSONALIZE_NAMES', False)
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        # An interrupted request might already have reached Arkesel.
        db.execute(update(SmsOutbox).where(SmsOutbox.state == 'processing',
            SmsOutbox.updated_at < now - timedelta(minutes=10)).values(state='unknown', updated_at=now))
        keys = db.scalars(select(SmsOutbox.event_key).where(SmsOutbox.state == 'pending',
                            (SmsOutbox.attempts == 0) | (SmsOutbox.updated_at < now - timedelta(minutes=2)))
                          .order_by(SmsOutbox.created_at, SmsOutbox.event_key).limit(25)).all()
    for key in keys:
        with SessionLocal.begin() as db:
            claimed = db.execute(update(SmsOutbox).where(
                SmsOutbox.event_key == key, SmsOutbox.state == 'pending',
                (SmsOutbox.attempts == 0) | (SmsOutbox.updated_at < now - timedelta(minutes=2)),
            ).values(state='processing', updated_at=datetime.now(timezone.utc), attempts=SmsOutbox.attempts + 1))
            if claimed.rowcount != 1:
                continue
            row = db.get(SmsOutbox, key)
            user = db.get(User, row.user_id)
            if not eligible(user):
                row.state = 'cancelled'
                continue
            phone, text = user.phone_number, MESSAGES[row.template]
            name = user.full_name.strip() if personalize else None
            attempts = row.attempts
        message_id = None
        try:
            message_id = sender(phone, f'AquaFarm Ghana: {text} Sign in to view details.',
                                category='financial', recipient_name=name)
            state = 'accepted'
        except SmsDeliveryError as error:
            state = 'pending' if error.retryable and attempts < 2 else error.state
        with SessionLocal.begin() as db:
            db.execute(update(SmsOutbox).where(
                SmsOutbox.event_key == key, SmsOutbox.state == 'processing',
            ).values(state=state, message_id=message_id, updated_at=datetime.now(timezone.utc)))
