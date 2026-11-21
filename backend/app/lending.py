"""Phase 0008: consent-based loan applications and institution appraisal (no money movement)."""
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, func
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, User, Farm, owned_farm, audit
from .dashboard import build_dashboard


def now(): return datetime.now(timezone.utc)
def pesewas(x): return int((Decimal(str(x))*100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
def ghs(x): return round(x/100,2)

class Institution(Base):
    __tablename__ = 'finance_institutions'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    institution_type: Mapped[str] = mapped_column(String(40), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number: Mapped[str] = mapped_column(String(100), nullable=False, default='')
    owner_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class InstitutionMember(Base):
    __tablename__ = 'finance_institution_members'
    __table_args__ = (UniqueConstraint('institution_id','user_id',name='uq_finance_membership'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LoanApplication(Base):
    __tablename__ = 'loan_applications'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'), index=True)
    requested_pesewas: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(1000), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='submitted')
    report_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LoanDecision(Base):
    __tablename__ = 'loan_appraisals'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    approved_pesewas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class InstitutionIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    institution_type: Literal['bank','rural_bank','microfinance','credit_union','other']
    registration_number: str | None = Field(default=None, min_length=3, max_length=100)
    account_number: str | None = Field(default=None, min_length=3, max_length=100)

    @model_validator(mode='after')
    def require_institution_account_number(self):
        account = (self.account_number or self.registration_number or '').strip()
        if len(account) < 3:
            raise ValueError('Account number is required')
        self.account_number = account
        self.registration_number = account
        return self

class MemberIn(BaseModel):
    user_email: str = Field(min_length=3, max_length=255)
    role: Literal['officer','reviewer']

class ApplicationIn(BaseModel):
    institution_id: int = Field(gt=0)
    requested_ghs: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    term_months: int = Field(ge=1, le=240)
    purpose: str = Field(min_length=10, max_length=1000)
    evidence_id: int = Field(gt=0)
    monthly_other_income_ghs: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    monthly_household_expenses_ghs: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    monthly_external_debt_ghs: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    share_report: bool = Field(description='Farmer explicitly authorizes sharing the application appraisal snapshot with this institution.')

class DecisionIn(BaseModel):
    decision: Literal['under_review','more_information','approved','rejected']
    rationale: str = Field(min_length=10, max_length=2000)
    approved_ghs: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


def member(db, institution_id, user_id, roles=('owner','officer','reviewer')):
    institution = db.get(Institution, institution_id)
    if institution is None or institution.status != 'verified':
        raise HTTPException(404, 'Verified institution not found')
    membership = db.scalar(select(InstitutionMember).where(InstitutionMember.institution_id == institution_id, InstitutionMember.user_id == user_id, InstitutionMember.role.in_(roles)))
    if membership is None: raise HTTPException(404, 'Institution not found or access denied')
    return institution


def institution_view(x):
    account_number = getattr(x, 'account_number', None) or x.registration_number
    return {'id':x.id,'name':x.name,'institution_type':x.institution_type,
            'registration_number':account_number,'account_number':account_number,'status':x.status}


def application_view(x, include_report=False):
    import json
    result={'id':x.id,'farm_id':x.farm_id,'institution_id':x.institution_id,'requested_ghs':ghs(x.requested_pesewas),'term_months':x.term_months,'purpose':x.purpose,'status':x.status,'created_at':x.created_at}
    if include_report: result['shared_report_snapshot']=json.loads(x.report_snapshot_json)
    return result


def build_appraisal_snapshot(farm_id, user, db, data):
    from collections import defaultdict
    from .automated_costing import SharedCostAllocation
    from .feeding import FeedLedger, FeedProduct
    from .forecasting import CycleExpense, ProductionPlan, forecast
    from .loan_servicing import (
        LoanAccount, LoanInstallment, LoanEvidence, LoanRepayment,
        loan_evidence_view, loan_fee_total, sums,
    )
    from .operations import FishSample, StockingCycle, population
    from .sales import FishSale, HarvestLot, SalePayment
    from .main import ProductionUnit

    farm = db.get(Farm, farm_id)
    units = db.scalars(select(ProductionUnit).where(ProductionUnit.farm_id == farm_id)).all()
    unit_by_id = {unit.id: unit for unit in units}
    cycles = db.scalars(select(StockingCycle).where(StockingCycle.unit_id.in_(unit_by_id))).all() if units else []
    cycle_ids = [cycle.id for cycle in cycles]
    samples = db.scalars(select(FishSample).where(FishSample.cycle_id.in_(cycle_ids)).order_by(FishSample.sampled_on, FishSample.id)).all() if cycle_ids else []
    samples_by_cycle = defaultdict(list)
    for sample in samples:
        samples_by_cycle[sample.cycle_id].append(sample)
    lots = db.scalars(select(HarvestLot).where(HarvestLot.farm_id == farm_id)).all()
    lots_by_cycle = defaultdict(list)
    for lot in lots:
        lots_by_cycle[lot.cycle_id].append(lot)

    plans = db.scalars(select(ProductionPlan).where(ProductionPlan.farm_id == farm_id).order_by(ProductionPlan.created_at)).all()
    plans_by_cycle = defaultdict(list)
    for plan in plans:
        if plan.cycle_id is not None:
            plans_by_cycle[plan.cycle_id].append(plan)
    forecast_by_plan = {plan.id: forecast(plan, db) for plan in plans}
    production_history = []
    for cycle in sorted(cycles, key=lambda item: (item.stocked_on, item.id)):
        current = population(cycle, db)
        production_history.append({
            'cycle_id': cycle.id,
            'production_unit': unit_by_id[cycle.unit_id].name,
            'species': cycle.species,
            'status': 'closed' if cycle.closed_at else 'active',
            'stocked_on': cycle.stocked_on,
            'fingerlings_stocked': current.stocked_count,
            'initial_average_weight_g': cycle.initial_average_weight_g,
            'estimated_live_fish': current.estimated_live_count,
            'estimated_survival_pct': current.estimated_survival_pct,
            'cumulative_mortality': current.total_mortality,
            'total_harvested_fish': current.total_harvested,
            'transferred_in_fish': current.transfer_in_count,
            'transferred_out_fish': current.transfer_out_count,
            'latest_average_weight_g': current.latest_average_weight_g,
            'latest_sampled_on': current.latest_sampled_on,
            'estimated_live_biomass_kg': current.estimated_biomass_kg,
            'sampling_history': [{
                'sampled_on': sample.sampled_on,
                'sample_count': sample.sample_count,
                'average_weight_g': sample.average_weight_g,
            } for sample in samples_by_cycle[cycle.id]],
            'harvests': [{
                'harvested_on': lot.harvested_on,
                'quantity_kg': lot.quantity_kg,
                'fish_count': lot.fish_count,
            } for lot in sorted(lots_by_cycle[cycle.id], key=lambda item: item.harvested_on)],
            'estimates': [{
                'plan_id': plan.id,
                'expected_harvest_kg': forecast_by_plan[plan.id]['expected_harvest_kg'],
                'expected_revenue_ghs': forecast_by_plan[plan.id]['expected_revenue_ghs'],
                'expected_profit_ghs': forecast_by_plan[plan.id]['expected_profit_ghs'],
                'target_weight_g': plan.target_weight_g,
                'harvest_timing': 'not recorded',
            } for plan in plans_by_cycle[cycle.id]],
        })
    plan_estimates = [{
        'plan_id': plan.id,
        'cycle_id': plan.cycle_id,
        'species': plan.species,
        'expected_harvest_kg': forecast_by_plan[plan.id]['expected_harvest_kg'],
        'expected_revenue_ghs': forecast_by_plan[plan.id]['expected_revenue_ghs'],
        'expected_profit_ghs': forecast_by_plan[plan.id]['expected_profit_ghs'],
        'target_weight_g': plan.target_weight_g,
        'harvest_timing': 'not recorded',
    } for plan in plans]

    plan_ids = [plan.id for plan in plans]
    expenses = db.scalars(select(CycleExpense).where(CycleExpense.plan_id.in_(plan_ids))).all() if plan_ids else []
    allocations = db.scalars(select(SharedCostAllocation).where(SharedCostAllocation.plan_id.in_(plan_ids))).all() if plan_ids else []
    expense_categories = defaultdict(float)
    for expense in expenses:
        expense_categories[expense.category] += expense.amount_ghs
    for allocation in allocations:
        expense_categories[allocation.category] += allocation.amount_ghs

    feed_products = db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id)).all()
    feed_ids = [product.id for product in feed_products]
    feed_ledger = db.scalars(select(FeedLedger).where(FeedLedger.feed_id.in_(feed_ids))).all() if feed_ids else []
    feed_totals = defaultdict(lambda: {'received_kg': 0.0, 'purchase_cost_ghs': 0.0, 'priced_receipts_kg': 0.0, 'consumed_kg': 0.0})
    for entry in feed_ledger:
        totals = feed_totals[entry.feed_id]
        if entry.event_type == 'receipt':
            totals['received_kg'] += entry.quantity_delta_kg
            if entry.cost_ghs is not None:
                totals['purchase_cost_ghs'] += entry.cost_ghs
                totals['priced_receipts_kg'] += entry.quantity_delta_kg
        elif entry.event_type == 'feeding':
            totals['consumed_kg'] += max(0, -entry.quantity_delta_kg)
    feed_summary = []
    estimated_consumed_cost = 0.0
    for product in feed_products:
        totals = feed_totals[product.id]
        average_price = totals['purchase_cost_ghs'] / totals['priced_receipts_kg'] if totals['priced_receipts_kg'] else None
        consumed_cost = totals['consumed_kg'] * average_price if average_price is not None else None
        if consumed_cost is not None:
            estimated_consumed_cost += consumed_cost
        feed_summary.append({
            'feed_product': product.name,
            'received_kg': round(totals['received_kg'], 3),
            'purchase_cash_outflow_ghs': round(totals['purchase_cost_ghs'], 2),
            'consumed_kg': round(totals['consumed_kg'], 3),
            'estimated_consumed_cost_ghs': round(consumed_cost, 2) if consumed_cost is not None else None,
            'consumption_valuation': 'historical weighted-average receipt price; indicative, not FIFO' if consumed_cost is not None else 'not available: no priced receipt',
        })

    report = build_dashboard(farm_id, user, db)
    payments = db.scalars(select(SalePayment).where(SalePayment.farm_id == farm_id)).all()
    sales = db.scalars(select(FishSale).where(FishSale.farm_id == farm_id)).all()
    current_month = date.today().replace(day=1)
    monthly_cashflow = {}
    for offset in range(11, -1, -1):
        month_number = current_month.month - 1 - offset
        year = current_month.year + month_number // 12
        month = month_number % 12 + 1
        key = f'{year:04d}-{month:02d}'
        monthly_cashflow[key] = {
            'month': key,
            'sales_payments_received_ghs': 0.0,
            'feed_purchase_cash_outflow_ghs': 0.0,
            'recorded_operating_expenses_ghs': 0.0,
            'net_recorded_operating_cashflow_ghs': 0.0,
        }
    recent_transaction_count = 0
    for payment in payments:
        key = payment.paid_on.strftime('%Y-%m')
        if key in monthly_cashflow:
            monthly_cashflow[key]['sales_payments_received_ghs'] += ghs(payment.amount_pesewas)
            recent_transaction_count += 1
    for entry in feed_ledger:
        key = entry.occurred_on.strftime('%Y-%m')
        if key in monthly_cashflow and entry.event_type == 'receipt':
            monthly_cashflow[key]['feed_purchase_cash_outflow_ghs'] += entry.cost_ghs or 0
            if entry.cost_ghs is not None:
                recent_transaction_count += 1
    for expense in expenses:
        key = expense.occurred_on.strftime('%Y-%m')
        if key in monthly_cashflow:
            monthly_cashflow[key]['recorded_operating_expenses_ghs'] += expense.amount_ghs
            recent_transaction_count += 1
    for allocation in allocations:
        key = allocation.occurred_on.strftime('%Y-%m')
        if key in monthly_cashflow:
            monthly_cashflow[key]['recorded_operating_expenses_ghs'] += allocation.amount_ghs
            recent_transaction_count += 1
    for month in monthly_cashflow.values():
        month['net_recorded_operating_cashflow_ghs'] = round(
            month['sales_payments_received_ghs']
            - month['feed_purchase_cash_outflow_ghs']
            - month['recorded_operating_expenses_ghs'], 2)

    owned_farm_ids = db.scalars(select(Farm.id).where(Farm.owner_id == user.id)).all()
    loans = db.scalars(select(LoanAccount).where(LoanAccount.farm_id.in_(owned_farm_ids)).order_by(LoanAccount.id)).all() if owned_farm_ids else []
    today = date.today()
    next_year = today + timedelta(days=365)
    loan_summaries = []
    next_year_obligations = 0
    overdue_obligations = 0
    loan_obligations_by_month = defaultdict(int)
    for loan in loans:
        disbursed, repaid_principal, repaid_interest, scheduled_interest_total = sums(db, loan)
        fees_paid = db.scalar(select(func.coalesce(func.sum(LoanRepayment.fees_pesewas),0)).where(LoanRepayment.loan_id==loan.id))
        paid_total = repaid_principal + repaid_interest
        cumulative_due = 0
        previous_unpaid = 0
        next_year_unpaid = 0
        overdue_unpaid = 0
        installments = db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id == loan.id).order_by(LoanInstallment.number)).all()
        next_due_on = None
        for installment in installments:
            cumulative_due += installment.principal_pesewas + installment.interest_pesewas
            unpaid_to_date = max(0, cumulative_due - paid_total)
            installment_unpaid = max(0, unpaid_to_date - previous_unpaid)
            if installment.due_on >= today and installment_unpaid and next_due_on is None:
                next_due_on = installment.due_on
            if installment.due_on < today:
                overdue_unpaid += installment_unpaid
            elif installment.due_on <= next_year:
                next_year_unpaid += installment_unpaid
                loan_obligations_by_month[installment.due_on.strftime('%Y-%m')] += installment_unpaid
            previous_unpaid = unpaid_to_date
        next_year_obligations += next_year_unpaid
        overdue_obligations += overdue_unpaid
        loan_summaries.append({
            'loan_id': loan.id,
            'farm_id': loan.farm_id,
            'status': loan.status,
            'repayment_frequency': loan.frequency,
            'term_months': loan.term_months,
            'annual_flat_interest_percent': loan.annual_flat_rate_bps / 100,
            'first_due_date': loan.first_due_date,
            'approved_ghs': ghs(loan.approved_pesewas),
            'disbursed_ghs': ghs(disbursed),
            'outstanding_principal_ghs': ghs(disbursed - repaid_principal),
            'outstanding_interest_ghs': ghs(scheduled_interest_total - repaid_interest),
            'outstanding_fees_ghs': ghs(loan_fee_total(loan) - fees_paid),
            'total_scheduled_balance_ghs': ghs(
                disbursed - repaid_principal + scheduled_interest_total - repaid_interest
                + loan_fee_total(loan) - fees_paid
            ),
            'next_due_on': next_due_on,
            'next_12_months_scheduled_payments_ghs': ghs(next_year_unpaid),
            'overdue_scheduled_amount_ghs': ghs(overdue_unpaid),
        })

    monthly_farm_cashflow = sum(item['net_recorded_operating_cashflow_ghs'] for item in monthly_cashflow.values()) / 12
    optional_monthly_income = float(data.monthly_other_income_ghs) if data.monthly_other_income_ghs is not None else None
    household_expenses = float(data.monthly_household_expenses_ghs) if data.monthly_household_expenses_ghs is not None else None
    external_debt = float(data.monthly_external_debt_ghs) if data.monthly_external_debt_ghs is not None else None
    has_capacity_inputs = all(value is not None for value in (optional_monthly_income, household_expenses, external_debt))
    monthly_existing_debt = next_year_obligations / 100 / 12
    monthly_surplus = None
    if has_capacity_inputs and recent_transaction_count:
        monthly_surplus = round(
            monthly_farm_cashflow + optional_monthly_income - household_expenses
            - external_debt - monthly_existing_debt, 2)
    projected_months = []
    for offset in range(12):
        month_number = current_month.month - 1 + offset
        year = current_month.year + month_number // 12
        month = month_number % 12 + 1
        key = f'{year:04d}-{month:02d}'
        scheduled_debt = round(loan_obligations_by_month[key] / 100, 2)
        projected_net = None
        if has_capacity_inputs and recent_transaction_count:
            projected_net = round(
                monthly_farm_cashflow + optional_monthly_income - household_expenses
                - external_debt - scheduled_debt, 2)
        projected_months.append({
            'month': key,
            'assumed_farm_operating_cashflow_ghs': round(monthly_farm_cashflow, 2) if recent_transaction_count else None,
            'farmer_declared_other_income_ghs': optional_monthly_income,
            'farmer_declared_household_expenses_ghs': household_expenses,
            'farmer_declared_external_debt_payments_ghs': external_debt,
            'tracked_loan_scheduled_payments_ghs': scheduled_debt,
            'projected_net_cashflow_after_obligations_ghs': projected_net,
        })

    application_video = db.get(LoanEvidence, data.evidence_id)
    return {
        'farmer': {'user_id': user.id, 'full_name': user.full_name, 'email': user.email},
        'farm': {'farm_id': farm.id, 'name': farm.name, 'region': farm.region, 'district': farm.district,
                 'farm_type': farm.farm_type, 'species': farm.species},
        'application': {'requested_ghs': float(data.requested_ghs), 'term_months': data.term_months, 'purpose': data.purpose},
        'currency': 'GHS',
        'production': report['production'],
        'production_history': production_history,
        'production_estimates': plan_estimates,
        'feed': report['feed'],
        'feed_costs': {
            'by_product': feed_summary,
            'recorded_operating_expenses_by_category_ghs': {key: round(value, 2) for key, value in sorted(expense_categories.items())},
            'estimated_consumed_feed_cost_ghs': round(estimated_consumed_cost, 2),
            'note': 'Feed purchases are cash outflows and inventory acquisitions; consumed-feed cost is a separate indicative weighted-average estimate.',
        },
        'sales': {
            **report['sales'],
            'invoiced_sales_revenue_ghs': report['sales']['invoiced_revenue_ghs'],
            'payments_received_ghs': report['sales']['payments_received_ghs'],
            'outstanding_customer_credit_ghs': report['sales']['outstanding_receivables_ghs'],
        },
        'costs': report['costs'],
        'cash_flow': {
            'historical_months': list(monthly_cashflow.values()),
            'projected_months': projected_months,
            'average_recorded_monthly_operating_cashflow_ghs': round(monthly_farm_cashflow, 2),
            'farmer_declared_monthly_other_income_ghs': optional_monthly_income,
            'farmer_declared_monthly_household_expenses_ghs': household_expenses,
            'farmer_declared_monthly_external_debt_payments_ghs': external_debt,
            'tracked_existing_loans_monthly_scheduled_payment_ghs': round(monthly_existing_debt, 2),
            'tracked_existing_loans_next_12_months_scheduled_payments_ghs': ghs(next_year_obligations),
            'tracked_existing_loans_overdue_scheduled_payments_ghs': ghs(overdue_obligations),
            'estimated_monthly_surplus_after_obligations_ghs': monthly_surplus,
            'estimated_monthly_repayment_capacity_ghs': max(0, monthly_surplus) if monthly_surplus is not None else None,
            'requested_principal_divided_by_term_ghs': round(float(data.requested_ghs) / data.term_months, 2),
            'notes': [
                'Historical cash flow uses recorded sale payments, feed receipt costs, and plan-linked expenses for the last 12 calendar months; empty months count as zero.',
                'Projected months assume the historical average farm operating cash flow repeats; undated plan harvest forecasts are excluded.',
                'Optional household income, expenses, and debts are farmer-declared and were not independently verified.',
                'Capacity is an indicative estimate, not an affordability decision; requested principal divided by term excludes interest and fees.',
                'Recorded expenses may overlap feed purchases or other plan entries; review categories before adding totals.',
            ],
        },
        'existing_loans': loan_summaries,
        'appraisal_data_completeness': {
            'external_income_provided': optional_monthly_income is not None,
            'household_expenses_provided': household_expenses is not None,
            'external_debt_obligations_provided': external_debt is not None,
            'production_plan_count': len(plans),
            'tracked_loan_count': len(loans),
            'sales_payment_count': len(payments),
            'sales_count': len(sales),
            'recent_cashflow_transaction_count': recent_transaction_count,
        },
        'application_video_media_type': application_video.media_type,
        'application_video_evidence': loan_evidence_view(application_video),
        'warnings': report['warnings'] + [
            'Production estimates, farmer-declared figures, and recorded transactions are not independently verified.',
            'No farm GPS coordinates or customer identities are included in this lender snapshot.',
        ],
        'disclaimer': 'Farmer-authorized application appraisal data; not independently verified and not a credit decision.',
    }


