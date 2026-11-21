"""Phase 0007: read-only, farm-scoped operational and financial analytics."""
from collections import defaultdict
from datetime import date, timedelta
from math import ceil
from fastapi import Query
from sqlalchemy import select
from .main import app, Db, CurrentUser, owned_farm, ProductionUnit
from .operations import StockingCycle, FishSample, WaterQuality, population
from .feeding import FeedProduct, FeedLedger, feed_forecast
from .forecasting import ProductionPlan
from .automated_costing import cost_report
from .sales import Customer, HarvestLot, FishSale, SalePayment, remaining_kg, ghs


def farm_data(farm_id, user, db):
    owned_farm(farm_id, user, db)
    units = db.scalars(select(ProductionUnit).where(ProductionUnit.farm_id == farm_id)).all()
    ids = [u.id for u in units]
    cycles = db.scalars(select(StockingCycle).where(StockingCycle.unit_id.in_(ids))).all() if ids else []
    feeds = db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id)).all()
    feed_ids = [f.id for f in feeds]
    ledger = db.scalars(select(FeedLedger).where(FeedLedger.feed_id.in_(feed_ids))).all() if feed_ids else []
    lots = db.scalars(select(HarvestLot).where(HarvestLot.farm_id == farm_id)).all()
    sales = db.scalars(select(FishSale).where(FishSale.farm_id == farm_id)).all()
    payments = db.scalars(select(SalePayment).where(SalePayment.farm_id == farm_id)).all()
    plans = db.scalars(select(ProductionPlan).where(ProductionPlan.farm_id == farm_id)).all()
    return units, cycles, feeds, ledger, lots, sales, payments, plans


def build_dashboard(farm_id, user, db):
    units, cycles, feeds, ledger, lots, sales, payments, plans = farm_data(farm_id, user, db)
    active = [c for c in cycles if c.closed_at is None]
    populations = [population(c, db) for c in active]
    feed_totals = defaultdict(float)
    for e in ledger: feed_totals[e.feed_id] += e.quantity_delta_kg
    revenue = sum(s.total_pesewas for s in sales)
    received = sum(p.amount_pesewas for p in payments)
    cost_reports = [cost_report(p, db) for p in plans]
    return {
        'farm_id': farm_id, 'currency': 'GHS',
        'production': {'total_units': len(units), 'active_units': sum(u.is_active for u in units),
                       'total_cycles': len(cycles), 'active_cycles': len(active),
                       'stocked_fish_in_active_cycles': sum(c.stocked_count for c in active),
                       'estimated_live_fish': sum(p.estimated_live_count for p in populations),
                       'estimated_live_biomass_kg': round(sum(p.estimated_biomass_kg for p in populations), 4),
                       'note': 'Estimated biomass is sample-based and excludes harvested-fish adjustments; do not treat as verified live inventory.'},
        'feed': {'products': len(feeds), 'remaining_stock_kg': round(sum(feed_totals.values()), 4),
                 'consumed_kg': round(-sum(e.quantity_delta_kg for e in ledger if e.event_type == 'feeding'), 4),
                 'by_product': [{'feed_id': f.id, 'name': f.name, 'stock_kg': round(feed_totals[f.id], 4)} for f in feeds]},
        'sales': {'customers': db.query(Customer).filter(Customer.farm_id == farm_id).count(),
                  'harvested_kg': round(sum(l.quantity_kg for l in lots), 4),
                  'available_harvest_kg': round(sum(remaining_kg(db, l) for l in lots), 4),
                  'sold_kg': round(sum(s.quantity_kg for s in sales), 4),
                  'sales_count': len(sales), 'invoiced_revenue_ghs': ghs(revenue),
                  'payments_received_ghs': ghs(received), 'outstanding_receivables_ghs': ghs(revenue-received)},
        'costs': {'production_plan_count': len(plans),
                  'projected_cycle_costs_ghs': round(sum(r['projected_cycle_total_cost_ghs'] for r in cost_reports), 2),
                  'recorded_costs_to_date_ghs': round(sum(r['actual_costs_to_date_ghs'] for r in cost_reports), 2),
                  'note': 'Totals sum plan-level costs; overlapping plans for one cycle can double count. Not a net-profit calculation.'},
        'warnings': ['Sales revenue is not cash received or net profit.',
                     'Feed purchases are stock acquisitions; feeding consumption is valued separately.',
                     'Dashboard totals include historical sales and costs; no period filter is applied.']
    }


