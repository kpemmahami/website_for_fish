"""Phase 0005: cycle-level actual costing, without counting feed purchases as consumption.

Feed valuation uses historical weighted-average receipt price (indicative, not FIFO).
Unallocated shared farm expenses are excluded until explicitly allocated to a plan.
"""
from datetime import date, datetime, timezone
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, audit
from .forecasting import ProductionPlan, CycleExpense, owned_plan, calculate
from .feeding import FeedLedger, FeedProduct

class SharedCostAllocation(Base):
    __tablename__ = 'shared_cost_allocations'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('production_plans.id'), index=True)
    category: Mapped[str] = mapped_column(String(40))
    amount_ghs: Mapped[float] = mapped_column(Float)
    occurred_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AllocationIn(BaseModel):
    category: Literal['labour', 'electricity', 'water', 'fuel', 'maintenance', 'equipment', 'administration', 'other']
    amount_ghs: float = Field(gt=0)
    occurred_on: date
    description: str | None = Field(default=None, max_length=2000)

class PricingIn(BaseModel):
    desired_profit_pct: float = Field(ge=0, le=500)
    profit_method: Literal['markup','margin'] = 'markup'
    market_price_ghs_per_kg: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def validate_margin(self):
        if self.profit_method == 'margin' and self.desired_profit_pct >= 100:
            raise ValueError('Profit margin must be below 100%')
        return self


def actual_feed_cost(cycle_id, farm_id, db):
    """Valuation based on receipts for each feed product used by this cycle."""
    entries = db.scalars(select(FeedLedger).where(FeedLedger.cycle_id == cycle_id,
                        FeedLedger.event_type == 'feeding')).all()
    lines, missing = [], False
    for feed_id in sorted({e.feed_id for e in entries}):
        feed = db.get(FeedProduct, feed_id)
        if feed is None or feed.farm_id != farm_id:
            raise HTTPException(409, 'Feed ledger has an invalid farm association')
        receipts = db.scalars(select(FeedLedger).where(FeedLedger.feed_id == feed_id,
                            FeedLedger.event_type == 'receipt')).all()
        priced = [r for r in receipts if r.cost_ghs is not None and r.quantity_delta_kg > 0]
        purchased_kg = sum(r.quantity_delta_kg for r in priced)
        consumed_kg = sum(-e.quantity_delta_kg for e in entries if e.feed_id == feed_id)
        unit_cost = sum(r.cost_ghs for r in priced)/purchased_kg if purchased_kg else None
        if unit_cost is None: missing = True
        lines.append({'feed_id':feed_id,'consumed_kg':round(consumed_kg,4),
                      'average_purchase_price_ghs_per_kg':round(unit_cost,4) if unit_cost is not None else None,
                      'indicative_consumed_feed_cost_ghs':round(consumed_kg*unit_cost,2) if unit_cost is not None else None})
    return lines, missing


