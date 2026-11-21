from datetime import date
from .test_api import client
from .test_operations import auth
from .test_foundation import upload_operation_evidence

def test_feed_stock_and_ownership():
    owner = auth('feed-owner@example.com')
    other = auth('feed-other@example.com')
    farm = client.post('/farms', json={'name':'Feed Test Farm','region':'Northern','district':'Tamale','farm_type':'pond','species':'Tilapia','latitude':9.4,'longitude':-0.8}, headers=owner)
    assert farm.status_code == 201, farm.text
    fid = farm.json()['id']
    unit = client.post(f'/farms/{fid}/units', json={'name':'Pond Feed','unit_type':'pond','capacity_m3':100}, headers=owner)
    assert unit.status_code == 201, unit.text
    uid = unit.json()['id']
    unit_data = unit.json()
    stocking = upload_operation_evidence(fid, unit_data, owner, 'stocking')
    assert stocking.status_code == 201, stocking.text
    cycle = client.post(f'/farms/{fid}/units/{uid}/cycles', params={'evidence_id':stocking.json()['id']}, json={'species':'Nile Tilapia','stocked_count':1000,'initial_average_weight_g':20,'stocked_on':date.today().isoformat()}, headers=owner)
    assert cycle.status_code == 201, cycle.text
    cid = cycle.json()['id']
    product = client.post(f'/farms/{fid}/feeds', json={'name':'Tilapia Starter','protein_pct':35}, headers=owner)
    assert product.status_code == 201, product.text
    feed_id = product.json()['id']
    assert client.get(f'/farms/{fid}/feeds', headers=other).status_code == 404
    receipt_evidence = upload_operation_evidence(fid, unit_data, owner, 'feed_delivery')
    assert receipt_evidence.status_code == 201, receipt_evidence.text
    evidence_params = {'unit_id':uid, 'evidence_id':receipt_evidence.json()['id']}
    assert client.post(f'/farms/{fid}/feeds/{feed_id}/receipts', params=evidence_params, json={'quantity_kg':50,'total_cost_ghs':300,'occurred_on':date.today().isoformat()}, headers=other).status_code == 404
    receipt = client.post(f'/farms/{fid}/feeds/{feed_id}/receipts', params=evidence_params, json={'quantity_kg':50,'total_cost_ghs':300,'occurred_on':date.today().isoformat()}, headers=owner)
    assert receipt.status_code == 201, receipt.text
    root = f'/farms/{fid}/units/{uid}/cycles/{cid}'
    feeding_evidence = upload_operation_evidence(fid, unit_data, owner, 'feeding', cid)
    assert feeding_evidence.status_code == 201, feeding_evidence.text
    feeding_params = {'evidence_id':feeding_evidence.json()['id']}
    assert client.post(f'{root}/feeding', params=feeding_params, json={'feed_id':feed_id,'quantity_kg':51,'fed_on':date.today().isoformat()}, headers=owner).status_code == 409
    fed = client.post(f'{root}/feeding', params=feeding_params, json={'feed_id':feed_id,'quantity_kg':2,'fed_on':date.today().isoformat()}, headers=owner)
    assert fed.status_code == 201, fed.text
    assert client.get(f'/farms/{fid}/feeds', headers=owner).json()[0]['stock_kg'] == 48
    assert client.post(f'/farms/{fid}/feeding-profiles/tilapia/approve', headers=owner).status_code == 200
    estimate = client.post(f'{root}/feeding-estimate', json={'feed_id':feed_id,'daily_feeding_rate_pct':5}, headers=owner)
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()['estimated_daily_feed_kg'] == 1
    assert estimate.json()['automatic_recommendation_suspended'] is True
    recommendation_id = estimate.json()['recommendation_id']
    assert client.post(
        f'/farms/{fid}/feeding-recommendations/{recommendation_id}/approve',
        headers=owner,
    ).status_code == 409
    recommendations = client.get(f'/farms/{fid}/feeding-recommendations', headers=owner)
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()[0]['actual_total_kg'] == 0

    count_evidence = upload_operation_evidence(fid, unit_data, owner, 'feed_stock_count')
    assert count_evidence.status_code == 201, count_evidence.text
    reconciliation = client.post(
        f'/farms/{fid}/feeds/{feed_id}/reconciliations',
        params={'unit_id':uid, 'evidence_id':count_evidence.json()['id']},
        json={'physical_stock_kg':45,'occurred_on':date.today().isoformat(),'reason':'Physical bag count'},
        headers=owner,
    )
    assert reconciliation.status_code == 201, reconciliation.text
    assert reconciliation.json()['variance_kg'] == -3
    assert client.get(f'/farms/{fid}/feeds', headers=owner).json()[0]['stock_kg'] == 45
    forecast = client.get(f'/farms/{fid}/feed-forecast', headers=owner)
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()['cycles_without_approved_recommendation'] == [cid]
    assert forecast.json()['feeds'][0]['current_stock_kg'] == 45
    fcr = client.get(f'{root}/fcr', headers=owner)
    assert fcr.status_code == 200, fcr.text
    assert fcr.json()['indicative_fcr'] is None