@app.get('/farms/{farm_id}/dashboard', tags=['Dashboard and reporting'])
def dashboard(farm_id: int, user: CurrentUser, db: Db):
    return build_dashboard(farm_id, user, db)


@app.get('/farms/{farm_id}/dashboard/cycles', tags=['Dashboard and reporting'])
def cycle_dashboard(farm_id: int, user: CurrentUser, db: Db):
    units, cycles, *_ = farm_data(farm_id, user, db)
    by_unit = {u.id: u for u in units}
    rows = []
    for c in cycles:
        p = population(c, db)
        rows.append({'cycle_id': c.id, 'unit_id': c.unit_id, 'unit_name': by_unit[c.unit_id].name,
                     'species': c.species, 'status': 'closed' if c.closed_at else 'active',
                     'stocked_on': c.stocked_on, 'stocked_count': p.stocked_count,
                     'mortality_count': p.total_mortality,
                     'mortality_pct': round(100*p.total_mortality/c.stocked_count, 2) if c.stocked_count else None,
                     'estimated_live_count': p.estimated_live_count,
                     'latest_average_weight_g': p.latest_average_weight_g,
                     'estimated_biomass_kg': p.estimated_biomass_kg,
                     'latest_sampled_on': p.latest_sampled_on})
    return {'farm_id': farm_id, 'cycles': rows, 'note': 'Historical estimates do not subtract harvested fish.'}


@app.get('/farms/{farm_id}/dashboard/monthly', tags=['Dashboard and reporting'])
def monthly_dashboard(farm_id: int, user: CurrentUser, db: Db, year: int = Query(ge=2000, le=2200)):
    _, _, _, ledger, _, sales, payments, plans = farm_data(farm_id, user, db)
    months = {m: {'month': f'{year}-{m:02d}', 'invoiced_revenue_ghs': 0.0,
                  'payments_received_ghs': 0.0, 'fish_sold_kg': 0.0,
                  'feed_purchased_kg': 0.0, 'feed_consumed_kg': 0.0,
                  'feed_purchase_cash_outflow_ghs': 0.0,
                  'manual_expenses_ghs': 0.0, 'shared_allocations_ghs': 0.0} for m in range(1,13)}
    for s in sales:
        if s.sold_on.year == year:
            x=months[s.sold_on.month]; x['invoiced_revenue_ghs']+=ghs(s.total_pesewas); x['fish_sold_kg']+=s.quantity_kg
    for p in payments:
        if p.paid_on.year == year: months[p.paid_on.month]['payments_received_ghs']+=ghs(p.amount_pesewas)
    for e in ledger:
        if e.occurred_on.year != year: continue
        x=months[e.occurred_on.month]
        if e.event_type == 'receipt':
            x['feed_purchased_kg']+=e.quantity_delta_kg
            x['feed_purchase_cash_outflow_ghs']+=e.cost_ghs or 0
        elif e.event_type == 'feeding': x['feed_consumed_kg']+=-e.quantity_delta_kg
    from .forecasting import CycleExpense
    from .automated_costing import SharedCostAllocation
    plan_ids = [p.id for p in plans]
    if plan_ids:
        for e in db.scalars(select(CycleExpense).where(CycleExpense.plan_id.in_(plan_ids))).all():
            if e.occurred_on.year == year: months[e.occurred_on.month]['manual_expenses_ghs']+=e.amount_ghs
        for e in db.scalars(select(SharedCostAllocation).where(SharedCostAllocation.plan_id.in_(plan_ids))).all():
            if e.occurred_on.year == year: months[e.occurred_on.month]['shared_allocations_ghs']+=e.amount_ghs
    return {'farm_id': farm_id, 'year': year, 'currency': 'GHS',
            'months': [{k: round(v, 2) if isinstance(v, float) else v for k,v in row.items()} for row in months.values()],
            'warnings': ['Feed purchases are cash outflows, not feed-consumption expenses.',
                         'Manual expenses can include feed purchases; do not add columns to derive net profit.',
                         'Overlapping plans can duplicate recorded expenses.']}