@app.post('/finance/institutions', status_code=201, tags=['Financial institutions and loan appraisal'])
def create_institution(data: InstitutionIn, user: CurrentUser, db: Db):
    institution=Institution(**data.model_dump(),owner_user_id=user.id,status='pending')
    db.add(institution); db.flush()
    db.add(InstitutionMember(institution_id=institution.id,user_id=user.id,role='owner'))
    audit(db,user,'create','finance_institution',institution.id); db.commit(); db.refresh(institution)
    return institution_view(institution)

@app.get('/finance/institutions', tags=['Financial institutions and loan appraisal'])
def verified_institutions(user: CurrentUser, db: Db):
    return [institution_view(x) for x in db.scalars(select(Institution).where(Institution.status=='verified').order_by(Institution.name)).all()]

@app.get('/finance/institutions/mine', tags=['Financial institutions and loan appraisal'])
def my_institutions(user: CurrentUser, db: Db):
    memberships=db.scalars(select(InstitutionMember).where(InstitutionMember.user_id==user.id)).all()
    roles={membership.institution_id:membership.role for membership in memberships}
    institutions=db.scalars(select(Institution).where(Institution.id.in_(roles)).order_by(Institution.id)).all()
    return [{**institution_view(institution),'role':roles[institution.id]} for institution in institutions]