def cost_report(plan, db, desired_profit_pct=None, profit_method=None):
    expenses = db.scalars(select(CycleExpense).where(CycleExpense.plan_id == plan.id)).all()
    allocations = db.scalars(select(SharedCostAllocation).where(SharedCostAllocation.plan_id == plan.id)).all()
    manual_by_category = {}
    for e in expenses:
        manual_by_category[e.category] = manual_by_category.get(e.category,0)+e.amount_ghs
    allocated = sum(a.amount_ghs for a in allocations)
    feed_lines, missing_feed_price = (actual_feed_cost(plan.cycle_id,plan.farm_id,db)
                                      if plan.cycle_id is not None else ([],False))
    consumed_feed_cost = sum(x['indicative_consumed_feed_cost_ghs'] or 0 for x in feed_lines)
    # Feed receipts represent stock purchases, not cycle costs. Cycle cost is feed actually fed.
    # If feeding entries exist, manual feed expenses must not also be added to cost.
    feed_mode = 'consumption' if feed_lines else ('manual' if manual_by_category.get('feed') else 'not_recorded')
    manual_feed = manual_by_category.get('feed',0)
    manual_other = sum(v for k,v in manual_by_category.items() if k != 'feed')
    actual_feed = consumed_feed_cost if feed_lines else manual_feed
    actual_total = actual_feed + manual_other + allocated
    base = calculate(plan)
    harvest = base['expected_harvest_kg']
    current_biomass_kg = None
    remaining_feed_kg = base['estimated_feed_kg']
    consumed_feed_kg = sum(line['consumed_kg'] for line in feed_lines)
    if plan.cycle_id is not None:
        from .operations import StockingCycle, population
        cycle = db.get(StockingCycle, plan.cycle_id)
        if cycle is not None and cycle.closed_at is None:
            current = population(cycle, db)
            current_biomass_kg = current.estimated_biomass_kg
            harvest_weight_g = max(current.latest_average_weight_g, plan.target_weight_g)
            harvest = round(current.estimated_live_count * harvest_weight_g / 1000, 2)
            remaining_feed_kg = max(0, (harvest - current_biomass_kg) * plan.expected_fcr)

    # Historical actual spending and projected total cycle cost are different metrics.
    # Value consumed feed from priced receipts; use the plan's rate for unpriced
    # consumption and the remaining feed requirement.
    priced_consumed_kg = sum(
        line['consumed_kg'] for line in feed_lines
        if line['average_purchase_price_ghs_per_kg'] is not None
    )
    priced_consumed_cost = sum(
        line['indicative_consumed_feed_cost_ghs'] or 0 for line in feed_lines
    )
    consumed_rate = (
        priced_consumed_cost / priced_consumed_kg
        if priced_consumed_kg > 0 else plan.feed_price_ghs_per_kg
    )
    projected_consumed_feed_cost = priced_consumed_cost + max(
        0, consumed_feed_kg - priced_consumed_kg
    ) * plan.feed_price_ghs_per_kg
    projected_feed_cost = (
        projected_consumed_feed_cost + remaining_feed_kg * consumed_rate
        if feed_lines else manual_feed + remaining_feed_kg * plan.feed_price_ghs_per_kg
    )
    projected_nonfeed_cost = (
        plan.fingerling_cost_ghs + plan.other_budget_ghs + manual_other + allocated
    )
    projected_total = projected_nonfeed_cost + projected_feed_cost
    unit = projected_total / harvest if harvest and projected_total >= 0 else None
    actual_unit = actual_total / harvest if harvest and not missing_feed_price else None
    pct = plan.desired_profit_pct if desired_profit_pct is None else desired_profit_pct
    method = plan.profit_method if profit_method is None else profit_method
    if method == 'margin' and pct >= 100:
        raise HTTPException(422, 'Profit margin must be below 100%')
    price = (unit*(1+pct/100) if method=='markup' else unit/(1-pct/100)) if unit is not None else None
    market_price = getattr(plan, 'market_price_ghs_per_kg', None)
    break_even = unit
    projected_revenue = price * harvest if price is not None and harvest is not None else None
    projected_profit = projected_revenue - projected_total if projected_revenue is not None else None
    actual_price = (
        actual_unit * (1 + pct / 100) if method == 'markup'
        else actual_unit / (1 - pct / 100)
    ) if actual_unit is not None else None
    market_revenue = market_price * harvest if market_price is not None and harvest is not None else None
    market_profit = market_revenue - projected_total if market_revenue is not None else None
    warnings = ['Actual-to-date costs are not the final cost of a production cycle.',
                'Projected cost/kg uses record-derived harvest estimates and planned future costs.',
                'Feed consumption is valued using historical weighted-average purchase prices, not FIFO.',
                'Record all other relevant expenses and allocate shared costs to avoid underpricing.']
    if plan.cycle_id is None: warnings.append('Plan is not linked to a stocking cycle; automatic feed consumption unavailable.')
    if missing_feed_price: warnings.append('Some consumed feed has no priced receipts; the plan feed price is used for those quantities.')
    if feed_lines and manual_feed: warnings.append('Manual feed expense excluded to avoid double counting with feeding ledger.')
    if not feed_lines and not manual_feed: warnings.append('No actual feed consumption cost recorded yet.')
    if plan.cycle_id is not None and current_biomass_kg is not None:
        warnings.append('Harvest forecast uses estimated live fish and the latest recorded sample; it is not a verified harvest.')
    if market_price is not None:
        warnings.append('Market price is farmer-entered and has not been independently verified.')
    r=lambda x:round(x,2) if x is not None else None
    return {'plan_id':plan.id,'cycle_id':plan.cycle_id,'currency':'GHS',
            'projected_cycle_total_cost_ghs':r(projected_total),
            'projected_harvest_kg':harvest,
            'actual_costs_to_date_ghs':r(actual_total),
            'actual_feed_cost_to_date_ghs':r(actual_feed),
            'manual_nonfeed_expenses_ghs':r(manual_other),
            'shared_cost_allocations_ghs':r(allocated),
            'manual_feed_expenses_excluded_ghs':r(manual_feed) if feed_lines else 0,
            'feed_valuation_method':feed_mode,
            'feed_cost_lines':feed_lines,
            'indicative_actual_cost_per_forecast_kg_ghs':r(actual_unit),
            'break_even_ghs_per_kg':r(break_even),
            'desired_profit_pct':pct,'profit_method':method,
            'indicative_price_based_on_costs_to_date_ghs_per_kg':r(actual_price),
            'recommended_price_ghs_per_kg':r(price),
            'projected_revenue_ghs':r(projected_revenue),
            'projected_profit_ghs':r(projected_profit),
            'market_price_ghs_per_kg':r(market_price),
            'market_price_difference_ghs_per_kg':r(price-market_price if price is not None and market_price is not None else None),
            'market_projected_revenue_ghs':r(market_revenue),
            'market_projected_profit_ghs':r(market_profit),
            'warnings':warnings}

