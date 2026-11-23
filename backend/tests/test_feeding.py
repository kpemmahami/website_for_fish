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

    from datetime import datetime, timedelta, timezone
    from app.feeding import FeedingRecommendation
    from app.feeding_sessions import daily_summary
    from app.main import SessionLocal
    from app.operations import StockingCycle

    today = date.today()
    with SessionLocal.begin() as db:
        recommendation = db.get(FeedingRecommendation, recommendation_id)
        recommendation.status = 'approved'
        recommendation.approved_at = datetime.now(timezone.utc)
        recommendation.daily_ration_kg = 2
        recommendation.session_count = 4
        recommendation.session_ration_kg = 0.5
    schedule = f'{root}/feeding-sessions?day={today}'
    original = client.get(schedule, headers=owner).json()
    assert original['scheduled_count'] == 4
    assert original['pending_count'] == 4
    assert original['actual_kg'] == 2
    assert len(original['unassigned_entries']) == 1
    assert client.get(schedule, headers=other).status_code == 404
    assert client.put(f'{root}/feeding-sessions/times?day={today}', json={'times': {'1':'07:00','2':'12:00','3':'15:00','4':'18:00'}, 'ends': {'1':'09:00','2':'13:00','3':'16:00','4':'19:00'}}, headers=owner).status_code == 200
    from app.production_alerts import farm_activity
    from datetime import time
    with SessionLocal() as db:
        def attention(hour, minute=0):
            return farm_activity(db,fid,datetime.combine(today,time(hour,minute),timezone.utc))['feeding_attention']
        assert attention(6,59) == []
        opened = attention(7)
        assert [(item['number'],item['status']) for item in opened] == [(1,'due')]
        assert opened[0]['scheduled_end'] == '09:00'
        assert [(item['number'],item['status']) for item in attention(12)] == [(1,'missed'),(2,'due')]
        assert [(item['number'],item['status']) for item in attention(13)] == [(1,'missed'),(2,'missed')]
    # The original 2 kg remains on the historical unassigned entry; the schedule records only the three sessions below.
    for session, amount in enumerate((0.5, 0.4, 0.5), 1):
        video = upload_operation_evidence(fid, unit_data, owner, 'feeding', cid)
        payload = {'feed_id':feed_id, 'quantity_kg':amount, 'fed_on':str(today), 'session_number':session,
                   'recommendation_id':recommendation_id, 'actual_fed_at':today.isoformat()+'T00:00:00Z'}
        params = {'evidence_id':video.json()['id']}
        record = client.post(f'{root}/feeding', params=params, json=payload, headers=owner)
        assert record.status_code == 201, record.text
        assert client.post(f'{root}/feeding', params=params, json=payload, headers=owner).json()['id'] == record.json()['id']
        assert client.post(f'{root}/feeding', params=params, json={**payload,'quantity_kg':1}, headers=owner).status_code == 409
    report = client.get(schedule, headers=owner).json()
    assert report['recorded_count'] == 3
    assert report['completion_pct'] == 75
    assert report['actual_kg'] == 3.4
    assert round(sum(session['actual_kg'] for session in report['sessions']),2) == 1.4
    assert all(row['entries'][0]['recorder'] and row['entries'][0]['evidence_status']=='uploaded' for row in report['sessions'][:3])
    assert client.get(f'/farms/{fid}/feeds', headers=owner).json()[0]['stock_kg'] == 43.6
    with SessionLocal() as db:
        cycle_row = db.get(StockingCycle, cid)
        before = daily_summary(db, cycle_row, today, datetime.combine(today, datetime.min.time(), timezone.utc))
        after = daily_summary(db, cycle_row, today, datetime.combine(today + timedelta(days=1), datetime.min.time(), timezone.utc))
        assert before['pending_count'] == 1
        assert after['missed_count'] == 1
    skipped = client.post(f'{root}/feeding-sessions/4/skip?day={today}', json={'reason':'Feed unavailable'}, headers=owner)
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()['skipped_count'] == 1
    assert skipped.json()['sessions'][3]['actual_kg'] == 0
    assert client.get(f'/farms/{fid}/feeds', headers=owner).json()[0]['stock_kg'] == 43.6
    history = client.get(f'{root}/feeding-sessions/history?end={today}', headers=owner).json()
    assert history['completion_pct'] == 75 and history['skipped_count'] == 1

    grower = client.post(f'/farms/{fid}/feeds', json={'name':'Tilapia Grower'}, headers=owner).json()['id']
    video = upload_operation_evidence(fid, unit_data, owner, 'feed_delivery')
    assert client.post(f'/farms/{fid}/feeds/{grower}/receipts', params={
        'unit_id': uid, 'evidence_id': video.json()['id'],
    }, json={'quantity_kg':1,'total_cost_ghs':6,'occurred_on':str(today)}, headers=owner).status_code == 201
    video = upload_operation_evidence(fid, unit_data, owner, 'feeding', cid)
    extra = client.post(f'{root}/feeding', params={'evidence_id':video.json()['id']}, json={
        'feed_id':grower, 'quantity_kg':0.2, 'fed_on':str(today),
        'recommendation_id':recommendation_id, 'session_number':1,
    }, headers=owner)
    assert extra.status_code == 201, extra.text
    combined = client.get(schedule, headers=owner).json()
    assert combined['sessions'][0]['actual_kg'] == 0.7
    assert len(combined['sessions'][0]['entries']) == 2
    assert combined['recorded_count'] == 3
    stock_by_id = {item['id']:item['stock_kg'] for item in client.get(f'/farms/{fid}/feeds', headers=owner).json()}
    assert stock_by_id[grower] == 0.8
    assert stock_by_id[feed_id] == 43.6

    from app.operations import FishSample
    with SessionLocal.begin() as db:
        db.add(FishSample(cycle_id=cid,sampled_on=today,weights_g_json='[25]',sample_count=1,average_weight_g=25))
    changed = client.get(schedule, headers=owner).json()['frequency_advisory']
    assert changed['active_sessions'] == 4
    assert changed['suggested_sessions'] == 2
    assert changed['effective_on_if_approved'] == str(today + timedelta(days=1))
    with SessionLocal.begin() as db:
        old = db.get(FeedingRecommendation, recommendation_id)
        values = {column.name: getattr(old,column.name) for column in old.__table__.columns if column.name!='id'}
        values.update(session_count=2, session_ration_kg=1, approved_at=datetime.now(timezone.utc))
        db.add(FeedingRecommendation(**values))
    assert client.get(schedule, headers=owner).json()['scheduled_count'] == 4
    tomorrow = today + timedelta(days=1)
    with SessionLocal() as db:
        next_day = daily_summary(db, db.get(StockingCycle,cid), tomorrow, datetime.combine(tomorrow,datetime.min.time(),timezone.utc))
        assert next_day['scheduled_count'] == 2
        assert next_day['recorded_count'] == 0

    summary_path = f'/farms/{fid}/dashboard/production-feeding'
    filters = {'cycle_ids':[cid,cid], 'start':str(today), 'end':str(today), 'forecast_days':14}
    filtered = client.post(summary_path, json=filters, headers=owner)
    assert filtered.status_code == 200, filtered.text
    result = filtered.json()
    assert len(result['cycles']) == 1
    assert result['cycles'][0]['period']['recorded_count'] == 3
    assert result['cycles'][0]['period']['actual_kg'] == 3.6
    assert result['cycles'][0]['today']['scheduled_count'] == 4
    assert result['cycles'][0]['forecast']['quantity_kg'] == 28
    assert result['balances'][0]['balance_kg'] == 15.6
    assert client.post(summary_path, json={**filters,'cycle_ids':[]}, headers=owner).json() == {'cycles':[],'balances':[]}
    assert client.post(summary_path, json={**filters,'cycle_ids':[cid,999999]}, headers=owner).status_code == 404
    assert client.post(summary_path, json=filters, headers=other).status_code == 404
    assert client.post(summary_path, json={**filters,'start':str(today+timedelta(days=1))}, headers=owner).status_code == 422