def require_platform_admin(user: CurrentUser):
    admin_email=os.getenv('AQUAFARM_PLATFORM_ADMIN_EMAIL','').strip().lower()
    if not admin_email or user.email.lower()!=admin_email:
        raise HTTPException(403,'Platform administrator access required')

@app.get('/finance/admin/institutions/pending', tags=['Financial institutions and loan appraisal'])
def pending_institutions(user: CurrentUser, db: Db):
    require_platform_admin(user)
    institutions=db.scalars(select(Institution).where(Institution.status=='pending').order_by(Institution.created_at)).all()
    return [institution_view(x) for x in institutions]

@app.post('/finance/institutions/{institution_id}/verify', tags=['Financial institutions and loan appraisal'])
def verify_institution(institution_id: int, user: CurrentUser, db: Db):
    # Separate, configured platform administrator; registration never grants verification.
    admin_email=os.getenv('AQUAFARM_PLATFORM_ADMIN_EMAIL','').strip().lower()
    if not admin_email or user.email.lower()!=admin_email:
        raise HTTPException(403,'Platform administrator access required')
    inst=db.get(Institution,institution_id)
    if inst is None: raise HTTPException(404,'Institution not found')
    inst.status='verified'; audit(db,user,'verify','finance_institution',inst.id); db.commit()
    return institution_view(inst)

