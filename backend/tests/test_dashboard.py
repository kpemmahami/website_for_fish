import os
import json
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from openpyxl import load_workbook
os.environ.setdefault('SECRET_KEY', 'test-only-key-not-for-production-123456789')
from .test_api import client
from .test_foundation import signup
from app.feeding import FeedLedger, FeedProduct
from app.forecasting import CycleExpense, ProductionPlan
from app.main import ProductionUnit, SessionLocal
from app.operations import FishSample, Mortality, StockingCycle, WaterQuality


def test_dashboard_empty_farm_and_csv_and_access():
    a=signup('dashboard-owner@example.com')
    b=signup('dashboard-other@example.com')
    data={'name':'Dashboard Farm','region':'Northern','district':'Tamale','farm_type':'pond','species':'Tilapia'}
    response=client.post('/farms', json=data, headers=a)
    assert response.status_code == 201, response.text
    fid=response.json()['id']
    root=f'/farms/{fid}'
    assert client.get(root+'/dashboard',headers=b).status_code == 404
    result=client.get(root+'/dashboard',headers=a)
    assert result.status_code == 200, result.text
    assert result.json()['sales']['invoiced_revenue_ghs']==0
    assert result.json()['production']['active_cycles']==0
    monthly=client.get(root+'/dashboard/monthly?year=2026',headers=a)
    assert monthly.status_code==200 and len(monthly.json()['months'])==12
    assert client.get(root+'/dashboard/monthly?year=1999',headers=a).status_code==422
    for endpoint in ('cycles.csv','summary.csv','monthly.csv?year=2026'):
        result=client.get(root+'/reports/'+endpoint,headers=a)
        assert result.status_code==200 and 'text/csv' in result.headers['content-type']
        assert client.get(root+'/reports/'+endpoint,headers=b).status_code==404
    analytics=client.get(root+'/dashboard/analytics',headers=a)
    assert analytics.status_code==200,analytics.text
    assert analytics.json()['summary']['active_units']==0
    excel=client.get(root+'/reports/bank-ready.xlsx',headers=a)
    assert excel.status_code==200,excel.text
    workbook=load_workbook(BytesIO(excel.content),read_only=True)
    assert 'Summary' in workbook.sheetnames
    assert 'Feed Inventory' in workbook.sheetnames
    assert client.get(root+'/reports/bank-ready.xlsx',headers=b).status_code==404
    for kind in ('production','sales','inventory','financial'):
        report=client.get(f'{root}/reports/analytics/{kind}.csv',headers=a)
        assert report.status_code==200,report.text
        assert 'text/csv' in report.headers['content-type']
        assert client.get(f'{root}/reports/analytics/{kind}.csv',headers=b).status_code==404


