"""Production forecasts and cost-based selling price planning (GHS)."""
from datetime import date, datetime, timezone
from math import ceil
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, audit, owned_farm
from .operations import owned_cycle, StockingCycle
from .feeding import FeedLedger


def now():
    return datetime.now(timezone.utc)


class ProductionPlan(Base):
    __tablename__ = 'production_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey('stocking_cycles.id'), nullable=True, index=True)
    species: Mapped[str] = mapped_column(String(100))
    fingerling_count: Mapped[int] = mapped_column(Integer)
    initial_weight_g: Mapped[float] = mapped_column(Float)
    target_weight_g: Mapped[float] = mapped_column(Float)
    survival_pct: Mapped[float] = mapped_column(Float)
    expected_fcr: Mapped[float] = mapped_column(Float)
    feed_price_ghs_per_kg: Mapped[float] = mapped_column(Float)
    bag_size_kg: Mapped[float] = mapped_column(Float)
    fingerling_cost_ghs: Mapped[float] = mapped_column(Float)
    other_budget_ghs: Mapped[float] = mapped_column(Float)
    desired_profit_pct: Mapped[float] = mapped_column(Float)
    profit_method: Mapped[str] = mapped_column(String(12))
    market_price_ghs_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CycleExpense(Base):
    __tablename__ = 'cycle_expenses'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('production_plans.id'), index=True)
    category: Mapped[str] = mapped_column(String(40))
    amount_ghs: Mapped[float] = mapped_column(Float)
    occurred_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanIn(BaseModel):
    species: str = Field(min_length=2, max_length=100)
    fingerling_count: int = Field(gt=0)
    initial_weight_g: float = Field(gt=0)
    target_weight_g: float = Field(gt=0)
    survival_pct: float = Field(default=90, ge=0, le=100)
    expected_fcr: float = Field(default=1.5, gt=0, le=10)
    feed_price_ghs_per_kg: float = Field(ge=0)
    bag_size_kg: float = Field(default=25, gt=0)
    fingerling_cost_ghs: float = Field(default=0, ge=0)
    other_budget_ghs: float = Field(default=0, ge=0)
    desired_profit_pct: float = Field(default=25, ge=0, le=500)
    profit_method: Literal['markup', 'margin'] = 'markup'
    cycle_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def validate_plan(self):
        if self.target_weight_g <= self.initial_weight_g:
            raise ValueError('Target weight must exceed initial weight')
        if self.profit_method == 'margin' and self.desired_profit_pct >= 100:
            raise ValueError('Profit margin must be below 100%')
        return self


class ExpenseIn(BaseModel):
    category: Literal['labour', 'electricity', 'water', 'fuel', 'health', 'maintenance', 'harvest', 'transport', 'equipment', 'fingerlings', 'feed', 'other']
    amount_ghs: float = Field(gt=0)
    occurred_on: date
    notes: str | None = Field(default=None, max_length=2000)


def calculate(data, additional_cost_ghs=0.0):
    """Simplified planning model; not a biological growth prediction.

    Biomass change approximates feed demand. Mortality timing, feed stages,
    stock already purchased, and growth duration are not modeled.
    """
    survivors = round(data.fingerling_count * data.survival_pct / 100)
    harvest_kg = survivors * data.target_weight_g / 1000
    initial_kg = data.fingerling_count * data.initial_weight_g / 1000
    biomass_gain_kg = max(0.0, harvest_kg - initial_kg)
    feed_kg = biomass_gain_kg * data.expected_fcr
    bags = ceil(feed_kg / data.bag_size_kg) if feed_kg else 0
    feed_budget = feed_kg * data.feed_price_ghs_per_kg
    base_cost = feed_budget + data.fingerling_cost_ghs + data.other_budget_ghs
    total_cost = base_cost + additional_cost_ghs
    cost_per_kg = total_cost / harvest_kg if harvest_kg > 0 else None
    if cost_per_kg is None:
        price = None
    elif data.profit_method == 'markup':
        price = cost_per_kg * (1 + data.desired_profit_pct / 100)
    else:
        price = cost_per_kg / (1 - data.desired_profit_pct / 100)
    r = lambda x: round(x, 2) if x is not None else None
    return {'fingerlings_stocked': data.fingerling_count,
            'expected_survivors': survivors,
            'expected_harvest_kg': r(harvest_kg),
            'estimated_feed_kg': r(feed_kg),
            'estimated_feed_bags': bags,
            'bag_size_kg': data.bag_size_kg,
            'estimated_feed_budget_ghs': r(feed_budget),
            'planned_other_costs_ghs': r(data.fingerling_cost_ghs + data.other_budget_ghs),
            'recorded_extra_expenses_ghs': r(additional_cost_ghs),
            'estimated_total_cost_ghs': r(total_cost),
            'break_even_ghs_per_kg': r(cost_per_kg),
            'desired_profit_pct': data.desired_profit_pct,
            'profit_method': data.profit_method,
            'recommended_price_ghs_per_kg': r(price),
            'expected_revenue_ghs': r(price * harvest_kg) if price is not None else None,
            'expected_profit_ghs': r(price * harvest_kg - total_cost) if price is not None else None,
            'currency': 'GHS',
            'warnings': ['Planning estimate only; actual growth, survival and FCR may differ.',
                         'Feed is estimated from net biomass gain; mortality timing is not modeled.',
                         'Enter all relevant costs to avoid underpricing; expenses must not duplicate planned costs.',
                         'Selling price is cost-based, not a live market quotation.']}