def test_operational_schedule_sessions_without_ration(monkeypatch):
    from datetime import datetime, time, timedelta, timezone
    from app import feeding_sessions
    from app.feeding import FeedLedger
    from app.main import SessionLocal
    from app.operations import StockingCycle
    from app.production_alerts import farm_activity

    owner = auth('operational-feeding@example.com')
    other = auth('operational-feeding-other@example.com')
    farm = client.post('/farms', json={
        'name':'Operational Feeding Farm','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Tilapia','latitude':9.4,'longitude':-0.8,
    }, headers=owner).json()
    farm_id = farm['id']
    unit = client.post(f'/farms/{farm_id}/units', json={'name':'Pond A','unit_type':'pond'}, headers=owner).json()
    other_unit = client.post(f'/farms/{farm_id}/units', json={'name':'Pond B','unit_type':'pond'}, headers=owner).json()
    feed = client.post(f'/farms/{farm_id}/feeds', json={'name':'Grower'}, headers=owner).json()
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    with SessionLocal.begin() as db:
        cycle = StockingCycle(unit_id=unit['id'],species='Tilapia',stocked_count=100,initial_average_weight_g=30,stocked_on=day)
        second = StockingCycle(unit_id=other_unit['id'],species='Tilapia',stocked_count=100,initial_average_weight_g=30,stocked_on=day)
        db.add_all([cycle, second])
        db.flush()
        cycle_id, second_id = cycle.id, second.id
        db.add(FeedLedger(feed_id=feed['id'],event_type='receipt',quantity_delta_kg=10,cost_ghs=50,occurred_on=day))

    root = f'/farms/{farm_id}/units/{unit["id"]}/cycles/{cycle_id}'
    second_root = f'/farms/{farm_id}/units/{other_unit["id"]}/cycles/{second_id}'
    path = root+'/feeding-sessions'
    windows = [{'name':name,'start':start,'end':end} for name,start,end in (
        ('Morning','07:00','09:00'),('Midday','12:00','13:00'),
        ('Afternoon','15:00','16:00'),('Evening','18:00','19:00'),
    )]

    class ScheduleClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(day, time.min, timezone.utc).astimezone(tz)

    config = {'effective_on':str(day),'sessions':windows}
    with monkeypatch.context() as mock:
        mock.setattr(feeding_sessions,'datetime',ScheduleClock)
        assert client.put(path+'/schedule', json=config, headers=other).status_code == 404
        assert client.put(path+'/schedule', json={**config,'sessions':[windows[0],windows[0]]}, headers=owner).status_code == 422
        saved = client.put(path+'/schedule', json=config, headers=owner)
        assert saved.status_code == 200, saved.text
        schedule_id = saved.json()['id']
        assert client.put(second_root+'/feeding-sessions/schedule', json={**config,'sessions':windows[:2]}, headers=owner).status_code == 200

    summary_path = f'{path}?day={day}'
    assert client.post(f'/farms/{farm_id}/feeding-profiles/tilapia/approve', headers=owner).status_code == 200
    estimate = client.post(root+'/feeding-estimate',json={'feed_id':feed['id']},headers=owner)
    assert estimate.status_code == 200 and estimate.json()['automatic_recommendation_suspended']
    initial = client.get(summary_path, headers=owner).json()
    assert initial['scheduled_count'] == 4 and initial['daily_ration_kg'] is None
    assert client.get(f'{second_root}/feeding-sessions?day={day}', headers=owner).json()['scheduled_count'] == 2

    def record(number, quantity, actual, **extra):
        evidence = upload_operation_evidence(farm_id, unit, owner, 'feeding', cycle_id)
        assert evidence.status_code == 201, evidence.text
        params = {'evidence_id':evidence.json()['id']}
        body = {'feed_id':feed['id'],'quantity_kg':quantity,'fed_on':str(day),'actual_fed_at':f'{day}T{actual}',
                'session_number':number, **({'schedule_id':schedule_id} if number else {}), **extra}
        return client.post(root+'/feeding', json=body, params=params, headers=owner), params, body

    def stock():
        return client.get(f'/farms/{farm_id}/feeds', headers=owner).json()[0]['stock_kg']

    assert record(1, 0.4, '08:00:00+00:00', schedule_id=schedule_id+1)[0].status_code == 409
    assert record(1, 0.4, '09:30:00Z')[0].status_code == 422
    first, params, body = record(1, 0.4, '09:00:00+01:00')
    assert first.status_code == 201, first.text
    assert client.post(root+'/feeding', json=body, params=params, headers=owner).json()['id'] == first.json()['id']
    assert stock() == 9.6
    assert record(1, 0.4, '08:15:00Z')[0].status_code == 409
    assert record(2, 0.6, '12:30:00Z')[0].status_code == 201
    assert client.get(summary_path, headers=owner).json()['actual_kg'] == 1.0
    with SessionLocal() as db:
        target = db.get(StockingCycle, cycle_id)
        during = feeding_sessions.daily_summary(db, target, day, datetime.combine(day,time(15,30),timezone.utc))
        assert [row['status'] for row in during['sessions']] == ['recorded','recorded','due','upcoming']
        attention = farm_activity(db, farm_id, datetime.combine(day,time(16,0),timezone.utc))['feeding_attention']
        assert any(row['cycle_id']==cycle_id and row['number']==3 and row['status']=='missed' for row in attention)
    assert record(4, 0.5, '18:30:00Z')[0].status_code == 201
    result = client.get(summary_path, headers=owner).json()
    assert result['actual_kg'] == 1.5 and result['recorded_count'] == 3 and result['missed_count'] == 1
    assert result['sessions'][2]['status'] == 'missed'
    assert stock() == 8.5
    assert record(4, 50, '18:45:00Z', additional_session_event=True)[0].status_code == 409
    assert record(4, 0.2, '18:45:00Z', additional_session_event=True)[0].status_code == 201
    assert record(None, 0.1, '15:30:00Z')[0].status_code == 422
    unplanned, _, _ = record(None, 0.1, '15:30:00Z', notes='Window confirmed after recording')
    assert unplanned.status_code == 201
    reconcile_path = path+'/reconcile/'+str(unplanned.json()['id'])
    assert client.post(reconcile_path,json={'session_number':2,'reason':'Wrong time window'},headers=owner).status_code == 422
    linked = client.post(reconcile_path,json={'session_number':3,'reason':'Actual time matches the afternoon session'},headers=owner)
    assert linked.status_code == 200, linked.text
    assert linked.json()['recorded_count'] == 4 and linked.json()['unscheduled_count'] == 0
    assert linked.json()['sessions'][2]['entries'][0]['on_time'] is True
    assert stock() == 8.2
    assert record(None, 0.1, '20:00:00Z', notes='Feeding after the last session')[0].status_code == 201
    history = client.get(f'{path}/history?end={day}&days=7',headers=owner).json()
    assert history['recorded_count'] == 4 and history['recommended_kg'] is None
    assert history['days'][0]['unscheduled_count'] == 1 and history['actual_kg'] == 1.9
    cost = client.get(root+'/feeding-costs', headers=owner).json()
    assert cost['total_indicative_cost_ghs'] == 9.5
    next_day = day + timedelta(days=1)
    updated = client.put(path+'/schedule',json={'effective_on':str(next_day),'sessions':windows[:2]},headers=owner)
    assert updated.status_code == 200, updated.text
    assert client.get(summary_path,headers=owner).json()['scheduled_count'] == 4
    assert client.get(f'{path}?day={next_day}',headers=owner).json()['scheduled_count'] == 2
