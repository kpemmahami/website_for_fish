"""Cycle-level cost and selling-price scenarios in Ghana cedis."""

from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape

from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .automated_costing import actual_feed_cost, cost_report
from .farm_expenses import FarmExpense
from .forecasting import ProductionPlan
from .main import CurrentUser, Db, ProductionUnit, app
from .operations import StockingCycle, owned_farm, population
from .sales import FishSale, HarvestLot

CENT = Decimal('0.01')
ROOT = '/farms/{farm_id}/cycles/{cycle_id}/pricing-advisor'


def decimal(value):
    return Decimal(str(value))


def rounded(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP)) if value is not None else None


class PricingIn(BaseModel):
    margin_pct: Decimal = Field(default=Decimal('25'), ge=0, lt=100, decimal_places=2)
    saleable_yield_pct: Decimal = Field(default=Decimal('100'), gt=0, le=100, decimal_places=2)
    selling_cost_per_kg: Decimal = Field(default=Decimal('0'), ge=0, max_digits=12, decimal_places=2)
    proposed_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_quantity_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)


def scenario(cost, weight, price, margin, realized=Decimal(0)):
    revenue = realized + weight * price
    profit = revenue - cost
    actual_margin = profit / revenue * 100 if revenue else None
    return {
        'price_ghs_per_kg': rounded(price), 'revenue_ghs': rounded(revenue),
        'cost_ghs': rounded(cost), 'profit_ghs': rounded(profit),
        'profit_per_kg_ghs': rounded(profit / weight) if weight else None,
        'margin_pct': rounded(actual_margin), 'return_on_cost_pct': rounded(profit / cost * 100) if cost else None,
        'status': 'below_break_even' if profit < 0 else 'meets_target'
        if actual_margin is not None and actual_margin >= margin else 'below_target',
    }