def owned_plan(farm_id, plan_id, user, db):
    owned_farm(farm_id, user, db)
    plan = db.scalar(select(ProductionPlan).where(ProductionPlan.id == plan_id, ProductionPlan.farm_id == farm_id))
    if plan is None:
        raise HTTPException(404, 'Production plan not found')
    return plan


def forecast(plan, db):
    expenses = db.scalars(select(CycleExpense).where(CycleExpense.plan_id == plan.id)).all()
    return {'plan_id': plan.id, 'farm_id': plan.farm_id, 'cycle_id': plan.cycle_id,
            **calculate(plan, sum(x.amount_ghs for x in expenses))}


@app.post('/farms/{farm_id}/production-plans/preview', tags=['Production forecasting'])
def preview_plan(farm_id: int, data: PlanIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    if data.cycle_id is not None:
        verify_cycle(farm_id, data.cycle_id, user, db)
    return calculate(data)


def verify_cycle(farm_id, cycle_id, user, db):
    cycle = db.get(StockingCycle, cycle_id)
    if cycle is None:
        raise HTTPException(404, 'Stocking cycle not found')
    from .main import ProductionUnit
    unit = db.get(ProductionUnit, cycle.unit_id)
    if unit is None or unit.farm_id != farm_id:
        raise HTTPException(404, 'Stocking cycle not found')
    owned_farm(farm_id, user, db)
    return cycle


@app.post('/farms/{farm_id}/production-plans', status_code=201, tags=['Production forecasting'])
def create_plan(farm_id: int, data: PlanIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    if data.cycle_id is not None:
        verify_cycle(farm_id, data.cycle_id, user, db)
    plan = ProductionPlan(farm_id=farm_id, **data.model_dump())
    db.add(plan); db.flush()
    audit(db, user, 'create', 'production_plan', plan.id)
    db.commit(); db.refresh(plan)
    return forecast(plan, db)


@app.get('/farms/{farm_id}/production-plans', tags=['Production forecasting'])
def list_plans(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    plans = db.scalars(select(ProductionPlan).where(ProductionPlan.farm_id == farm_id).order_by(ProductionPlan.id)).all()
    return [forecast(p, db) for p in plans]


@app.get('/farms/{farm_id}/production-plans/{plan_id}', tags=['Production forecasting'])
def get_plan(farm_id: int, plan_id: int, user: CurrentUser, db: Db):
    return forecast(owned_plan(farm_id, plan_id, user, db), db)


@app.put('/farms/{farm_id}/production-plans/{plan_id}', tags=['Production forecasting'])
def update_plan(farm_id: int, plan_id: int, data: PlanIn, user: CurrentUser, db: Db):
    plan = owned_plan(farm_id, plan_id, user, db)
    if data.cycle_id is not None:
        verify_cycle(farm_id, data.cycle_id, user, db)
    for k, v in data.model_dump().items():
        setattr(plan, k, v)
    audit(db, user, 'update', 'production_plan', plan.id)
    db.commit(); db.refresh(plan)
    return forecast(plan, db)


@app.post('/farms/{farm_id}/production-plans/{plan_id}/expenses', status_code=201, tags=['Production forecasting'])
def add_expense(farm_id: int, plan_id: int, data: ExpenseIn, user: CurrentUser, db: Db):
    plan = owned_plan(farm_id, plan_id, user, db)
    expense = CycleExpense(plan_id=plan.id, **data.model_dump())
    db.add(expense); db.flush()
    audit(db, user, 'create', 'cycle_expense', expense.id)
    db.commit()
    return {'id': expense.id, 'plan_id': plan.id, **data.model_dump(), 'updated_forecast': forecast(plan, db)}


@app.get('/farms/{farm_id}/production-plans/{plan_id}/expenses', tags=['Production forecasting'])
def list_expenses(farm_id: int, plan_id: int, user: CurrentUser, db: Db):
    owned_plan(farm_id, plan_id, user, db)
    rows = db.scalars(select(CycleExpense).where(CycleExpense.plan_id == plan_id).order_by(CycleExpense.id)).all()
    return [{'id': e.id, 'category': e.category, 'amount_ghs': e.amount_ghs,
             'occurred_on': e.occurred_on, 'notes': e.notes} for e in rows]