@app.get('/farms/{farm_id}/production-plans/{plan_id}/automated-costing',tags=['Automated costing'])
def get_automated_costing(farm_id:int,plan_id:int,user:CurrentUser,db:Db):
    return cost_report(owned_plan(farm_id,plan_id,user,db),db)

@app.post('/farms/{farm_id}/production-plans/{plan_id}/pricing-scenario',tags=['Automated costing'])
def pricing_scenario(farm_id:int,plan_id:int,data:PricingIn,user:CurrentUser,db:Db):
    plan = owned_plan(farm_id,plan_id,user,db)
    result = cost_report(plan,db,data.desired_profit_pct,data.profit_method)
    market_price = data.market_price_ghs_per_kg
    result['market_price_ghs_per_kg'] = market_price
    result['market_price_difference_ghs_per_kg'] = round(
        result['recommended_price_ghs_per_kg'] - market_price, 2
    ) if result['recommended_price_ghs_per_kg'] is not None and market_price is not None else None
    result['market_projected_revenue_ghs'] = round(
        market_price * result['projected_harvest_kg'], 2
    ) if market_price is not None and result['projected_harvest_kg'] is not None else None
    result['market_projected_profit_ghs'] = round(
        result['market_projected_revenue_ghs'] - result['projected_cycle_total_cost_ghs'], 2
    ) if result['market_projected_revenue_ghs'] is not None else None
    return result


@app.patch('/farms/{farm_id}/production-plans/{plan_id}/pricing', tags=['Automated costing'])
def update_pricing(farm_id:int,plan_id:int,data:PricingIn,user:CurrentUser,db:Db):
    plan = owned_plan(farm_id,plan_id,user,db)
    plan.desired_profit_pct = data.desired_profit_pct
    plan.profit_method = data.profit_method
    plan.market_price_ghs_per_kg = data.market_price_ghs_per_kg
    audit(db,user,'update','production_plan_pricing',plan.id)
    db.commit()
    db.refresh(plan)
    return cost_report(plan,db)

@app.post('/farms/{farm_id}/production-plans/{plan_id}/shared-cost-allocations',status_code=201,tags=['Automated costing'])
def add_allocation(farm_id:int,plan_id:int,data:AllocationIn,user:CurrentUser,db:Db):
    plan=owned_plan(farm_id,plan_id,user,db)
    if data.occurred_on > date.today(): raise HTTPException(422,'Allocation date cannot be in the future')
    a=SharedCostAllocation(plan_id=plan.id,**data.model_dump())
    db.add(a);db.flush();audit(db,user,'create','shared_cost_allocation',a.id)
    db.commit();db.refresh(a)
    return {'id':a.id,'plan_id':plan.id,**data.model_dump(mode='json')}

@app.get('/farms/{farm_id}/production-plans/{plan_id}/shared-cost-allocations',tags=['Automated costing'])
def list_allocations(farm_id:int,plan_id:int,user:CurrentUser,db:Db):
    owned_plan(farm_id,plan_id,user,db)
    rows=db.scalars(select(SharedCostAllocation).where(SharedCostAllocation.plan_id==plan_id).order_by(SharedCostAllocation.id)).all()
    return [{'id':a.id,'plan_id':a.plan_id,'category':a.category,'amount_ghs':a.amount_ghs,
             'occurred_on':a.occurred_on,'description':a.description} for a in rows]
