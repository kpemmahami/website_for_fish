"""Internal double-entry posting primitives for institution accounting."""
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .lending import Institution, member
from .main import Base, CurrentUser, Db, app, audit

MAX_PESEWAS = 2 ** 63 - 1


class AccountingAccount(Base):
    __tablename__ = 'institution_accounting_accounts'
    __table_args__ = (
        UniqueConstraint('institution_id', 'code', name='uq_accounting_institution_code'),
        CheckConstraint("category IN ('asset','liability','equity','income','expense','contra')",
                        name='ck_accounting_account_category'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True)


class AccountingJournal(Base):
    __tablename__ = 'institution_accounting_journals'
    __table_args__ = (UniqueConstraint('institution_id', 'source_type', 'source_reference',
                                       name='uq_accounting_journal_source'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    source_type: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(String(120))
    effective_on: Mapped[date] = mapped_column(Date)
    posted_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64))


class AccountingPeriod(Base):
    __tablename__ = 'institution_accounting_periods'
    __table_args__ = (UniqueConstraint('institution_id', 'starts_on', name='uq_accounting_period_month'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    starts_on: Mapped[date] = mapped_column(Date)
    closed: Mapped[bool]
    changed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def lock_accounting_institution(db: Session, institution_id: int) -> None:
    # Share a write lock between changing period state and posting into a period.
    db.execute(update(Institution).where(Institution.id == institution_id)
               .values(status=Institution.status))


def find_period(db: Session, institution_id: int, starts_on: date) -> AccountingPeriod | None:
    return db.scalar(select(AccountingPeriod).where(
        AccountingPeriod.institution_id == institution_id, AccountingPeriod.starts_on == starts_on,
    ))


class AccountingLine(Base):
    __tablename__ = 'institution_accounting_lines'
    __table_args__ = (
        CheckConstraint('(debit_pesewas > 0 AND credit_pesewas = 0) OR '
                        '(credit_pesewas > 0 AND debit_pesewas = 0)', name='ck_accounting_line_one_side'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey('institution_accounting_journals.id'), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('institution_accounting_accounts.id'), index=True)
    debit_pesewas: Mapped[int] = mapped_column(BigInteger)
    credit_pesewas: Mapped[int] = mapped_column(BigInteger)


@dataclass(frozen=True)
class PostingLine:
    account_id: int
    debit_pesewas: int = 0
    credit_pesewas: int = 0


def post_journal(db: Session, *, institution_id: int, source_type: str, source_reference: str,
                 effective_on: date, posted_by: int, lines: list[PostingLine]) -> AccountingJournal:
    """Post a balanced GHS journal inside the caller's authorized financial transaction."""
    source_type, source_reference = source_type.strip(), source_reference.strip()
    if not 0 < len(source_type) <= 40 or not 0 < len(source_reference) <= 120:
        raise ValueError('A valid journal source and reference are required')
    if len(lines) < 2:
        raise ValueError('A journal requires debit and credit lines')
    entries = [(line.account_id, line.debit_pesewas, line.credit_pesewas) for line in lines]
    for _, debit, credit in entries:
        if type(debit) is not int or type(credit) is not int or min(debit, credit) != 0 or max(debit, credit) <= 0:
            raise ValueError('Each journal line requires one positive amount in whole pesewas')
    debits = sum(debit for _, debit, _ in entries)
    credits = sum(credit for _, _, credit in entries)
    if debits != credits or debits > MAX_PESEWAS:
        raise ValueError('Journal debits and credits must balance within the supported amount')
    account_ids = {account_id for account_id, _, _ in entries}
    if len(account_ids) < 2:
        raise ValueError('A journal must affect at least two accounts')

    fingerprint = hashlib.sha256(json.dumps(
        [effective_on.isoformat(), posted_by, sorted(entries)], separators=(',', ':'),
    ).encode()).hexdigest()
    existing_query = select(AccountingJournal).where(
        AccountingJournal.institution_id == institution_id,
        AccountingJournal.source_type == source_type,
        AccountingJournal.source_reference == source_reference,
    )
    existing = db.scalar(existing_query)
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError('Journal source already posted with different details')
        return existing

    lock_accounting_institution(db, institution_id)
    existing = db.scalar(existing_query)
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError('Journal source already posted with different details')
        return existing
    period = find_period(db, institution_id, effective_on.replace(day=1))
    if period is not None and period.closed:
        raise ValueError('Accounting period is closed')
    filters = (AccountingAccount.institution_id == institution_id,
               AccountingAccount.id.in_(account_ids), AccountingAccount.active.is_(True))
    count = len(db.scalars(select(AccountingAccount.id).where(*filters)
                           .order_by(AccountingAccount.id).with_for_update()).all())
    if count != len(account_ids):
        raise ValueError('All journal accounts must be active accounts of this institution')

    # A source event and its journal share the caller's commit. The savepoint lets
    # a concurrent replay recover from the uniqueness check without orphaning lines.
    try:
        with db.begin_nested():
            journal = AccountingJournal(
                institution_id=institution_id, source_type=source_type, source_reference=source_reference,
                effective_on=effective_on, posted_by=posted_by, posted_at=datetime.now(timezone.utc),
                fingerprint=fingerprint,
            )
            db.add(journal)
            db.flush()
            db.add_all(AccountingLine(journal_id=journal.id, account_id=account_id,
                                      debit_pesewas=debit, credit_pesewas=credit)
                       for account_id, debit, credit in entries)
            db.flush()
    except IntegrityError:
        existing = db.scalar(existing_query)
        if existing is None:
            raise
        if existing.fingerprint != fingerprint:
            raise ValueError('Journal source already posted with different details') from None
        return existing
    return journal


ROOT = '/finance/institutions/{institution_id}/accounting/accounts'
TAG = ['Institution accounting']
AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


class CreateAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                           min_length=1, max_length=32, pattern=r'^[A-Za-z0-9.-]+$')]
    name: AccountName
    category: Literal['asset', 'liability', 'equity', 'income', 'expense', 'contra']


class EditAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: AccountName
    active: bool


def account_view(account: AccountingAccount):
    return {key: getattr(account, key) for key in ('id', 'code', 'name', 'category', 'active')}


@app.get(ROOT, tags=TAG)
def list_accounts(institution_id: int, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    accounts = db.scalars(select(AccountingAccount).where(
        AccountingAccount.institution_id == institution_id,
    ).order_by(AccountingAccount.code, AccountingAccount.id))
    return [account_view(account) for account in accounts]


@app.post(ROOT, status_code=201, tags=TAG)
def create_account(institution_id: int, data: CreateAccount, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    account = AccountingAccount(institution_id=institution_id, **data.model_dump())
    db.add(account)
    try:
        db.flush()
        audit(db, user, 'create', 'accounting_account', account.id, json.dumps({
            'institution_id': institution_id, 'account': account_view(account),
        }))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'That account code is already in use') from None
    return account_view(account)


@app.patch(ROOT+'/{account_id}', tags=TAG)
def edit_account(institution_id: int, account_id: int, data: EditAccount, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    account = db.scalar(select(AccountingAccount).where(
        AccountingAccount.institution_id == institution_id, AccountingAccount.id == account_id,
    ).with_for_update())
    if account is None:
        raise HTTPException(404, 'Accounting account not found')
    previous = account_view(account)
    account.name = data.name
    account.active = data.active
    audit(db, user, 'update', 'accounting_account', account.id, json.dumps({
        'institution_id': institution_id, 'previous': previous, 'account': account_view(account),
    }))
    db.commit()
    return account_view(account)


ACCOUNTING = '/finance/institutions/{institution_id}/accounting'


def amount_ghs(pesewas) -> str:
    return f'{Decimal(pesewas) / 100:.2f}'


def journal_view(journal: AccountingJournal):
    return {key: getattr(journal, key) for key in (
        'id', 'source_type', 'source_reference', 'effective_on', 'posted_at', 'posted_by',
    )}


@app.get(ACCOUNTING+'/journals', tags=TAG)
def list_journals(institution_id: int, user: CurrentUser, db: Db,
                  start: date | None = None, end: date | None = None, offset: int = Query(0, ge=0),
                  reference: Annotated[str, Query(max_length=200)] = '',
                  account_code: Annotated[str, Query(max_length=32)] = ''):
    member(db, institution_id, user.id, 'manage_staff')
    if start and end and start > end:
        raise HTTPException(422, 'Start date must be on or before end date')
    query = select(AccountingJournal).where(AccountingJournal.institution_id == institution_id)
    if start:
        query = query.where(AccountingJournal.effective_on >= start)
    if end:
        query = query.where(AccountingJournal.effective_on <= end)
    query = filter_journals(query, institution_id, reference, account_code)
    journals = db.scalars(query.order_by(AccountingJournal.effective_on.desc(), AccountingJournal.id.desc())
                          .offset(offset).limit(26)).all()
    return {'items': [journal_view(journal) for journal in journals[:25]], 'has_more': len(journals) > 25}


def filter_journals(query, institution_id: int, reference: str, account_code: str):
    reference = reference.strip()
    if reference:
        query = query.where(func.lower(AccountingJournal.source_reference).contains(reference.lower(), autoescape=True))
    account_code = account_code.strip().upper()
    if account_code:
        matching_journals = select(AccountingLine.journal_id).join(
            AccountingAccount, AccountingAccount.id == AccountingLine.account_id,
        ).where(AccountingAccount.institution_id == institution_id, AccountingAccount.code == account_code)
        query = query.where(AccountingJournal.id.in_(matching_journals))
    return query


def csv_text(value: str) -> str:
    if value.startswith(('\t', '\r', '\n')) or value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


@app.get(ACCOUNTING+'/journals/export', tags=TAG)
def export_journals(institution_id: int, start: date, end: date, user: CurrentUser, db: Db,
                    reference: Annotated[str, Query(max_length=200)] = '',
                    account_code: Annotated[str, Query(max_length=32)] = ''):
    member(db, institution_id, user.id, 'manage_staff')
    if start > end:
        raise HTTPException(422, 'Start date must be on or before end date')
    query = select(
        AccountingJournal.id, AccountingJournal.effective_on, AccountingJournal.source_reference,
        AccountingAccount.code, AccountingAccount.name, AccountingLine.debit_pesewas,
        AccountingLine.credit_pesewas,
    ).select_from(AccountingJournal).join(
        AccountingLine, AccountingLine.journal_id == AccountingJournal.id,
    ).join(AccountingAccount, AccountingAccount.id == AccountingLine.account_id).where(
        AccountingJournal.institution_id == institution_id,
        AccountingAccount.institution_id == institution_id,
        AccountingJournal.effective_on.between(start, end),
    ).order_by(AccountingJournal.effective_on.desc(), AccountingJournal.id.desc(), AccountingLine.id)
    rows = db.execute(filter_journals(query, institution_id, reference, account_code))
    output = io.StringIO(newline='')
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['Journal ID', 'Effective date', 'Source reference', 'Account code',
                     'Account name', 'Debit (GHS)', 'Credit (GHS)'])
    for journal_id, effective_on, reference, code, name, debit, credit in rows:
        writer.writerow([journal_id, effective_on, csv_text(reference), csv_text(code), csv_text(name),
                         amount_ghs(debit), amount_ghs(credit)])
    return Response(output.getvalue(), media_type='text/csv', headers={
        'Cache-Control': 'private, no-store',
        'Content-Disposition': f'attachment; filename="journals-{start}-to-{end}.csv"',
    })


@app.get(ACCOUNTING+'/journals/{journal_id}', tags=TAG)
def journal_details(institution_id: int, journal_id: int, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    journal = db.scalar(select(AccountingJournal).where(
        AccountingJournal.institution_id == institution_id, AccountingJournal.id == journal_id,
    ))
    if journal is None:
        raise HTTPException(404, 'Journal not found')
    rows = db.execute(select(AccountingLine, AccountingAccount).join(
        AccountingAccount, AccountingAccount.id == AccountingLine.account_id,
    ).where(AccountingLine.journal_id == journal.id, AccountingAccount.institution_id == institution_id)
      .order_by(AccountingLine.id))
    return {**journal_view(journal), 'lines': [
        {'code': account.code, 'name': account.name,
         'debit_ghs': amount_ghs(line.debit_pesewas), 'credit_ghs': amount_ghs(line.credit_pesewas)}
        for line, account in rows
    ]}


@app.get(ACCOUNTING+'/trial-balance', tags=TAG)
def trial_balance(institution_id: int, user: CurrentUser, db: Db, as_of: date | None = None):
    member(db, institution_id, user.id, 'manage_staff')
    cutoff = as_of or datetime.now(timezone.utc).date()
    rows = db.execute(select(
        AccountingAccount.code, AccountingAccount.name,
        func.sum(AccountingLine.debit_pesewas), func.sum(AccountingLine.credit_pesewas),
    ).select_from(AccountingLine).join(
        AccountingAccount, AccountingAccount.id == AccountingLine.account_id,
    ).join(AccountingJournal, AccountingJournal.id == AccountingLine.journal_id).where(
        AccountingAccount.institution_id == institution_id, AccountingJournal.institution_id == institution_id,
        AccountingJournal.effective_on <= cutoff,
    ).group_by(AccountingAccount.id, AccountingAccount.code, AccountingAccount.name)
      .order_by(AccountingAccount.code)).all()
    balances = [(code, name, debit-credit) for code, name, debit, credit in rows]
    debit_total = sum(max(0, net) for _, _, net in balances)
    credit_total = sum(max(0, -net) for _, _, net in balances)
    return {'as_of': cutoff, 'debit_total_ghs': amount_ghs(debit_total),
            'credit_total_ghs': amount_ghs(credit_total), 'balanced': debit_total == credit_total,
            'items': [{'code': code, 'name': name, 'debit_ghs': amount_ghs(max(0, net)),
                       'credit_ghs': amount_ghs(max(0, -net))} for code, name, net in balances]}


class PeriodChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    starts_on: date
    closed: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


@app.get(ACCOUNTING+'/periods', tags=TAG)
def list_periods(institution_id: int, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    rows = db.scalars(select(AccountingPeriod).where(
        AccountingPeriod.institution_id == institution_id,
    ).order_by(AccountingPeriod.starts_on.desc()))
    return [{'starts_on': row.starts_on, 'closed': row.closed, 'changed_at': row.changed_at} for row in rows]


@app.put(ACCOUNTING+'/periods', tags=TAG)
def change_period(institution_id: int, data: PeriodChange, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    if data.starts_on.day != 1:
        raise HTTPException(422, 'Select the first day of an accounting month')
    lock_accounting_institution(db, institution_id)
    period = find_period(db, institution_id, data.starts_on)
    before = period.closed if period else False
    if before == data.closed:
        raise HTTPException(409, 'Accounting period already has this status')
    if period is None:
        period = AccountingPeriod(institution_id=institution_id, starts_on=data.starts_on)
        db.add(period)
    period.closed = data.closed
    period.changed_by = user.id
    period.changed_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, user, 'close' if data.closed else 'reopen', 'accounting_period', period.id,
          json.dumps({'institution_id': institution_id, 'starts_on': data.starts_on.isoformat(),
                      'previous_closed': before, 'closed': data.closed, 'reason': data.reason}))
    db.commit()
    return {'starts_on': period.starts_on, 'closed': period.closed, 'changed_at': period.changed_at}