@app.post('/finance/institutions/{institution_id}/reject', tags=['Financial institutions and loan appraisal'])
def reject_institution(institution_id: int, user: CurrentUser, db: Db):
    require_platform_admin(user)
    inst=db.get(Institution,institution_id)
    if inst is None: raise HTTPException(404,'Institution not found')
    inst.status='rejected'; audit(db,user,'reject','finance_institution',inst.id); db.commit()
    return institution_view(inst)

@app.post('/finance/institutions/{institution_id}/members', tags=['Financial institutions and loan appraisal'])
def add_member(institution_id: int, data: MemberIn, user: CurrentUser, db: Db):
    member(db,institution_id,user.id,('owner',))
    target=db.scalar(select(User).where(func.lower(User.email)==data.user_email.lower()))
    if target is None: raise HTTPException(404,'User not found; user must register first')
    existing=db.scalar(select(InstitutionMember).where(InstitutionMember.institution_id==institution_id,InstitutionMember.user_id==target.id))
    if existing: raise HTTPException(409,'Already a member')
    db.add(InstitutionMember(institution_id=institution_id,user_id=target.id,role=data.role))
    audit(db,user,'add_member','finance_institution',institution_id); db.commit()
    return {'institution_id':institution_id,'user_id':target.id,'role':data.role}

