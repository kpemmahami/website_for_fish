from types import SimpleNamespace
from app.automated_costing import cost_report

def test_pricing_with_no_expenses(monkeypatch):
    class DB:
        def scalars(self, query):
            return SimpleNamespace(all=lambda: [])
    plan=SimpleNamespace(id=1,cycle_id=None,farm_id=1,fingerling_count=1000,
        survival_pct=90,target_weight_g=500,initial_weight_g=20,expected_fcr=1.5,
        bag_size_kg=25,feed_price_ghs_per_kg=10,fingerling_cost_ghs=500,
        other_budget_ghs=100,desired_profit_pct=25,profit_method='markup')
    result=cost_report(plan,DB())
    assert result['actual_costs_to_date_ghs']==0
    assert result['projected_cycle_total_cost_ghs']>0
    assert result['indicative_price_based_on_costs_to_date_ghs_per_kg']==0
    assert result['break_even_ghs_per_kg']>0
    assert result['recommended_price_ghs_per_kg']>result['break_even_ghs_per_kg']
    assert result['projected_revenue_ghs']>result['projected_cycle_total_cost_ghs']
    assert result['projected_profit_ghs']==round(
        result['projected_revenue_ghs']-result['projected_cycle_total_cost_ghs'],2)


def test_live_population_changes_harvest_and_price(monkeypatch):
    from app import operations
    from app.automated_costing import cost_report

    cycle=SimpleNamespace(closed_at=None)
    class DB:
        def scalars(self, query):
            return SimpleNamespace(all=lambda: [])
        def get(self, model, cycle_id):
            return cycle
    plan=SimpleNamespace(id=1,cycle_id=3,farm_id=1,fingerling_count=1000,
        survival_pct=90,target_weight_g=500,initial_weight_g=20,expected_fcr=1.5,
        bag_size_kg=25,feed_price_ghs_per_kg=2,fingerling_cost_ghs=100,
        other_budget_ghs=50,desired_profit_pct=20,profit_method='markup',
        market_price_ghs_per_kg=3.5)
    population=SimpleNamespace(estimated_live_count=900,estimated_biomass_kg=180,
        latest_average_weight_g=200)
    monkeypatch.setattr(operations,'population',lambda *_:population)
    first=cost_report(plan,DB())
    population.estimated_live_count=800
    population.estimated_biomass_kg=160
    second=cost_report(plan,DB())
    assert first['projected_harvest_kg']==450
    assert second['projected_harvest_kg']==400
    assert second['break_even_ghs_per_kg']>first['break_even_ghs_per_kg']
    assert second['market_projected_profit_ghs'] is not None