def build_analytics(farm_id: int, user, db):
    farm = owned_farm(farm_id, user, db)
    dashboard_data = build_dashboard(farm_id, user, db)
    units, cycles, feeds, ledger, _, _, _, plans = farm_data(farm_id, user, db)
    unit_by_id = {unit.id: unit for unit in units}
    cycles_by_id = {cycle.id: cycle for cycle in cycles}
    cycle_rows = cycle_dashboard(farm_id, user, db)['cycles']
    cycle_ids = list(cycles_by_id)
    samples = db.scalars(
        select(FishSample).where(FishSample.cycle_id.in_(cycle_ids))
        .order_by(FishSample.sampled_on, FishSample.id)
    ).all() if cycle_ids else []
    samples_by_cycle = defaultdict(list)
    growth_trends = []
    for sample in samples:
        cycle = cycles_by_id[sample.cycle_id]
        unit = unit_by_id[cycle.unit_id]
        samples_by_cycle[sample.cycle_id].append(sample)
        growth_trends.append({
            'cycle_id': cycle.id,
            'unit_id': unit.id,
            'unit_name': unit.name,
            'species': cycle.species,
            'sampled_on': sample.sampled_on,
            'average_weight_g': sample.average_weight_g,
            'sample_count': sample.sample_count,
        })

    feed_by_cycle = defaultdict(float)
    for entry in ledger:
        if entry.event_type == 'feeding' and entry.cycle_id is not None:
            feed_by_cycle[entry.cycle_id] += -entry.quantity_delta_kg

    plans_by_cycle = defaultdict(list)
    for plan in plans:
        if plan.cycle_id is not None:
            plans_by_cycle[plan.cycle_id].append(plan)

    harvest_forecasts = []
    pricing_rows = []
    pricing_by_plan = {plan.id: cost_report(plan, db) for plan in plans}
    today = date.today()
    for cycle in cycles:
        if cycle.closed_at is not None:
            continue
        matching_plans = plans_by_cycle.get(cycle.id, [])
        if not matching_plans:
            harvest_forecasts.append({
                'cycle_id': cycle.id,
                'unit_name': unit_by_id[cycle.unit_id].name,
                'species': cycle.species,
                'expected_harvest_kg': None,
                'expected_harvest_on': None,
                'date_basis': 'unavailable',
                'note': 'No production plan is linked to this active cycle.',
            })
            continue

        plan = max(matching_plans, key=lambda item: (item.created_at, item.id))
        pricing = pricing_by_plan[plan.id]
        history = samples_by_cycle.get(cycle.id, [])
        expected_date = None
        date_basis = 'insufficient_growth_samples'
        if history and history[-1].average_weight_g >= plan.target_weight_g:
            expected_date = today
            date_basis = 'target_weight_reached'
        elif len(history) >= 2:
            previous, latest = history[-2], history[-1]
            elapsed_days = (latest.sampled_on - previous.sampled_on).days
            growth_per_day = (
                (latest.average_weight_g - previous.average_weight_g) / elapsed_days
                if elapsed_days > 0 else 0
            )
            if growth_per_day > 0 and latest.average_weight_g < plan.target_weight_g:
                days_to_target = ceil((plan.target_weight_g - latest.average_weight_g) / growth_per_day)
                expected_date = latest.sampled_on + timedelta(days=days_to_target)
                date_basis = 'linear_projection_from_last_two_samples'

        row = {
            'plan_id': plan.id,
            'cycle_id': cycle.id,
            'unit_name': unit_by_id[cycle.unit_id].name,
            'species': cycle.species,
            'expected_harvest_kg': pricing['projected_harvest_kg'],
            'expected_harvest_on': expected_date,
            'date_basis': date_basis,
            'latest_average_weight_g': history[-1].average_weight_g if history else cycle.initial_average_weight_g,
            'target_weight_g': plan.target_weight_g,
            'note': 'Planning forecast; harvest weight and date are estimates, not verified commitments.',
        }
        harvest_forecasts.append(row)
    for plan in plans:
        pricing = pricing_by_plan[plan.id]
        pricing_rows.append({
            'plan_id': plan.id,
            'cycle_id': plan.cycle_id,
            'species': plan.species,
            'desired_profit_pct': pricing['desired_profit_pct'],
            'profit_method': pricing['profit_method'],
            'projected_harvest_kg': pricing['projected_harvest_kg'],
            'projected_cycle_total_cost_ghs': pricing['projected_cycle_total_cost_ghs'],
            'actual_costs_to_date_ghs': pricing['actual_costs_to_date_ghs'],
            'indicative_actual_cost_per_forecast_kg_ghs': pricing['indicative_actual_cost_per_forecast_kg_ghs'],
            'break_even_ghs_per_kg': pricing['break_even_ghs_per_kg'],
            'desired_profit_pct': pricing['desired_profit_pct'],
            'profit_method': pricing['profit_method'],
            'market_price_ghs_per_kg': pricing['market_price_ghs_per_kg'],
            'market_price_difference_ghs_per_kg': pricing['market_price_difference_ghs_per_kg'],
            'recommended_price_ghs_per_kg': pricing['recommended_price_ghs_per_kg'],
            'projected_revenue_ghs': pricing['projected_revenue_ghs'],
            'projected_profit_ghs': pricing['projected_profit_ghs'],
            'market_projected_revenue_ghs': pricing['market_projected_revenue_ghs'],
            'market_projected_profit_ghs': pricing['market_projected_profit_ghs'],
            'warnings': pricing['warnings'],
        })

    active_cycle_rows = [row for row in cycle_rows if row['status'] == 'active']
    unit_comparisons = []
    for unit in units:
        unit_cycle_rows = [row for row in cycle_rows if row['unit_id'] == unit.id]
        active_unit_cycles = [row for row in unit_cycle_rows if row['status'] == 'active']
        positive_gain_cycles = []
        for row in unit_cycle_rows:
            cycle = cycles_by_id[row['cycle_id']]
            initial_biomass = cycle.stocked_count * cycle.initial_average_weight_g / 1000
            gain = row['estimated_biomass_kg'] - initial_biomass
            if gain > 0:
                positive_gain_cycles.append((row['cycle_id'], gain))
        feed_for_positive_gain = sum(feed_by_cycle[cycle_id] for cycle_id, _ in positive_gain_cycles)
        biomass_gain = sum(gain for _, gain in positive_gain_cycles)
        stocked = sum(row['stocked_count'] for row in unit_cycle_rows)
        mortality = sum(row['mortality_count'] for row in unit_cycle_rows)
        unit_comparisons.append({
            'unit_id': unit.id,
            'unit_name': unit.name,
            'unit_type': unit.unit_type,
            'active_cycles': len(active_unit_cycles),
            'stocked_fish': stocked,
            'estimated_live_fish': sum(row['estimated_live_count'] for row in active_unit_cycles),
            'estimated_biomass_kg': round(sum(row['estimated_biomass_kg'] for row in active_unit_cycles), 4),
            'mortality_count': mortality,
            'mortality_pct': round(100 * mortality / stocked, 2) if stocked else None,
            'feed_consumed_kg': round(sum(feed_by_cycle[row['cycle_id']] for row in unit_cycle_rows), 4),
            'indicative_fcr': round(feed_for_positive_gain / biomass_gain, 4) if biomass_gain else None,
        })

    unit_ids = list(unit_by_id)
    water_records = db.scalars(
        select(WaterQuality).where(WaterQuality.unit_id.in_(unit_ids))
        .order_by(WaterQuality.observed_at.desc(), WaterQuality.id.desc())
        .limit(200)
    ).all() if unit_ids else []
    latest_water = {}
    water_history = []
    for record in water_records[:200]:
        unit = unit_by_id[record.unit_id]
        row = {
            'unit_id': unit.id,
            'unit_name': unit.name,
            'unit_type': unit.unit_type,
            'observed_at': record.observed_at,
            'temperature_c': record.temperature_c,
            'dissolved_oxygen_mg_l': record.dissolved_oxygen_mg_l,
            'ph': record.ph,
            'ammonia_mg_l': record.ammonia_mg_l,
            'nitrite_mg_l': record.nitrite_mg_l,
        }
        latest_water.setdefault(unit.id, row)
        water_history.append(row)
    water_history.reverse()

    feed_inventory = []
    for feed in feeds:
        entries = [entry for entry in ledger if entry.feed_id == feed.id]
        receipts = [entry for entry in entries if entry.event_type == 'receipt' and entry.quantity_delta_kg > 0]
        priced_receipts = [entry for entry in receipts if entry.cost_ghs is not None]
        purchased_kg = sum(entry.quantity_delta_kg for entry in receipts)
        purchased_cost = sum(entry.cost_ghs or 0 for entry in receipts)
        priced_kg = sum(entry.quantity_delta_kg for entry in priced_receipts)
        priced_cost = sum(entry.cost_ghs or 0 for entry in priced_receipts)
        consumed_kg = -sum(entry.quantity_delta_kg for entry in entries if entry.event_type == 'feeding')
        feed_inventory.append({
            'feed_id': feed.id,
            'feed_name': feed.name,
            'supplier': feed.supplier,
            'purchased_kg': round(purchased_kg, 4),
            'consumed_kg': round(consumed_kg, 4),
            'remaining_stock_kg': round(sum(entry.quantity_delta_kg for entry in entries), 4),
            'purchase_cost_ghs': round(purchased_cost, 2),
            'estimated_consumed_cost_ghs': round(consumed_kg * priced_cost / priced_kg, 2) if priced_kg else None,
        })

    monthly = monthly_dashboard(farm_id, user, db, today.year)['months']
    active_growth = sum(
        (row['estimated_biomass_kg'] for row in active_cycle_rows), 0
    )
    available_harvest_forecasts = [
        row['expected_harvest_kg']
        for row in harvest_forecasts
        if row['expected_harvest_kg'] is not None
    ]
    expected_harvest = (
        round(sum(available_harvest_forecasts), 2)
        if available_harvest_forecasts else None
    )
    return {
        'farm': {
            'farm_id': farm.id,
            'name': farm.name,
            'owner_name': user.full_name,
            'region': farm.region,
            'district': farm.district,
            'farm_type': farm.farm_type,
            'species': farm.species,
        },
        'generated_on': today,
        'summary': {
            'total_units': dashboard_data['production']['total_units'],
            'active_units': dashboard_data['production']['active_units'],
            'active_cycles': dashboard_data['production']['active_cycles'],
            'stocked_fish': dashboard_data['production']['stocked_fish_in_active_cycles'],
            'estimated_live_fish': dashboard_data['production']['estimated_live_fish'],
            'mortality_count': sum(row['mortality_count'] for row in active_cycle_rows),
            'estimated_biomass_kg': round(active_growth, 4),
            'expected_harvest_kg': expected_harvest,
            'upcoming_harvest_count': sum(
                row['expected_harvest_on'] is not None and row['expected_harvest_on'] >= today
                for row in harvest_forecasts
            ),
            'remaining_feed_kg': dashboard_data['feed']['remaining_stock_kg'],
            'payments_received_ghs': dashboard_data['sales']['payments_received_ghs'],
            'outstanding_customer_credit_ghs': dashboard_data['sales']['outstanding_receivables_ghs'],
        },
        'production': {
            'cycles': cycle_rows,
            'growth_trends': growth_trends,
            'unit_comparisons': unit_comparisons,
            'harvest_forecasts': harvest_forecasts,
            'upcoming_harvests': [
                row for row in harvest_forecasts
                if row['expected_harvest_on'] is not None and row['expected_harvest_on'] >= today
            ],
        },
        'water_quality': {
            'latest_by_unit': list(latest_water.values()),
            'history': water_history,
        },
        'feed': {
            'inventory': feed_inventory,
            'forecast': feed_forecast(farm_id, user, db, 30),
        },
        'finance': {
            'sales': dashboard_data['sales'],
            'costs': dashboard_data['costs'],
            'pricing_by_plan': pricing_rows,
            'monthly_cashflow': monthly,
        },
        'warnings': [
            'Survival, biomass, FCR, harvest, and financial metrics are record-derived estimates, not independently verified results.',
            'Harvest dates use a linear projection from the two latest samples and are unavailable without sufficient positive growth data.',
            'Feed cost uses weighted-average priced receipts; it is not FIFO. Overlapping production plans can duplicate projected costs.',
            'Invoiced sales are not cash received, and operating cash flow is not net profit.',
        ],
    }


@app.get('/farms/{farm_id}/dashboard/analytics', tags=['Dashboard and reporting'])
def dashboard_analytics(farm_id: int, user: CurrentUser, db: Db):
    return build_analytics(farm_id, user, db)