@app.post('/farms/{farm_id}/loan-applications', status_code=201, tags=['Financial institutions and loan appraisal'])
def submit_application(farm_id:int,data:ApplicationIn,user:CurrentUser,db:Db):
    import json
    from .loan_servicing import required_loan_evidence

    owned_farm(farm_id,user,db)
    inst=db.get(Institution,data.institution_id)
    if inst is None or inst.status!='verified': raise HTTPException(404,'Verified institution not found')
    if not data.share_report: raise HTTPException(422,'Explicit report-sharing consent is required')
    evidence=required_loan_evidence(db,data.evidence_id,farm_id,'loan_application',user.id)
    safe=build_appraisal_snapshot(farm_id,user,db,data)
    safe['application_video_evidence_id']=evidence.id
    obj=LoanApplication(farm_id=farm_id,institution_id=inst.id,requested_pesewas=pesewas(data.requested_ghs),term_months=data.term_months,purpose=data.purpose,status='submitted',report_snapshot_json=json.dumps(safe,default=str))
    db.add(obj); db.flush()
    evidence.application_id=obj.id
    audit(db,user,'submit','loan_application',obj.id,json.dumps({'evidence_id':evidence.id}))
    db.commit(); db.refresh(obj)
    result=application_view(obj)
    result['evidence_id']=evidence.id
    return result