def calculate_advisor(db, farm_id, cycle, unit, data):
    current = population(cycle, db)
    plan = db.scalar(select(ProductionPlan).where(
        ProductionPlan.farm_id == farm_id, ProductionPlan.cycle_id == cycle.id,
    ).order_by(ProductionPlan.created_at.desc(), ProductionPlan.id.desc()).limit(1))
    report = cost_report(plan, db) if plan else None
    if report:
        incurred = decimal(report['actual_costs_to_date_ghs'])
        remaining = max(Decimal(0), decimal(report['projected_cycle_total_cost_ghs']) - incurred) if not cycle.closed_at else Decimal(0)
        feed = decimal(report['actual_feed_cost_to_date_ghs'])
        missing_prices = any('no priced receipts' in warning for warning in report['warnings'])
    else:
        feed_lines, missing_prices = actual_feed_cost(cycle.id, farm_id, db)
        feed = sum((decimal(line['indicative_consumed_feed_cost_ghs']) for line in feed_lines
                    if line['indicative_consumed_feed_cost_ghs'] is not None), Decimal(0))
        incurred, remaining = feed, Decimal(0)
    expense_costs = {}
    unallocated = 0
    for expense in db.scalars(select(FarmExpense).where(
        FarmExpense.farm_id == farm_id, FarmExpense.classification == 'operating',
    )):
        if expense.cycle_id == cycle.id:
            expense_costs[expense.category] = expense_costs.get(expense.category, 0) + expense.amount_pesewas
        elif expense.cycle_id is None and expense.unit_id in (None, unit.id):
            unallocated += expense.amount_pesewas
    allocated = sum(expense_costs.values()) / Decimal(100)
    incurred += allocated
    lots = db.scalars(select(HarvestLot).where(HarvestLot.farm_id == farm_id, HarvestLot.cycle_id == cycle.id)).all()
    harvested = sum((decimal(lot.quantity_kg) for lot in lots), Decimal(0))
    saleable_harvested = sum((max(Decimal(0), decimal(lot.quantity_kg) - decimal(lot.loss_kg)) for lot in lots), Decimal(0))
    sales = db.scalars(select(FishSale).where(FishSale.farm_id == farm_id, FishSale.harvest_lot_id.in_([lot.id for lot in lots]))).all()
    sold = sum((decimal(sale.quantity_kg) for sale in sales), Decimal(0))
    realized = sum(sale.total_pesewas for sale in sales) / Decimal(100)
    target = cycle.target_harvest_weight_g if cycle.target_harvest_weight_g is not None else plan.target_weight_g if plan else None
    live = max(0, current.estimated_live_count)
    if cycle.expected_survival_pct is not None:
        live = min(live, max(0, int(decimal(cycle.stocked_count) * decimal(cycle.expected_survival_pct) / 100) - current.total_harvested))
    forecast = Decimal(0) if cycle.closed_at else decimal(live) * decimal(target) / 1000 if target is not None else None
    weight = saleable_harvested + forecast * data.saleable_yield_pct / 100 if forecast is not None else None
    from .processing import ProcessingInput
    transfers = db.scalars(select(ProcessingInput).where(ProcessingInput.harvest_id.in_([lot.id for lot in lots]))).all()
    transferred = sum((decimal(row.quantity_kg) for row in transfers), Decimal(0))
    transferred_cost = sum(row.cost_pesewas or 0 for row in transfers)/Decimal(100)
    unsold = max(Decimal(0), saleable_harvested - sold - transferred)
    to_sell = unsold + forecast * data.saleable_yield_pct / 100 if forecast is not None else None
    # Selling assumptions apply only to kilograms still expected to be sold.
    estimated_selling_cost = to_sell * data.selling_cost_per_kg if to_sell is not None else None
    cost = incurred + remaining + (estimated_selling_cost or 0)
    warnings = []
    if not report and not cycle.closed_at:
        warnings.append('No production plan records remaining costs. Estimates exclude unrecorded costs.')
    if not current.latest_sampled_on:
        warnings.append('No fish sample is recorded. Current biomass uses the initial stocking weight.')
    if missing_prices:
        warnings.append('Some feed consumption has no priced receipt.')
    if report and report['warnings']:
        warnings.extend(warning for warning in report['warnings'] if 'no priced receipts' not in warning)
    if unallocated:
        warnings.append('Farm-wide and unit-wide expenses without an explicit cycle allocation are excluded.')
    if data.saleable_yield_pct == 100 and forecast:
        warnings.append('The forecast assumes 100% saleable yield. Enter a lower yield if grading or processing causes losses.')
    if any(row.cost_pesewas is None for row in transfers):
        warnings.append('A processing transfer has an unvalued production cost.')
    if not incurred and not remaining:
        warnings.append('No attributable production costs are available.')
    if weight is None or weight <= 0:
        warnings.append('Insufficient data for a reliable saleable harvest weight.')
    usable = weight is not None and weight > 0 and incurred + remaining > 0
    break_even = cost / weight if usable else None
    fresh_cost = max(Decimal(0),cost-transferred_cost)
    floor = max(Decimal(0), (fresh_cost - realized) / to_sell) if usable and to_sell else None
    target_price = (max(Decimal(0), (fresh_cost / (1 - data.margin_pct / 100) - realized) / to_sell)
                    .quantize(CENT, rounding=ROUND_CEILING)) if usable and to_sell else None
    allocated_harvest = (incurred + remaining) * saleable_harvested / weight if usable else None
    proposal = scenario(fresh_cost, to_sell, data.proposed_price, data.margin_pct, realized) if floor is not None and data.proposed_price is not None else None
    if proposal:
        proposal.update(difference_from_break_even=rounded(data.proposed_price - floor),
                        difference_from_target=rounded(data.proposed_price - target_price))
    batch = None
    if usable and data.proposed_price is not None and data.sale_quantity_kg and data.sale_quantity_kg <= unsold:
        batch_cost = data.sale_quantity_kg * ((incurred + remaining) / weight + data.selling_cost_per_kg)
        batch = scenario(batch_cost, data.sale_quantity_kg, data.proposed_price, data.margin_pct)
    return {
        'unit_name':unit.name, 'cycle_id':cycle.id, 'species':cycle.species, 'planned_harvest_on':cycle.expected_harvest_on,
        'sampled_on':current.latest_sampled_on, 'current_biomass_kg':max(0,current.estimated_biomass_kg),
        'incurred_ghs':rounded(incurred), 'remaining_cost_ghs':rounded(remaining) if report or cycle.closed_at else None,
        'expected_selling_cost_ghs':rounded(estimated_selling_cost), 'total_cost_ghs':rounded(cost) if incurred + remaining > 0 else None,
        'consumed_feed_cost_ghs':rounded(feed), 'allocated_expenses_ghs':{key:rounded(value / Decimal(100)) for key,value in expense_costs.items()},
        'unallocated_ghs':rounded(unallocated / Decimal(100)), 'cost_allocated_to_harvest_ghs':rounded(allocated_harvest),
        'forecast_harvest_kg':rounded(forecast), 'saleable_weight_kg':rounded(weight), 'harvested_kg':rounded(harvested),
        'sold_kg':rounded(sold), 'transferred_to_processing_kg':rounded(transferred), 'unsold_harvest_kg':rounded(unsold), 'realized_revenue_ghs':rounded(realized),
        'break_even_ghs_per_kg':rounded(break_even), 'remaining_break_even_ghs_per_kg':rounded(floor),
        'target_ghs_per_kg':rounded(target_price), 'margin_pct':rounded(data.margin_pct),
        'market_reference_ghs_per_kg':plan.market_price_ghs_per_kg if plan else None,
        'at_target':scenario(cost,to_sell,target_price,data.margin_pct,realized) if target_price is not None else None,
        'proposal':proposal, 'batch':batch, 'warnings':warnings,
        'confidence':'insufficient_data' if not usable else 'provisional' if warnings else 'complete',
    }


