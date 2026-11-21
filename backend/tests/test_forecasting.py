import os
os.environ.setdefault('SECRET_KEY', 'test-only-key-not-for-production-123456789')
from app.forecasting import PlanIn, calculate
import pytest

def sample(**kwargs):
    d = dict(species='tilapia', fingerling_count=1000, initial_weight_g=20,
             target_weight_g=500, survival_pct=90, expected_fcr=1.5,
             feed_price_ghs_per_kg=20, fingerling_cost_ghs=1000,
             other_budget_ghs=500, desired_profit_pct=25)
    d.update(kwargs)
    return PlanIn(**d)

def test_basic_forecast():
    result = calculate(sample())
    assert result['expected_survivors'] == 900
    assert result['expected_harvest_kg'] == 450
    assert result['estimated_feed_kg'] == 645
    assert result['estimated_feed_bags'] == 26
    assert result['estimated_total_cost_ghs'] == 14400
    assert result['recommended_price_ghs_per_kg'] == 40

def test_margin_and_expenses():
    result = calculate(sample(profit_method='margin', desired_profit_pct=20), 3600)
    assert result['break_even_ghs_per_kg'] == 40
    assert result['recommended_price_ghs_per_kg'] == 50

def test_invalid_target():
    with pytest.raises(ValueError):
        sample(target_weight_g=10)

def test_invalid_margin():
    with pytest.raises(ValueError):
        sample(profit_method='margin', desired_profit_pct=100)

def test_zero_survival():
    result = calculate(sample(survival_pct=0))
    assert result['recommended_price_ghs_per_kg'] is None