@app.get('/farms/{farm_id}/loan-applications', tags=['Financial institutions and loan appraisal'])
def farmer_applications(farm_id:int,user:CurrentUser,db:Db):
    owned_farm(farm_id,user,db)
    return [application_view(x) for x in db.scalars(select(LoanApplication).where(LoanApplication.farm_id==farm_id).order_by(LoanApplication.id.desc())).all()]

@app.get('/finance/institutions/{institution_id}/applications', tags=['Financial institutions and loan appraisal'])
def lender_applications(institution_id:int,user:CurrentUser,db:Db):
    member(db,institution_id,user.id)
    return [application_view(x) for x in db.scalars(select(LoanApplication).where(LoanApplication.institution_id==institution_id).order_by(LoanApplication.id.desc())).all()]

@app.get('/finance/institutions/{institution_id}/applications/{application_id}', tags=['Financial institutions and loan appraisal'])
def lender_application(institution_id:int,application_id:int,user:CurrentUser,db:Db):
    member(db,institution_id,user.id)
    obj=db.scalar(select(LoanApplication).where(LoanApplication.id==application_id,LoanApplication.institution_id==institution_id))
    if obj is None: raise HTTPException(404,'Application not found')
    result=application_view(obj,True)
    result['appraisals']=[{'decision':d.decision,'rationale':d.rationale,'approved_ghs':ghs(d.approved_pesewas) if d.approved_pesewas is not None else None,'created_at':d.created_at} for d in db.scalars(select(LoanDecision).where(LoanDecision.application_id==obj.id).order_by(LoanDecision.id)).all()]
    return result