def test_analytics_growth_harvest_feed_water_and_financial_forecasts():
    farmer=signup('dashboard-analytics-owner@example.com')
    farm=client.post('/farms',json={
        'name':'Analytics Farm','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Tilapia',
    },headers=farmer)
    assert farm.status_code==201,farm.text
    farm_id=farm.json()['id']
    today=date.today()
    with SessionLocal() as db:
        unit=ProductionUnit(farm_id=farm_id,name='North Pond',unit_type='pond')
        db.add(unit);db.flush()
        cycle=StockingCycle(unit_id=unit.id,species='Tilapia',stocked_count=1000,
            initial_average_weight_g=10,stocked_on=today-timedelta(days=30))
        db.add(cycle);db.flush()
        cycle_id=cycle.id
        db.add_all([
            FishSample(cycle_id=cycle.id,sampled_on=today-timedelta(days=20),
                weights_g_json=json.dumps([100,100]),sample_count=2,average_weight_g=100),
            FishSample(cycle_id=cycle.id,sampled_on=today-timedelta(days=10),
                weights_g_json=json.dumps([200,200]),sample_count=2,average_weight_g=200),
        ])
        db.add(Mortality(cycle_id=cycle.id,dead_count=100,observed_on=today-timedelta(days=5)))
        db.add(WaterQuality(unit_id=unit.id,observed_at=datetime.combine(
            today,datetime.min.time(),timezone.utc),temperature_c=29,
            dissolved_oxygen_mg_l=5.5,ph=7.2))
        feed=FeedProduct(farm_id=farm_id,name='Grower feed')
        db.add(feed);db.flush()
        feed_id=feed.id
        db.add_all([
            FeedLedger(feed_id=feed.id,event_type='receipt',quantity_delta_kg=100,
                cost_ghs=200,occurred_on=today-timedelta(days=15)),
            FeedLedger(feed_id=feed.id,event_type='feeding',quantity_delta_kg=-50,
                cycle_id=cycle.id,occurred_on=today-timedelta(days=5)),
        ])
        db.add(ProductionPlan(farm_id=farm_id,cycle_id=cycle.id,species='Tilapia',
            fingerling_count=1000,initial_weight_g=10,target_weight_g=500,
            survival_pct=90,expected_fcr=1.5,feed_price_ghs_per_kg=2,
            bag_size_kg=25,fingerling_cost_ghs=100,other_budget_ghs=50,
            desired_profit_pct=20,profit_method='markup'))
        db.commit()

    response=client.get(f'/farms/{farm_id}/dashboard/analytics',headers=farmer)
    assert response.status_code==200,response.text
    analytics=response.json()
    assert analytics['summary']['expected_harvest_kg']==450
    assert analytics['summary']['estimated_live_fish']==900
    forecast=analytics['production']['harvest_forecasts'][0]
    assert forecast['expected_harvest_on']==(today+timedelta(days=20)).isoformat()
    assert forecast['date_basis']=='linear_projection_from_last_two_samples'
    assert analytics['production']['unit_comparisons'][0]['mortality_pct']==10
    assert analytics['production']['unit_comparisons'][0]['indicative_fcr']==0.2941
    assert analytics['feed']['inventory'][0]['remaining_stock_kg']==50
    assert analytics['feed']['inventory'][0]['estimated_consumed_cost_ghs']==100
    assert analytics['water_quality']['latest_by_unit'][0]['dissolved_oxygen_mg_l']==5.5
    pricing=analytics['finance']['pricing_by_plan'][0]
    assert pricing['projected_harvest_kg']==450
    assert pricing['break_even_ghs_per_kg']==2.36
    assert pricing['recommended_price_ghs_per_kg']==2.83
    assert pricing['projected_revenue_ghs']>pricing['projected_cycle_total_cost_ghs']
    assert pricing['projected_profit_ghs']>0
    updated=client.patch(f'/farms/{farm_id}/production-plans/{pricing["plan_id"]}/pricing',
        headers=farmer,json={'desired_profit_pct':30,'profit_method':'markup',
            'market_price_ghs_per_kg':3.5})
    assert updated.status_code==200,updated.text
    assert updated.json()['desired_profit_pct']==30
    assert updated.json()['market_price_ghs_per_kg']==3.5
    assert updated.json()['market_price_difference_ghs_per_kg']<0
    assert updated.json()['market_projected_profit_ghs'] is not None
    other_access=client.patch(
        f'/farms/{farm_id}/production-plans/{pricing["plan_id"]}/pricing',
        headers=signup('dashboard-pricing-other@example.com'),
        json={'desired_profit_pct':10,'profit_method':'markup','market_price_ghs_per_kg':None})
    assert other_access.status_code==404
    with SessionLocal() as db:
        db.add(Mortality(cycle_id=cycle_id,dead_count=100,observed_on=today))
        db.add(CycleExpense(plan_id=pricing['plan_id'],category='labour',
            amount_ghs=100,occurred_on=today))
        db.add(FeedLedger(feed_id=feed_id,event_type='receipt',quantity_delta_kg=100,
            cost_ghs=400,occurred_on=today))
        db.commit()
    recalculated=client.get(f'/farms/{farm_id}/dashboard/analytics',headers=farmer)
    assert recalculated.status_code==200,recalculated.text
    refreshed=recalculated.json()['finance']['pricing_by_plan'][0]
    assert recalculated.json()['summary']['expected_harvest_kg']==400
    assert recalculated.json()['production']['harvest_forecasts'][0]['expected_harvest_kg']==400
    assert refreshed['projected_harvest_kg']==400
    assert refreshed['projected_cycle_total_cost_ghs']>pricing['projected_cycle_total_cost_ghs']
    assert refreshed['recommended_price_ghs_per_kg']>updated.json()['recommended_price_ghs_per_kg']
    report=client.get(f'/farms/{farm_id}/reports/bank-ready.xlsx',headers=farmer)
    assert report.status_code==200,report.text
    workbook=load_workbook(BytesIO(report.content),read_only=True,data_only=True)
    assert 'Growth History' in workbook.sheetnames
    harvest_sheet=workbook['Harvest Forecasts']
    headers=next(harvest_sheet.iter_rows(min_row=1,max_row=1,values_only=True))
    date_column=headers.index('expected_harvest_on')
    assert any(row[date_column]==(today+timedelta(days=20)).isoformat()
        for row in harvest_sheet.iter_rows(min_row=2,values_only=True))
    inventory_csv=client.get(f'/farms/{farm_id}/reports/analytics/inventory.csv',headers=farmer)
    assert inventory_csv.status_code==200,inventory_csv.text
    assert 'Grower feed' in inventory_csv.text
