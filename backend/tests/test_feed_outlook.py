from datetime import datetime, timedelta, timezone

from .test_api import client
from .test_operations import auth
from app.evidence import RecordEvidence
from app.feeding import FeedLedger
from app.main import SessionLocal
from app.operations import FishSample, Mortality, StockingCycle, WaterQuality
from app.sales import HarvestLot


def test_forecast_requires_fresh_approved_data_and_recalculates_from_farm_records():
    owner = auth('outlook-owner@example.com')
    outsider = auth('outlook-outsider@example.com')
    farm = client.post('/farms', headers=owner, json={
        'name':'Outlook Farm','region':'Northern','district':'Tamale','farm_type':'pond','species':'Tilapia',
    }).json()
    base = f'/farms/{farm["id"]}'
    pond = client.post(base+'/units',headers=owner,json={'name':'Starter pond','unit_type':'pond'}).json()
    tank = client.post(base+'/units',headers=owner,json={'name':'Catfish tank','unit_type':'tank'}).json()
    feed = client.post(base+'/feeds',headers=owner,json={'name':'Starter feed','pellet_size_mm':0.8}).json()
    instant = datetime.now(timezone.utc)
    today = instant.date()
    with SessionLocal.begin() as db:
        cycle = StockingCycle(unit_id=pond['id'],species='Tilapia',stocked_count=1000,initial_average_weight_g=4,stocked_on=today-timedelta(days=3))
        catfish = StockingCycle(unit_id=tank['id'],species='Catfish',stocked_count=500,initial_average_weight_g=4,stocked_on=cycle.stocked_on)
        db.add_all([cycle,catfish])
        db.flush()
        cycle_id, catfish_id = cycle.id, catfish.id
        db.add(FeedLedger(feed_id=feed['id'],event_type='receipt',quantity_delta_kg=1,cost_ghs=5,occurred_on=today))
    root = f'{base}/units/{pond["id"]}/cycles/{cycle_id}'
    estimate = {'feed_id':feed['id'],'daily_feeding_rate_pct':8}

    def outlook():
        response = client.get(base+'/feed-outlook',headers=owner)
        assert response.status_code == 200, response.text
        result = response.json()
        return next(row for row in result['cycles'] if row['cycle_id']==cycle_id),result

    def calculate():
        result = client.post(root+'/feeding-estimate',headers=owner,json=estimate)
        assert result.status_code == 200,result.text
        return result.json()

    def approve(item, actor=owner):
        return client.post(base+f'/feeding-recommendations/{item["recommendation_id"]}/approve',headers=actor)

    def evidence(db, record, kind, key):
        db.flush()
        row = RecordEvidence(farm_id=farm['id'],unit_id=pond['id'],cycle_id=cycle_id,
            record_type=kind,record_id=record.id,storage_name=key,media_type='video/webm',size_bytes=10,duration_seconds=15)
        db.add(row)
        db.flush()
        return row.id

    draft, report = outlook()
    assert draft['status']=='draft' and not draft['forecast']
    assert any('verified fish sample' in line for line in draft['reasons'])
    assert any('dissolved oxygen' in line for line in draft['reasons'])
    assert {row['cycle_id'] for row in report['cycles']}=={cycle_id,catfish_id}
    assert client.get(base+'/feed-outlook',headers=outsider).status_code==404
    assert client.post(base+'/feeding-profiles/tilapia/approve',headers=owner).status_code==200
    suspended = calculate()
    assert suspended['status']=='suspended' and approve(suspended).status_code==409

    with SessionLocal.begin() as db:
        water = WaterQuality(unit_id=pond['id'],observed_at=instant-timedelta(minutes=2),dissolved_oxygen_mg_l=6)
        db.add(water)
        water_evidence = evidence(db,water,'water_quality','outlook-water')
    review_path = base+f'/evidence/{water_evidence}/verification'
    assert client.post(review_path,headers=owner,json={'verification_status':'verified','notes':'Water reading reviewed'}).status_code==200
    provisional = calculate()
    assert provisional['status']=='provisional' and approve(provisional).status_code==409

    with SessionLocal.begin() as db:
        sample = FishSample(cycle_id=cycle_id,sampled_on=today,weights_g_json='[4]',sample_count=1,average_weight_g=4)
        db.add(sample)
        sample_evidence = evidence(db,sample,'growth','outlook-sample')
    assert client.post(base+f'/evidence/{sample_evidence}/verification',headers=owner,
                       json={'verification_status':'verified','notes':'Fish sample reviewed'}).status_code==200
    pending = calculate()
    assert pending['status']=='pending_approval' and outlook()[0]['status']=='pending_approval'
    assert approve(pending, outsider).status_code==404
    with SessionLocal.begin() as db:
        db.add(Mortality(cycle_id=cycle_id,dead_count=10,observed_on=today))
    assert approve(pending).status_code==409
    approved = calculate()
    assert approve(approved).status_code==200

    windows = [{'name':f'Session {i+1}','start':f'{7+i*3:02}:00','end':f'{8+i*3:02}:00','allocation_pct':pct}
               for i,pct in enumerate((10,20,30,40))]
    schedule = {'sessions':windows,'effective_on':str(today+timedelta(days=1))}
    assert client.put(root+'/feeding-sessions/schedule',headers=owner,json=schedule).status_code==200
    forecast, report = outlook()
    assert forecast['status']=='approved' and len(forecast['forecast'])==7
    assert forecast['forecast'][0]['date']==str(today+timedelta(days=1))
    assert forecast['forecast'][0]['daily_kg']==0.3168
    assert [row['quantity_kg'] for row in forecast['forecast'][0]['sessions']]==[0.03168,0.06336,0.09504,0.12672]
    assert report['inventory'][0]['shortage_kg']==1.2176
    assert report['inventory'][0]['available_kg']==1
    aggregate = client.get(base+'/feed-forecast?forecast_days=7',headers=owner).json()
    assert aggregate['feeds'][0]['expected_usage_kg']==2.2176
    dashboard = client.get(base+'/dashboard/analytics',headers=owner).json()
    assert dashboard['feed']['weekly_forecast']['feeds'][0]['expected_usage_kg']==2.2176

    with SessionLocal.begin() as db:
        db.add(HarvestLot(farm_id=farm['id'],cycle_id=cycle_id,harvested_on=today,quantity_kg=0.4,fish_count=100))
    revised, report = outlook()
    assert revised['estimated_live_count']==890 and revised['forecast'][0]['daily_kg']==0.2848
    assert revised['recommendation']['daily_ration_kg']==0.3168
    assert report['inventory'][0]['available_kg']==1

    with SessionLocal.begin() as db:
        linked = db.get(RecordEvidence,water_evidence)
        db.get(WaterQuality,linked.record_id).observed_at = instant-timedelta(days=2)
    expired, report = outlook()
    assert expired['status']=='expired' and not expired['forecast']
    assert report['inventory'][0]['required_kg']==0