@app.post('/finance/institutions/{institution_id}/applications/{application_id}/appraise', tags=['Financial institutions and loan appraisal'])
def appraise(institution_id:int,application_id:int,data:DecisionIn,user:CurrentUser,db:Db):
    member(db,institution_id,user.id,('owner','reviewer'))
    obj=db.scalar(select(LoanApplication).where(LoanApplication.id==application_id,LoanApplication.institution_id==institution_id))
    if obj is None: raise HTTPException(404,'Application not found')
    if obj.status in ('approved','rejected'): raise HTTPException(409,'Final decision already recorded')
    if data.decision=='approved' and data.approved_ghs is None: raise HTTPException(422,'Approved amount required')
    if data.decision!='approved' and data.approved_ghs is not None: raise HTTPException(422,'Approved amount only valid for approval')
    if data.approved_ghs is not None and pesewas(data.approved_ghs)>obj.requested_pesewas:
        raise HTTPException(422,'Approved amount cannot exceed the requested amount')
    obj.status=data.decision; obj.updated_at=now()
    db.add(LoanDecision(application_id=obj.id,reviewer_user_id=user.id,decision=data.decision,rationale=data.rationale,approved_pesewas=pesewas(data.approved_ghs) if data.approved_ghs is not None else None))
    audit(db,user,'appraise','loan_application',obj.id); db.commit()
    return {'application_id':obj.id,'status':obj.status,'approved_ghs':float(data.approved_ghs) if data.approved_ghs is not None else None}