def scoped_cycle(farm_id, cycle_id, user, db):
    farm = owned_farm(farm_id, user, db)
    row = db.execute(select(StockingCycle,ProductionUnit).join(
        ProductionUnit, ProductionUnit.id==StockingCycle.unit_id,
    ).where(ProductionUnit.farm_id==farm_id, StockingCycle.id==cycle_id)).first()
    if row is None:
        raise HTTPException(404,'Stocking cycle not found')
    return farm, *row


@app.post(ROOT, tags=['Pricing advisor'])
def cycle_advisor(farm_id: int, cycle_id: int, data: PricingIn, user: CurrentUser, db: Db):
    _, cycle, unit = scoped_cycle(farm_id,cycle_id,user,db)
    return calculate_advisor(db,farm_id,cycle,unit,data)


@app.post(ROOT+'.pdf', tags=['Pricing advisor'])
def cycle_advisor_pdf(farm_id: int, cycle_id: int, data: PricingIn, user: CurrentUser, db: Db):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from .loan_appraisal_pdf import monetary

    farm, cycle, unit = scoped_cycle(farm_id,cycle_id,user,db)
    result = calculate_advisor(db,farm_id,cycle,unit,data)
    output = BytesIO()
    style = ParagraphStyle('pricing',fontName='Appraisal',fontSize=10,leading=15)
    heading = ParagraphStyle('pricing_heading',parent=style,fontName='Appraisal-Bold',fontSize=17,leading=21)
    story = [Paragraph('Production Cost &amp; Selling Price Report',heading), Spacer(1,12)]
    def line(text):
        story.append(Paragraph(escape(str(text)),style))
    line(f'{farm.name} | {unit.name} | {cycle.species} | Cycle #{cycle.id} | {date.today()}')
    line(f'Confidence: {result["confidence"].replace("_"," ")}')
    line(f'Saleable weight (kg): {result["saleable_weight_kg"] if result["saleable_weight_kg"] is not None else "Unavailable"}')
    line(f'Assumed saleable yield: {data.saleable_yield_pct}% | Target revenue margin: {data.margin_pct}%')
    for label,key in [('Incurred cost','incurred_ghs'),('Expected remaining cost','remaining_cost_ghs'),('Expected selling cost','expected_selling_cost_ghs'),
                      ('Feed consumed cost','consumed_feed_cost_ghs'),('Total expected cost','total_cost_ghs'),('Break-even per kg','break_even_ghs_per_kg'),
                      ('Suggested price per kg','target_ghs_per_kg'),('Invoiced sales to date','realized_revenue_ghs')]:
        line(f'{label}: {monetary(result[key])}')
    for category, amount in result['allocated_expenses_ghs'].items():
        line(f'{category}: {monetary(amount)}')
    for label in ('at_target','proposal','batch'):
        if result[label]:
            values = result[label]
            line(f'{label.replace("_"," ").title()}: revenue {monetary(values["revenue_ghs"])}, profit/loss {monetary(values["profit_ghs"])}, margin {values["margin_pct"]}%')
    for warning in result['warnings']:
        line(warning)
    SimpleDocTemplate(output,title='Production Cost and Selling Price Report').build(story)
    return Response(output.getvalue(),media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="production-pricing-{cycle.id}.pdf"',
        'Cache-Control':'private, no-store',
    })
