"""Phase 0009: manually verified loan servicing ledger. No money movement or automated notifications."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange
import hashlib
import json
import uuid
from typing import Literal
from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import update, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, select, func, or_
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, Farm, User, owned_farm, audit
from .sms_outbox import enqueue_financial_sms, notifications_enabled
from .lending import Institution, InstitutionMember, LoanApplication, LoanDecision, application_scope, require_application_scope, member, ghs

TAG = ['Loan disbursement and recovery (manual ledger)']
def utcnow(): return datetime.now(timezone.utc)
def cents(value): return int((Decimal(str(value))*100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
def add_months(day, months):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))

class LoanAccount(Base):
    __tablename__='loan_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), unique=True, nullable=False)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'), index=True, nullable=False)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True, nullable=False)
    approved_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_flat_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    commitment_fee_pesewas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_fee_pesewas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_fee_rate_bps: Mapped[int | None] = mapped_column(Integer)
    insurance_fee_rate_bps: Mapped[int | None] = mapped_column(Integer)
    insurance_fee_pesewas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='awaiting_disbursement')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class LoanDisbursement(Base):
    __tablename__='loan_disbursements'
    __table_args__=(UniqueConstraint('loan_id','reference',name='uq_loan_disbursement_reference'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('loan_accounts.id'), index=True, nullable=False)
    amount_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    disbursed_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class DisbursementReview(Base):
    __tablename__ = 'loan_disbursement_reviews'
    __table_args__ = (UniqueConstraint('loan_id', 'reference', name='uq_disbursement_review_reference'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('loan_accounts.id'))
    amount_pesewas: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(100))
    disbursed_on: Mapped[date] = mapped_column(Date)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('loan_evidence.id'), unique=True)
    prepared_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(16), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))


class LoanInstallment(Base):
    __tablename__='loan_installments'
    __table_args__=(UniqueConstraint('loan_id','number',name='uq_loan_installment_number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('loan_accounts.id'), index=True, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    principal_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    fees_pesewas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class LoanRepayment(Base):
    __tablename__='loan_repayments'
    __table_args__=(UniqueConstraint('loan_id','reference',name='uq_loan_repayment_reference'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey('loan_accounts.id'), index=True, nullable=False)
    amount_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    principal_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    fees_pesewas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class CollectionDeposit(Base):
    __tablename__ = 'collection_deposits'
    repayment_id: Mapped[int] = mapped_column(ForeignKey('loan_repayments.id'), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    amount_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)


class StandaloneDeposit(Base):
    __tablename__ = 'standalone_collection_deposits'
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(48), unique=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('loan_evidence.id'), unique=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    amount_pesewas: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoanEvidence(Base):
    __tablename__='loan_evidence'
    __table_args__=(UniqueConstraint('farm_id','sha256',name='uq_loan_evidence_farm_sha256'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True, nullable=False)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey('loan_accounts.id'), index=True, nullable=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('loan_applications.id'), index=True, nullable=True)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class CustomInstallmentIn(BaseModel):
    due_on: date
    principal_ghs: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    interest_ghs: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    fees_ghs: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode='after')
    def require_amount(self):
        if self.principal_ghs + self.interest_ghs <= 0:
            raise ValueError('Each custom installment must have a positive amount')
        return self

class OpenLoanIn(BaseModel):
    application_id: int = Field(gt=0)
    annual_flat_interest_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    commitment_fee_ghs: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)
    processing_fee_ghs: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)
    processing_fee_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    insurance_fee_percent: Decimal = Field(default=Decimal('1'), ge=0, le=100, max_digits=5, decimal_places=2)
    repayment_frequency: Literal['monthly','quarterly','harvest','custom']
    first_due_date: date
    custom_schedule: list[CustomInstallmentIn] | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode='after')
    def validate_custom_schedule(self):
        if self.processing_fee_percent is not None and self.processing_fee_ghs:
            raise ValueError('Enter processing as either a percentage or a fixed amount')
        if self.repayment_frequency == 'custom':
            if not self.custom_schedule:
                raise ValueError('Custom repayment schedules require at least one installment')
            dates = [item.due_on for item in self.custom_schedule]
            if dates[0] != self.first_due_date:
                raise ValueError('First due date must match the first custom installment')
            if dates != sorted(set(dates)):
                raise ValueError('Custom installment dates must be unique and ascending')
        elif self.custom_schedule is not None:
            raise ValueError('Custom installments are only valid for a custom repayment schedule')
        return self

class TransactionIn(BaseModel):
    amount_ghs: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reference: str = Field(min_length=3,max_length=100)
    transaction_date: date
    evidence_id: int = Field(gt=0)

def scoped_loan_ids(institution_id, user_id):
    return select(LoanAccount.id).join(LoanApplication, LoanApplication.id == LoanAccount.application_id).where(
        LoanAccount.institution_id == institution_id, *application_scope(institution_id, user_id),
    )


def loan_for_lender(db, loan_id, user, permission='view'):
    loan=db.get(LoanAccount,loan_id)
    if loan is None: raise HTTPException(404,'Loan not found')
    member(db,loan.institution_id,user.id,permission)
    require_application_scope(db, db.get(LoanApplication, loan.application_id), user.id)
    return loan

def loan_for_view(db, loan_id, user):
    loan=db.get(LoanAccount,loan_id)
    if loan is None: raise HTTPException(404,'Loan not found')
    try:
        owned_farm(loan.farm_id,user,db)
        return loan
    except HTTPException:
        return loan_for_lender(db, loan_id, user)

def sums(db, loan):
    disbursed=db.scalar(select(func.coalesce(func.sum(LoanDisbursement.amount_pesewas),0)).where(LoanDisbursement.loan_id==loan.id))
    repaid_principal=db.scalar(select(func.coalesce(func.sum(LoanRepayment.principal_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
    repaid_interest=db.scalar(select(func.coalesce(func.sum(LoanRepayment.interest_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
    scheduled_interest=0 if loan.status in ('offered','declined','awaiting_disbursement') else db.scalar(
        select(func.coalesce(func.sum(LoanInstallment.interest_pesewas),0)).where(LoanInstallment.loan_id==loan.id))
    return disbursed,repaid_principal,repaid_interest,scheduled_interest

def scheduled_interest(principal, annual_flat_rate_bps, term_months):
    return int((Decimal(principal)*Decimal(annual_flat_rate_bps)*Decimal(term_months)/Decimal(120000))
               .quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def loan_fee_total(loan):
    return loan.commitment_fee_pesewas + loan.processing_fee_pesewas + loan.insurance_fee_pesewas


def loan_evidence_view(evidence):
    return {
        'id': evidence.id,
        'record_type': evidence.record_type,
        'media_type': evidence.media_type,
        'duration_seconds': evidence.duration_seconds,
        'sha256': evidence.sha256,
        'size_bytes': evidence.size_bytes,
        'captured_at': evidence.captured_at,
        'device_recorded_at': evidence.device_recorded_at,
        'server_received_at': evidence.server_received_at,
    }


async def store_loan_evidence(
    farm_id: int,
    record_type: str,
    loan_id: int | None,
    request: Request,
    captured_at: datetime,
    device_recorded_at: datetime,
    duration_seconds: int,
    user,
    db,
    *,
    retry_upload: bool = False,
):
    from .evidence import MAX_VIDEO_BYTES, evidence_directory

    if duration_seconds != 15:
        raise HTTPException(422, 'Loan video evidence must be 15 seconds')
    if captured_at.tzinfo is None or device_recorded_at.tzinfo is None:
        raise HTTPException(422, 'Capture and device timestamps must include a timezone')
    received_at = utcnow()
    captured_utc = captured_at.astimezone(timezone.utc)
    if captured_utc > received_at + timedelta(minutes=5) or received_at - captured_utc > timedelta(hours=24):
        raise HTTPException(422, 'Record a fresh video within 24 hours before submitting')

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
    digest = hashlib.sha256()
    total = 0
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
        existing = db.scalar(select(LoanEvidence).where(
            LoanEvidence.farm_id == farm_id, LoanEvidence.sha256 == sha256,
        ))
        if existing is not None:
            if (retry_upload and existing.loan_id == loan_id
                    and existing.record_type == record_type and existing.uploaded_by == user.id
                    and (root / existing.storage_name).is_file()):
                path.unlink()
                return loan_evidence_view(existing)
            raise HTTPException(409, 'Duplicate loan video evidence already exists for this farm')
        evidence = LoanEvidence(
            farm_id=farm_id,
            loan_id=loan_id,
            record_type=record_type,
            storage_name=storage_name,
            media_type=media_type,
            size_bytes=total,
            duration_seconds=15,
            sha256=sha256,
            captured_at=captured_utc,
            device_recorded_at=device_recorded_at.astimezone(timezone.utc),
            server_received_at=received_at,
            uploaded_by=user.id,
        )
        db.add(evidence)
        db.flush()
        audit(db, user, 'upload', 'loan_evidence', evidence.id, json.dumps({
            'farm_id': farm_id,
            'loan_id': loan_id,
            'record_type': record_type,
            'sha256': sha256,
        }))
        db.commit()
        db.refresh(evidence)
        return loan_evidence_view(evidence)
    except Exception:
        if path.exists():
            path.unlink()
        raise


def required_loan_evidence(db, evidence_id: int, farm_id: int, record_type: str, user_id: int, loan_id: int | None = None):
    evidence = db.get(LoanEvidence, evidence_id)
    received_at = evidence.server_received_at if evidence is not None else None
    if received_at is not None and received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    if (
        evidence is None
        or evidence.farm_id != farm_id
        or evidence.record_type != record_type
        or evidence.uploaded_by != user_id
        or evidence.application_id is not None
        or evidence.record_id is not None
        or evidence.loan_id != loan_id
        or utcnow() - received_at > timedelta(hours=2)
    ):
        raise HTTPException(422, 'Upload a new 15-second in-app video for this loan submission')
    return evidence


def view(db,loan):
    disbursed,paid_p,paid_i,scheduled_i=sums(db,loan)
    fees = loan_fee_total(loan)
    fees_paid = db.scalar(select(func.coalesce(func.sum(LoanRepayment.fees_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
    expected_interest = scheduled_i or scheduled_interest(loan.approved_pesewas,loan.annual_flat_rate_bps,loan.term_months)
    total_contract = loan.approved_pesewas + expected_interest + fees
    current_balance = disbursed-paid_p+scheduled_i-paid_i+fees-fees_paid
    reserved = pending_disbursements(db, loan.id) if loan.status == 'awaiting_disbursement' else 0
    return {'id':loan.id,'application_id':loan.application_id,'farm_id':loan.farm_id,'institution_id':loan.institution_id,
        'status':loan.status,'currency':'GHS','approved_ghs':ghs(loan.approved_pesewas),
        'disbursed_ghs':ghs(disbursed),'undisbursed_ghs':ghs(loan.approved_pesewas-disbursed),
        'pending_disbursement_ghs':ghs(reserved),
        'available_for_disbursement_ghs':ghs(max(0,loan.approved_pesewas-disbursed-reserved)),
        'principal_repaid_ghs':ghs(paid_p),'interest_repaid_ghs':ghs(paid_i),
        'outstanding_principal_ghs':ghs(disbursed-paid_p),
        'scheduled_interest_ghs':ghs(scheduled_i), 'outstanding_scheduled_interest_ghs':ghs(scheduled_i-paid_i),
        'expected_interest_ghs':ghs(expected_interest),
        'commitment_fee_ghs':ghs(loan.commitment_fee_pesewas),
        'processing_fee_ghs':ghs(loan.processing_fee_pesewas),
        'insurance_fee_ghs':ghs(loan.insurance_fee_pesewas),
        'processing_fee_percent':None if loan.processing_fee_rate_bps is None else loan.processing_fee_rate_bps/100,
        'insurance_fee_percent':None if loan.insurance_fee_rate_bps is None else loan.insurance_fee_rate_bps/100,
        'total_fees_ghs':ghs(fees),
        'fees_paid_ghs':ghs(fees_paid),
        'outstanding_fees_ghs':ghs(fees-fees_paid),
        'total_contract_repayment_ghs':ghs(total_contract),
        'total_scheduled_balance_ghs':ghs(max(0,current_balance)) if loan.status in ('active','repaid') else 0,
        'annual_flat_interest_percent':loan.annual_flat_rate_bps/100,
        'repayment_frequency':loan.frequency,'first_due_date':loan.first_due_date,'term_months':loan.term_months,
        'note':'Interest is flat over the approved term. Percentage-based fees are calculated separately on approved principal.'}

def standard_installments(loan, principal):
    count={'monthly':loan.term_months,'quarterly':(loan.term_months+2)//3,'harvest':1}[loan.frequency]
    # Flat simple interest on fully disbursed principal, not reducing-balance interest.
    interest=scheduled_interest(principal,loan.annual_flat_rate_bps,loan.term_months)
    fees=loan_fee_total(loan)
    step={'monthly':1,'quarterly':3,'harvest':0}[loan.frequency]
    for n in range(count):
        p=principal//count+(principal%count if n==count-1 else 0)
        i=interest//count+(interest%count if n==count-1 else 0)
        f=fees//count+(fees%count if n==count-1 else 0)
        due=add_months(loan.first_due_date,n*step) if step else loan.first_due_date
        yield LoanInstallment(loan_id=loan.id, number=n+1, due_on=due,
            principal_pesewas=p, interest_pesewas=i, fees_pesewas=f)


def make_schedule(db, loan):
    if loan.frequency != 'custom':
        principal, _, _, _ = sums(db, loan)
        db.add_all(standard_installments(loan, principal))


@app.post('/farms/{farm_id}/loan-evidence',status_code=201,tags=TAG)
async def upload_application_evidence(
    farm_id:int,request:Request,user:CurrentUser,db:Db,
    captured_at:datetime,device_recorded_at:datetime,duration_seconds:int,
):
    owned_farm(farm_id,user,db)
    return await store_loan_evidence(
        farm_id,'loan_application',None,request,captured_at,device_recorded_at,duration_seconds,user,db)


@app.post('/finance/loans/{loan_id}/evidence',status_code=201,tags=TAG)
async def upload_transaction_evidence(
    loan_id:int,request:Request,user:CurrentUser,db:Db,
    record_type:Literal['disbursement','repayment','deposit'],
    captured_at:datetime,device_recorded_at:datetime,duration_seconds:int, retry_upload:bool=False,
):
    loan=loan_for_lender(db,loan_id,user,'disburse' if record_type=='disbursement' else 'repay')
    return await store_loan_evidence(
        loan.farm_id,record_type,loan.id,request,captured_at,device_recorded_at,duration_seconds,user,db,
        retry_upload=retry_upload and record_type in ('repayment','deposit'))


@app.get('/finance/loan-evidence/{evidence_id}/video',tags=TAG)
def download_loan_evidence(evidence_id:int,user:CurrentUser,db:Db):
    evidence=db.get(LoanEvidence,evidence_id)
    if evidence is None:
        raise HTTPException(404,'Loan video evidence not found')
    try:
        owned_farm(evidence.farm_id,user,db)
    except HTTPException:
        if evidence.loan_id is not None:
            loan_for_view(db,evidence.loan_id,user)
        elif evidence.application_id is not None:
            application=db.get(LoanApplication,evidence.application_id)
            if application is None:
                raise HTTPException(404,'Loan video evidence not found')
            member(db,application.institution_id,user.id)
            require_application_scope(db, application, user.id)
        else:
            raise HTTPException(404,'Loan video evidence not found')
    from .evidence import evidence_directory
    path=evidence_directory()/evidence.storage_name
    if not path.is_file():
        raise HTTPException(404,'Loan video evidence file is unavailable')
    return FileResponse(path,media_type=evidence.media_type,filename=f'loan_evidence_{evidence.id}{path.suffix}')


@app.post('/finance/institutions/{institution_id}/loans',status_code=201,tags=TAG)
def open_loan(institution_id:int,data:OpenLoanIn,user:CurrentUser,db:Db):
    member(db,institution_id,user.id,'appraise')
    application=db.get(LoanApplication,data.application_id)
    if application is None or application.institution_id!=institution_id: raise HTTPException(404,'Approved application not found')
    require_application_scope(db, application, user.id)
    if application.status!='approved': raise HTTPException(409,'Application not approved')
    if db.scalar(select(LoanAccount.id).where(LoanAccount.application_id==application.id)) is not None: raise HTTPException(409,'Loan account already exists')
    decision=db.scalar(select(LoanDecision).where(LoanDecision.application_id==application.id,LoanDecision.decision=='approved').order_by(LoanDecision.id.desc()))
    if decision is None or not decision.approved_pesewas: raise HTTPException(409,'Approved amount not found')
    if data.first_due_date<=date.today(): raise HTTPException(422,'First due date must be in the future')
    if data.custom_schedule and data.custom_schedule[-1].due_on > add_months(data.first_due_date,application.term_months-1):
        raise HTTPException(422,'Custom installments must fit within the approved repayment term')
    approved=decision.approved_pesewas
    annual_rate_bps = int(data.annual_flat_interest_percent * 100)
    processing_rate = data.processing_fee_percent
    insurance_rate = data.insurance_fee_percent
    commitment_fee = cents(data.commitment_fee_ghs)
    processing_fee = cents(data.processing_fee_ghs if processing_rate is None else Decimal(approved) * processing_rate / 10000)
    insurance_fee = cents(Decimal(approved) * insurance_rate / 10000)
    if data.custom_schedule:
        custom_principal=sum(cents(item.principal_ghs) for item in data.custom_schedule)
        custom_interest=sum(cents(item.interest_ghs) for item in data.custom_schedule)
        expected_interest = scheduled_interest(approved, annual_rate_bps, application.term_months)
        if custom_principal!=approved:
            raise HTTPException(422,'Custom installment principal must equal the approved loan amount')
        if custom_interest!=expected_interest:
            raise HTTPException(422,'Custom installment interest must equal the scheduled flat interest')
        if sum(cents(item.fees_ghs) for item in data.custom_schedule)!=commitment_fee+processing_fee+insurance_fee:
            raise HTTPException(422,'Custom installment fees must equal the commitment, processing, and insurance fees')
    loan=LoanAccount(application_id=application.id,institution_id=institution_id,farm_id=application.farm_id,
        approved_pesewas=approved,annual_flat_rate_bps=annual_rate_bps,
        frequency=data.repayment_frequency,first_due_date=data.first_due_date,term_months=application.term_months,
        status='offered',
        commitment_fee_pesewas=commitment_fee,processing_fee_pesewas=processing_fee,insurance_fee_pesewas=insurance_fee,
        processing_fee_rate_bps=None if processing_rate is None else int(processing_rate * 100),
        insurance_fee_rate_bps=int(insurance_rate * 100))
    db.add(loan);db.flush()
    if data.custom_schedule:
        for number,item in enumerate(data.custom_schedule,1):
            db.add(LoanInstallment(loan_id=loan.id,number=number,due_on=item.due_on,
                principal_pesewas=cents(item.principal_ghs),interest_pesewas=cents(item.interest_ghs),
                fees_pesewas=cents(item.fees_ghs)))
    audit(db,user,'open','loan_account',loan.id);db.commit()
    return view(db,loan)

class LoanOfferResponse(BaseModel):
    decision: Literal['accept', 'decline']


@app.post('/finance/loans/{loan_id}/offer-response', tags=TAG)
def respond_to_offer(loan_id: int, data: LoanOfferResponse, user: CurrentUser, db: Db):
    loan = db.get(LoanAccount, loan_id)
    if loan is None:
        raise HTTPException(404, 'Loan not found')
    owned_farm(loan.farm_id, user, db)
    member_institution = db.get(Institution, loan.institution_id)
    if member_institution is None or member_institution.status != 'verified':
        raise HTTPException(409, 'The institution is unavailable')
    status = 'awaiting_disbursement' if data.decision == 'accept' else 'declined'
    if data.decision == 'accept' and loan.first_due_date <= date.today():
        raise HTTPException(409, 'The first due date has passed. Contact the institution.')
    result = db.execute(update(LoanAccount).where(
        LoanAccount.id == loan_id, LoanAccount.status == 'offered',
    ).values(status=status))
    if result.rowcount != 1:
        raise HTTPException(409, 'This offer is no longer awaiting a response')
    audit(db, user, data.decision + '_offer', 'loan_account', loan_id)
    db.commit()
    return view(db, loan)


def lock_disbursement_policy(db, institution_id):
    db.execute(update(Institution).where(Institution.id == institution_id).values(status=Institution.status))
    institution = db.get(Institution, institution_id)
    db.refresh(institution)
    return institution


def lock_disbursement_loan(db, loan):
    db.execute(update(LoanAccount).where(LoanAccount.id == loan.id).values(status=LoanAccount.status))
    db.refresh(loan)


def pending_disbursements(db, loan_id):
    return db.scalar(select(func.coalesce(func.sum(DisbursementReview.amount_pesewas), 0)).where(
        DisbursementReview.loan_id == loan_id, DisbursementReview.status == 'pending',
    ))


def check_disbursement(db, loan, amount, reference, disbursed_on, *, reserved=0):
    if loan.status != 'awaiting_disbursement':
        raise HTTPException(409, 'Loan not awaiting disbursement')
    if db.scalar(select(LoanDisbursement.id).where(
        LoanDisbursement.loan_id == loan.id, LoanDisbursement.reference == reference,
    )) is not None:
        raise HTTPException(409, 'Disbursement reference already recorded')
    if disbursed_on > utcnow().date():
        raise HTTPException(422, 'Future disbursement cannot be recorded')
    disbursed, _, _, _ = sums(db, loan)
    if amount > loan.approved_pesewas - disbursed - reserved:
        raise HTTPException(422, 'Disbursement exceeds approved amount')
    return disbursed


def post_disbursement(db, loan, amount, reference, disbursed_on, evidence, recorded_by, actor, disbursed):
    transaction = LoanDisbursement(loan_id=loan.id, amount_pesewas=amount, reference=reference,
                                  disbursed_on=disbursed_on, recorded_by=recorded_by)
    db.add(transaction)
    db.flush()
    evidence.record_id = transaction.id
    if disbursed + amount == loan.approved_pesewas:
        db.flush()
        make_schedule(db, loan)
        loan.status = 'active'
    audit(db, actor, 'disburse', 'loan_account', loan.id, json.dumps({
        'amount_ghs': ghs(amount), 'reference': reference, 'evidence_id': evidence.id,
        'prepared_by': recorded_by,
    }))
    if notifications_enabled():
        enqueue_financial_sms(db, db.get(Farm, loan.farm_id).owner_id, 'disbursement', transaction.id)


@app.post('/finance/loans/{loan_id}/disbursements', status_code=201, tags=TAG)
def record_disbursement(loan_id: int, data: TransactionIn, user: CurrentUser, db: Db):
    loan = loan_for_lender(db, loan_id, user, 'disburse')
    if lock_disbursement_policy(db, loan.institution_id).require_disbursement_approval:
        raise HTTPException(409, 'This institution requires independent disbursement approval')
    lock_disbursement_loan(db, loan)
    amount = cents(data.amount_ghs)
    disbursed = check_disbursement(db, loan, amount, data.reference, data.transaction_date)
    evidence = required_loan_evidence(db, data.evidence_id, loan.farm_id, 'disbursement', user.id, loan.id)
    post_disbursement(db, loan, amount, data.reference, data.transaction_date, evidence, user.id, user, disbursed)
    db.commit()
    return view(db, loan)


class DisbursementPolicyIn(BaseModel):
    required: bool


@app.put('/finance/institutions/{institution_id}/disbursement-policy', tags=TAG)
def update_disbursement_policy(institution_id: int, data: DisbursementPolicyIn, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    institution = lock_disbursement_policy(db, institution_id)
    if not data.required and db.scalar(select(DisbursementReview.id)
        .join(LoanAccount, LoanAccount.id == DisbursementReview.loan_id)
        .where(LoanAccount.institution_id == institution_id, DisbursementReview.status == 'pending').limit(1)):
        raise HTTPException(409, 'Decide all pending disbursements before disabling this policy')
    if institution.require_disbursement_approval != data.required:
        institution.require_disbursement_approval = data.required
        audit(db, user, 'change_disbursement_policy', 'finance_institution', institution_id,
              json.dumps({'required': data.required}))
    db.commit()
    return {'required': institution.require_disbursement_approval}


def review_view(review):
    return {'id': review.id, 'loan_id': review.loan_id, 'reference': review.reference,
            'amount_ghs': ghs(review.amount_pesewas), 'disbursed_on': review.disbursed_on,
            'evidence_id': review.evidence_id, 'prepared_by': review.prepared_by,
            'status': review.status, 'created_at': review.created_at,
            'decided_by': review.decided_by, 'decided_at': review.decided_at, 'reason': review.reason}


@app.get('/finance/institutions/{institution_id}/disbursement-reviews', tags=TAG)
def disbursement_review_queue(institution_id: int, user: CurrentUser, db: Db,
                              status: Literal['pending','approved','rejected'] = 'pending',
                              offset: int = Query(0, ge=0)):
    member(db, institution_id, user.id, 'manage_staff')
    rows = db.scalars(select(DisbursementReview).join(LoanAccount, LoanAccount.id == DisbursementReview.loan_id)
        .where(LoanAccount.institution_id == institution_id, DisbursementReview.status == status)
        .order_by(DisbursementReview.id.desc()).offset(offset).limit(26)).all()
    return {'items': [review_view(row) for row in rows[:25]], 'has_more': len(rows) > 25}


@app.post('/finance/loans/{loan_id}/disbursement-reviews', status_code=201, tags=TAG)
def prepare_disbursement(loan_id: int, data: TransactionIn, user: CurrentUser, db: Db):
    loan = loan_for_lender(db, loan_id, user, 'disburse')
    if not lock_disbursement_policy(db, loan.institution_id).require_disbursement_approval:
        raise HTTPException(409, 'Independent disbursement approval is disabled')
    role = db.scalar(select(InstitutionMember.role).where(
        InstitutionMember.institution_id == loan.institution_id, InstitutionMember.user_id == user.id,
    ))
    if role == 'owner':
        raise HTTPException(403, 'A disbursement officer must prepare this record for the owner to review')
    lock_disbursement_loan(db, loan)
    amount = cents(data.amount_ghs)
    existing = db.scalar(select(DisbursementReview).where(
        DisbursementReview.loan_id == loan.id, DisbursementReview.reference == data.reference,
    ))
    if existing:
        if (existing.amount_pesewas != amount or existing.evidence_id != data.evidence_id
                or existing.prepared_by != user.id or existing.disbursed_on != data.transaction_date):
            raise HTTPException(409, 'Disbursement reference already prepared')
        return review_view(existing)
    check_disbursement(db, loan, amount, data.reference, data.transaction_date,
                       reserved=pending_disbursements(db, loan.id))
    evidence = required_loan_evidence(db, data.evidence_id, loan.farm_id, 'disbursement', user.id, loan.id)
    if db.scalar(select(DisbursementReview.id).where(DisbursementReview.evidence_id == evidence.id)) is not None:
        raise HTTPException(409, 'Evidence already attached to a disbursement review')
    review = DisbursementReview(loan_id=loan.id, amount_pesewas=amount, reference=data.reference,
                                disbursed_on=data.transaction_date, evidence_id=evidence.id, prepared_by=user.id)
    db.add(review)
    db.flush()
    audit(db, user, 'prepare_disbursement', 'loan_disbursement_review', review.id)
    db.commit()
    return review_view(review)


class DisbursementDecision(BaseModel):
    decision: Literal['approved','rejected']
    reason: str = Field(min_length=3, max_length=500, pattern=r'\S')


@app.post('/finance/loans/{loan_id}/disbursement-reviews/{review_id}/decision', tags=TAG)
def decide_disbursement(loan_id: int, review_id: int, data: DisbursementDecision, user: CurrentUser, db: Db):
    loan = loan_for_lender(db, loan_id, user, 'manage_staff')
    lock_disbursement_policy(db, loan.institution_id)
    lock_disbursement_loan(db, loan)
    review = db.scalar(select(DisbursementReview).where(
        DisbursementReview.id == review_id, DisbursementReview.loan_id == loan.id,
    ))
    if review is None:
        raise HTTPException(404, 'Disbursement review not found')
    if review.prepared_by == user.id:
        raise HTTPException(403, 'The preparing officer cannot decide this disbursement')
    if review.status != 'pending':
        if review.status == data.decision and review.decided_by == user.id and review.reason == data.reason.strip():
            return review_view(review)
        raise HTTPException(409, 'Disbursement already decided')
    if data.decision == 'approved':
        disbursed = check_disbursement(db, loan, review.amount_pesewas, review.reference, review.disbursed_on,
                                       reserved=pending_disbursements(db, loan.id) - review.amount_pesewas)
        evidence = db.get(LoanEvidence, review.evidence_id)
        if evidence is None or evidence.record_id is not None:
            raise HTTPException(409, 'Disbursement evidence is unavailable')
        post_disbursement(db, loan, review.amount_pesewas, review.reference, review.disbursed_on,
                          evidence, review.prepared_by, user, disbursed)
    review.status = data.decision
    review.reason = data.reason.strip()
    review.decided_by = user.id
    review.decided_at = utcnow()
    audit(db, user, data.decision, 'loan_disbursement_review', review.id, json.dumps({'reason': review.reason}))
    db.commit()
    return review_view(review)


@app.post('/finance/loans/{loan_id}/repayments',status_code=201,tags=TAG)
def record_repayment(loan_id:int,data:TransactionIn,user:CurrentUser,db:Db):
    if data.reference.upper().startswith('COLLECTION-'):
        raise HTTPException(422, 'This reference prefix is reserved for field collections')
    loan = loan_for_lender(db, loan_id, user, 'repay')
    post_repayment(db, loan, data, user)
    return view(db, loan)


class FieldRepaymentIn(BaseModel):
    collection_id: uuid.UUID
    amount_ghs: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    transaction_date: date
    evidence_id: int = Field(gt=0)
    customer_consented: Literal[True]


@app.post('/finance/loans/{loan_id}/field-repayments', tags=TAG)
def record_field_repayment(loan_id: int, data: FieldRepaymentIn, user: CurrentUser, db: Db):
    loan = loan_for_lender(db, loan_id, user, 'repay')
    transaction = post_repayment(db, loan, TransactionIn(
        amount_ghs=data.amount_ghs, reference=f'COLLECTION-{data.collection_id}',
        transaction_date=data.transaction_date, evidence_id=data.evidence_id,
    ), user, field_collection=True)
    deposit = db.get(CollectionDeposit, transaction.id)
    deposited = deposit.amount_pesewas if deposit else 0
    return {'id': transaction.id, 'reference': transaction.reference,
            'amount_ghs': ghs(transaction.amount_pesewas + deposited),
            'applied_to_loan_ghs': ghs(transaction.amount_pesewas),
            'deposited_ghs': ghs(deposited), 'posted_at': transaction.created_at}


def post_repayment(db, loan, data, user, *, field_collection=False):
    # Acquire the database write lock before reading any repayment balances.
    db.execute(update(LoanAccount).where(LoanAccount.id == loan.id).values(status=LoanAccount.status))
    db.refresh(loan)
    existing = db.scalar(select(LoanRepayment).where(
        LoanRepayment.loan_id == loan.id, LoanRepayment.reference == data.reference,
    ))
    if existing is not None:
        evidence = db.get(LoanEvidence, data.evidence_id) if field_collection else None
        deposit = db.get(CollectionDeposit, existing.id) if field_collection else None
        original_amount = existing.amount_pesewas + (deposit.amount_pesewas if deposit else 0)
        if (field_collection and existing.recorded_by == user.id
                and original_amount == cents(data.amount_ghs)
                and existing.paid_on == data.transaction_date
                and evidence is not None and evidence.record_type == 'repayment'
                and evidence.loan_id == loan.id and evidence.record_id == existing.id
                and evidence.uploaded_by == user.id):
            return existing
        raise HTTPException(409, 'Repayment reference already recorded')
    if loan.status != 'active':
        raise HTTPException(409, 'Loan is not active')
    if data.transaction_date>date.today(): raise HTTPException(422,'Future repayment cannot be recorded')
    amount=cents(data.amount_ghs)
    disbursed,paid_p,paid_i,interest=sums(db,loan)
    remaining_interest=interest-paid_i
    fees_paid=db.scalar(select(func.coalesce(func.sum(LoanRepayment.fees_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
    remaining_fees=loan_fee_total(loan)-fees_paid
    remaining_principal=disbursed-paid_p
    balance = remaining_interest + remaining_fees + remaining_principal
    excess = max(0, amount - balance)
    if excess and not field_collection:
        raise HTTPException(422, 'Payment exceeds outstanding scheduled balance')
    if amount > 2_147_483_647:
        raise HTTPException(422, 'Amount exceeds the maximum supported collection')
    amount -= excess
    evidence=required_loan_evidence(db,data.evidence_id,loan.farm_id,'repayment',user.id,loan.id)
    interest_part=min(amount,remaining_interest)
    fees_part=min(amount-interest_part,remaining_fees)
    principal_part=amount-interest_part-fees_part
    transaction=LoanRepayment(loan_id=loan.id,amount_pesewas=amount,interest_pesewas=interest_part,
        fees_pesewas=fees_part,principal_pesewas=principal_part,reference=data.reference,
        paid_on=data.transaction_date,recorded_by=user.id)
    db.add(transaction);db.flush()
    evidence.record_id=transaction.id
    if excess:
        customer = db.get(Farm, loan.farm_id).owner_id
        db.add(CollectionDeposit(repayment_id=transaction.id, customer_id=customer, amount_pesewas=excess))
        audit(db, user, 'record_excess_deposit', 'loan_repayment', transaction.id,
              json.dumps({'amount_ghs': ghs(excess), 'institution_id': loan.institution_id, 'customer_id': customer}))
    if amount == balance:
        loan.status = 'repaid'
    audit(db,user,'repay','loan_account',loan.id,json.dumps({
        'amount_ghs':ghs(amount),'reference':data.reference,'evidence_id':evidence.id,
        'interest_ghs':ghs(interest_part),'fees_ghs':ghs(fees_part),'principal_ghs':ghs(principal_part),
        **({'customer_consented': True} if field_collection else {}),
    }))
    if notifications_enabled():
        customer = db.get(Farm, loan.farm_id).owner_id
        enqueue_financial_sms(db, customer, 'settlement' if amount == balance else 'repayment', transaction.id)
        if excess:
            enqueue_financial_sms(db, customer, 'deposit', transaction.id)
    db.commit()
    return transaction

def collection_account_number(loan_id: int) -> str:
    return f'AQUA-LOAN-{loan_id:06d}'


@app.post('/finance/loans/{loan_id}/field-deposits', tags=TAG)
def record_field_deposit(loan_id: int, data: FieldRepaymentIn, user: CurrentUser, db: Db):
    # The loan identifies an established customer relationship and scopes video access.
    # A deposit has no effect on that loan's balance.
    loan = loan_for_lender(db, loan_id, user, 'repay')
    db.execute(update(LoanAccount).where(LoanAccount.id == loan.id).values(status=LoanAccount.status))
    db.refresh(loan)
    if loan.status not in ('active', 'repaid'):
        raise HTTPException(409, 'An established institution customer is required')
    customer_id = db.get(Farm, loan.farm_id).owner_id
    reference = f'DEPOSIT-{data.collection_id}'
    amount = cents(data.amount_ghs)
    if amount > 2_147_483_647 or data.transaction_date > utcnow().date():
        raise HTTPException(422, 'Invalid deposit amount or date')
    deposit = db.scalar(select(StandaloneDeposit).where(StandaloneDeposit.reference == reference))
    if deposit is not None:
        if (deposit.institution_id != loan.institution_id or deposit.customer_id != customer_id
                or deposit.recorded_by != user.id or deposit.evidence_id != data.evidence_id
                or deposit.amount_pesewas != amount or deposit.paid_on != data.transaction_date):
            raise HTTPException(409, 'Deposit reference already recorded')
    else:
        evidence = required_loan_evidence(db, data.evidence_id, loan.farm_id, 'deposit', user.id, loan.id)
        deposit = StandaloneDeposit(reference=reference, institution_id=loan.institution_id,
                                    customer_id=customer_id, evidence_id=evidence.id,
                                    recorded_by=user.id, amount_pesewas=amount, paid_on=data.transaction_date)
        db.add(deposit)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(409, 'Deposit already submitted. Retry the original collection.') from error
        evidence.record_id = deposit.id
        audit(db, user, 'record_deposit', 'collection_deposit', deposit.id,
              json.dumps({'institution_id': loan.institution_id, 'customer_consented': True}))
        enqueue_financial_sms(db, customer_id, 'deposit', f'standalone:{deposit.id}')
        db.commit()
    return {'id': deposit.id, 'reference': deposit.reference, 'amount_ghs': ghs(amount),
            'applied_to_loan_ghs': 0, 'deposited_ghs': ghs(amount), 'posted_at': deposit.created_at}


@app.get('/finance/institutions/{institution_id}/collection-customers', tags=TAG)
def collection_customers(institution_id: int, user: CurrentUser, db: Db,
                         search: str = Query('', max_length=120), offset: int = Query(0, ge=0),
                         deposits: bool = False):
    member(db, institution_id, user.id, 'repay')
    visible_loans = scoped_loan_ids(institution_id, user.id)
    query = select(LoanAccount.id, User.full_name, Farm.name).join(
        Farm, Farm.id == LoanAccount.farm_id,
    ).join(User, User.id == Farm.owner_id).where(
        LoanAccount.id.in_(visible_loans),
        LoanAccount.status.in_(('active', 'repaid')) if deposits else LoanAccount.status == 'active',
    )
    term = search.strip().lower()
    if term:
        number = term.removeprefix('aqua-loan-')
        conditions = [func.lower(User.full_name).contains(term, autoescape=True),
                      func.lower(Farm.name).contains(term, autoescape=True)]
        if number.isascii() and number.isdecimal() and len(number) <= 9:
            conditions.append(LoanAccount.id == int(number))
        query = query.where(or_(*conditions))
    if deposits:
        eligible = query.with_only_columns(
            User.id.label('customer_id'), func.max(LoanAccount.id).label('loan_id'),
        ).group_by(User.id).subquery()
        query = select(LoanAccount.id, User.full_name, Farm.name).join(
            Farm, Farm.id == LoanAccount.farm_id,
        ).join(User, User.id == Farm.owner_id).join(eligible, eligible.c.loan_id == LoanAccount.id)
    rows = db.execute(query.order_by(User.full_name, LoanAccount.id).offset(offset).limit(26)).all()
    return {'items': [
        {'loan_id': loan_id, 'account_number': collection_account_number(loan_id),
         'customer_name': customer, 'farm_name': farm}
        for loan_id, customer, farm in rows[:25]
    ], 'has_more': len(rows) > 25}


@app.get('/finance/institutions/{institution_id}/disbursements', tags=TAG)
def institution_disbursements(institution_id: int, user: CurrentUser, db: Db,
                              offset: int = Query(0, ge=0)):
    member(db, institution_id, user.id)
    visible_loans = scoped_loan_ids(institution_id, user.id)
    disbursed = select(
        LoanDisbursement.loan_id,
        func.sum(LoanDisbursement.amount_pesewas).label('amount'),
    ).join(LoanAccount, LoanAccount.id == LoanDisbursement.loan_id).where(
        LoanAccount.id.in_(visible_loans),
    ).group_by(LoanDisbursement.loan_id).subquery()
    recovered = select(
        LoanRepayment.loan_id,
        func.sum(LoanRepayment.amount_pesewas).label('amount'),
        func.sum(LoanRepayment.principal_pesewas).label('principal'),
    ).join(LoanAccount, LoanAccount.id == LoanRepayment.loan_id).where(
        LoanAccount.id.in_(visible_loans),
    ).group_by(LoanRepayment.loan_id).subquery()
    amounts = select(
        disbursed.c.loan_id, disbursed.c.amount.label('disbursed'),
        func.coalesce(recovered.c.amount, 0).label('recovered'),
        func.coalesce(recovered.c.principal, 0).label('principal'),
    ).outerjoin(recovered, recovered.c.loan_id == disbursed.c.loan_id).subquery()

    def summary(disbursed_amount, recovered_amount, principal_amount):
        return {
            'disbursed_ghs': ghs(disbursed_amount),
            'recovered_ghs': ghs(recovered_amount),
            'principal_recovered_ghs': ghs(principal_amount),
            'principal_recovery_percent': round(100 * principal_amount / disbursed_amount, 2)
            if disbursed_amount else None,
        }

    totals = db.execute(select(
        func.coalesce(func.sum(amounts.c.disbursed), 0),
        func.coalesce(func.sum(amounts.c.recovered), 0),
        func.coalesce(func.sum(amounts.c.principal), 0),
    )).one()
    rows = db.execute(select(
        amounts.c.loan_id, User.full_name, LoanAccount.status,
        amounts.c.disbursed, amounts.c.recovered, amounts.c.principal,
    ).select_from(amounts).join(LoanAccount, LoanAccount.id == amounts.c.loan_id).join(
        Farm, Farm.id == LoanAccount.farm_id,
    ).join(User, User.id == Farm.owner_id).order_by(
        User.full_name, amounts.c.loan_id,
    ).offset(offset).limit(26)).all()
    return {'totals': summary(*totals), 'has_more': len(rows) > 25, 'items': [
        {'loan_id': loan_id, 'account_number': collection_account_number(loan_id),
         'customer_name': name, 'status': status, **summary(sent, paid, principal)}
        for loan_id, name, status, sent, paid, principal in rows[:25]
    ]}


@app.get('/finance/institutions/{institution_id}/collections', tags=TAG)
def daily_collections(institution_id: int, user: CurrentUser, db: Db,
                      day: date | None = None, offset: int = Query(0, ge=0)):
    member(db, institution_id, user.id, 'repay')
    visible_loans = scoped_loan_ids(institution_id, user.id)
    from .daily_reminders import local_now
    day = day or local_now().date()
    filters = (LoanAccount.id.in_(visible_loans), LoanRepayment.paid_on == day)
    query = select(LoanRepayment, User.full_name, LoanEvidence.id, LoanEvidence.media_type,
                   func.coalesce(CollectionDeposit.amount_pesewas, 0)).select_from(
        LoanRepayment,
    ).join(LoanAccount, LoanAccount.id == LoanRepayment.loan_id).join(
        Farm, Farm.id == LoanAccount.farm_id,
    ).join(User, User.id == Farm.owner_id).outerjoin(
        LoanEvidence, (LoanEvidence.loan_id == LoanRepayment.loan_id)
        & (LoanEvidence.record_type == 'repayment') & (LoanEvidence.record_id == LoanRepayment.id),
    ).outerjoin(CollectionDeposit, CollectionDeposit.repayment_id == LoanRepayment.id).where(*filters)
    rows = db.execute(query.order_by(LoanRepayment.id.desc()).offset(offset).limit(26)).all()
    total, count, deposited_total = db.execute(select(
        func.coalesce(func.sum(LoanRepayment.amount_pesewas), 0), func.count(LoanRepayment.id),
        func.coalesce(func.sum(CollectionDeposit.amount_pesewas), 0),
    ).select_from(LoanRepayment).join(LoanAccount, LoanAccount.id == LoanRepayment.loan_id)
      .outerjoin(CollectionDeposit, CollectionDeposit.repayment_id == LoanRepayment.id).where(*filters)).one()
    deposit_filters = (StandaloneDeposit.institution_id == institution_id, StandaloneDeposit.paid_on == day,
                       StandaloneDeposit.evidence_id.in_(select(LoanEvidence.id).where(LoanEvidence.loan_id.in_(visible_loans))))
    standalone_total, standalone_count = db.execute(select(
        func.coalesce(func.sum(StandaloneDeposit.amount_pesewas), 0), func.count(StandaloneDeposit.id),
    ).where(*deposit_filters)).one()
    standalone_rows = db.execute(select(StandaloneDeposit, User.full_name, LoanEvidence.media_type)
        .join(User, User.id == StandaloneDeposit.customer_id)
        .join(LoanEvidence, LoanEvidence.id == StandaloneDeposit.evidence_id)
        .where(*deposit_filters).order_by(StandaloneDeposit.id.desc()).offset(offset).limit(26)).all()
    deposited_total += standalone_total
    return {'day': day, 'total_ghs': ghs(total), 'deposited_ghs': ghs(deposited_total),
            'standalone_count': standalone_count, 'standalone_items': [
                {'id': row.id, 'customer_name': name, 'reference': row.reference,
                 'deposited_ghs': ghs(row.amount_pesewas), 'evidence_id': row.evidence_id,
                 'evidence_media_type': media_type}
                for row, name, media_type in standalone_rows[:25]
            ],
            'total_received_ghs': ghs(total + deposited_total), 'count': count, 'has_more': len(rows) > 25 or len(standalone_rows) > 25,
            'items': [
                {'id': row.id, 'loan_id': row.loan_id, 'account_number': collection_account_number(row.loan_id),
                 'customer_name': customer, 'amount_ghs': ghs(row.amount_pesewas), 'reference': row.reference,
                 'deposited_ghs': ghs(deposited), 'total_received_ghs': ghs(row.amount_pesewas + deposited),
                 'posted_at': row.created_at, 'collector_id': row.recorded_by, 'evidence_id': evidence_id,
                 'evidence_media_type': media_type}
                for row, customer, evidence_id, media_type, deposited in rows[:25]
            ]}


@app.get('/finance/my-collection-deposits', tags=TAG)
def my_collection_deposits(user: CurrentUser, db: Db):
    excess = select(LoanAccount.institution_id.label('institution_id'),
                    CollectionDeposit.amount_pesewas.label('amount')).select_from(CollectionDeposit).join(
        LoanRepayment, LoanRepayment.id == CollectionDeposit.repayment_id,
    ).join(LoanAccount, LoanAccount.id == LoanRepayment.loan_id).where(CollectionDeposit.customer_id == user.id)
    standalone = select(StandaloneDeposit.institution_id, StandaloneDeposit.amount_pesewas).where(
        StandaloneDeposit.customer_id == user.id,
    )
    deposits = excess.union_all(standalone).subquery()
    rows = db.execute(select(Institution.id, Institution.name, func.sum(deposits.c.amount)).join(
        deposits, deposits.c.institution_id == Institution.id,
    ).group_by(Institution.id, Institution.name).order_by(Institution.name, Institution.id)).all()
    return [{'institution_id': institution_id, 'institution': name, 'recorded_deposits_ghs': ghs(amount)}
            for institution_id, name, amount in rows]



@app.get('/finance/loans/{loan_id}',tags=TAG)
def lender_loan(loan_id:int,user:CurrentUser,db:Db):
    return view(db,loan_for_view(db,loan_id,user))

@app.get('/farms/{farm_id}/loans',tags=TAG)
def farmer_loans(farm_id:int,user:CurrentUser,db:Db):
    owned_farm(farm_id,user,db)
    return [view(db,loan) for loan in db.scalars(select(LoanAccount).where(LoanAccount.farm_id==farm_id).order_by(LoanAccount.id.desc())).all()]

@app.get('/finance/institutions/{institution_id}/loans',tags=TAG)
def lender_loans(institution_id:int,user:CurrentUser,db:Db):
    member(db,institution_id,user.id)
    return [view(db,loan) for loan in db.scalars(select(LoanAccount).where(LoanAccount.id.in_(scoped_loan_ids(institution_id,user.id))).order_by(LoanAccount.id.desc())).all()]

@app.get('/finance/institutions/{institution_id}/portfolio',tags=TAG)
def lender_portfolio(institution_id:int,user:CurrentUser,db:Db):
    member(db,institution_id,user.id)
    loans=db.scalars(select(LoanAccount).where(LoanAccount.id.in_(scoped_loan_ids(institution_id,user.id)))).all()
    today=date.today()
    totals={'disbursed':0,'collected':0,'outstanding_principal':0,'outstanding_interest':0,
            'outstanding_fees':0,'due_through_today':0,'overdue_amount':0,'overdue_loans':0}
    for loan in loans:
        disbursed,paid_principal,paid_interest,scheduled_total_interest=sums(db,loan)
        fees=loan_fee_total(loan) if loan.status in ('active','repaid') else 0
        fees_paid=db.scalar(select(func.coalesce(func.sum(LoanRepayment.fees_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
        paid=paid_principal+paid_interest+fees_paid
        outstanding_principal=disbursed-paid_principal
        outstanding_interest=scheduled_total_interest-paid_interest
        totals['disbursed']+=disbursed
        totals['collected']+=paid
        totals['outstanding_principal']+=outstanding_principal
        totals['outstanding_interest']+=outstanding_interest
        totals['outstanding_fees']+=fees-fees_paid
        cumulative=0
        previous_unpaid=0
        overdue_amount=0
        if loan.status in ('active','repaid'):
            for installment in db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id==loan.id).order_by(LoanInstallment.number)).all():
                installment_total=installment.principal_pesewas+installment.interest_pesewas+installment.fees_pesewas
                cumulative+=installment_total
                if installment.due_on<=today:
                    totals['due_through_today']+=installment_total
                unpaid_to_date=max(0,cumulative-paid)
                installment_unpaid=max(0,unpaid_to_date-previous_unpaid)
                if installment.due_on<today:
                    overdue_amount+=installment_unpaid
                previous_unpaid=unpaid_to_date
        if overdue_amount:
            totals['overdue_loans']+=1
            totals['overdue_amount']+=overdue_amount
    total_balance=totals['outstanding_principal']+totals['outstanding_interest']
    total_balance+=totals['outstanding_fees']
    due=totals['due_through_today']
    performance=round(min(totals['collected'],due)/due*100,2) if due else None
    return {'institution_id':institution_id,'loan_accounts':len(loans),
        'active_loans':sum(loan.status=='active' for loan in loans),
        'total_disbursements_ghs':ghs(totals['disbursed']),
        'total_collections_ghs':ghs(totals['collected']),
        'principal_recovery_percent':round(
            100 * (totals['disbursed'] - totals['outstanding_principal']) / totals['disbursed'], 2
        ) if totals['disbursed'] else None,
        'outstanding_principal_ghs':ghs(totals['outstanding_principal']),
        'outstanding_interest_ghs':ghs(totals['outstanding_interest']),
        'outstanding_fees_ghs':ghs(totals['outstanding_fees']),
        'outstanding_balance_ghs':ghs(total_balance),
        'overdue_loans':totals['overdue_loans'],
        'arrears_ghs':ghs(totals['overdue_amount']),
        'repayment_performance_pct':performance}

@app.get('/finance/loans/{loan_id}/schedule',tags=TAG)
def loan_schedule(loan_id:int,user:CurrentUser,db:Db):
    loan=loan_for_view(db,loan_id,user)
    rows = db.scalars(select(LoanInstallment).where(
        LoanInstallment.loan_id == loan.id,
    ).order_by(LoanInstallment.number)).all()
    if not rows and loan.status in ('offered', 'awaiting_disbursement') and loan.frequency != 'custom':
        rows = list(standard_installments(loan, loan.approved_pesewas))
    return [{'number':x.number,'due_on':x.due_on,'principal_ghs':ghs(x.principal_pesewas),
             'interest_ghs':ghs(x.interest_pesewas),'fees_ghs':ghs(x.fees_pesewas),
             'total_ghs':ghs(x.principal_pesewas+x.interest_pesewas+x.fees_pesewas)}
            for x in rows]

@app.get('/finance/loans/{loan_id}/transactions',tags=TAG)
def loan_transactions(loan_id:int,user:CurrentUser,db:Db):
    loan=loan_for_view(db,loan_id,user)
    dis=[]
    for row in db.scalars(select(LoanDisbursement).where(LoanDisbursement.loan_id==loan.id)).all():
        evidence=db.scalar(select(LoanEvidence).where(
            LoanEvidence.loan_id==loan.id,LoanEvidence.record_type=='disbursement',LoanEvidence.record_id==row.id))
        dis.append({'type':'disbursement','date':row.disbursed_on,'reference':row.reference,
            'amount_ghs':ghs(row.amount_pesewas),'recorded_by':row.recorded_by,
            'evidence_id':evidence.id if evidence else None,
            'evidence_media_type':evidence.media_type if evidence else None,
            'evidence_metadata':loan_evidence_view(evidence) if evidence else None})
    rep=[]
    for row in db.scalars(select(LoanRepayment).where(LoanRepayment.loan_id==loan.id)).all():
        evidence=db.scalar(select(LoanEvidence).where(
            LoanEvidence.loan_id==loan.id,LoanEvidence.record_type=='repayment',LoanEvidence.record_id==row.id))
        rep.append({'type':'repayment','date':row.paid_on,'reference':row.reference,
            'amount_ghs':ghs(row.amount_pesewas),'principal_ghs':ghs(row.principal_pesewas),
            'interest_ghs':ghs(row.interest_pesewas),'fees_ghs':ghs(row.fees_pesewas),
            'recorded_by':row.recorded_by,'evidence_id':evidence.id if evidence else None,
            'evidence_media_type':evidence.media_type if evidence else None,
            'evidence_metadata':loan_evidence_view(evidence) if evidence else None})
    return sorted(dis+rep,key=lambda x:(x['date'],x['reference']))

@app.get('/farms/{farm_id}/loan-reminders',tags=TAG)
def farmer_reminders(farm_id:int,user:CurrentUser,db:Db):
    owned_farm(farm_id,user,db)
    result=[]; today=date.today()
    for loan in db.scalars(select(LoanAccount).where(LoanAccount.farm_id==farm_id,LoanAccount.status=='active')).all():
        _,paid_p,paid_i,_=sums(db,loan)
        fees_paid=db.scalar(select(func.coalesce(func.sum(LoanRepayment.fees_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
        paid=paid_p+paid_i+fees_paid
        cumulative=0
        for inst in db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id==loan.id).order_by(LoanInstallment.number)).all():
            cumulative+=inst.principal_pesewas+inst.interest_pesewas+inst.fees_pesewas
            unpaid=max(0,cumulative-paid)
            if unpaid and inst.due_on<=date.fromordinal(today.toordinal()+30):
                result.append({'loan_id':loan.id,'installment':inst.number,'due_on':inst.due_on,
                    'amount_due_to_date_ghs':ghs(unpaid),'status':'overdue' if inst.due_on<today else 'upcoming'})
    return result
