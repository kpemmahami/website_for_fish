from datetime import date

from .test_api import client
from .test_foundation import signup, upload_operation_evidence
from app.feeding import FeedLedger, FeedProduct
from app.main import SessionLocal
from app.operations import StockingCycle


def test_unit_assignments_are_scoped_and_revocable():
    owner = signup('staff-scope-owner@example.com')
    email = 'staff-scope-viewer@example.com'
    staff = signup(email)
    farm = client.post('/farms', headers=owner, json={
        'name': 'Assignment Test Farm', 'region': 'Northern', 'district': 'Tamale',
        'farm_type': 'pond', 'species': 'Tilapia', 'latitude': 9.4, 'longitude': -0.8,
    })
    assert farm.status_code == 201
    farm_id = farm.json()['id']
    units = []
    unit_details = []
    for name in ('Granted pond', 'Private pond'):
        response = client.post(f'/farms/{farm_id}/units', headers=owner, json={'name': name, 'unit_type': 'pond'})
        assert response.status_code == 201
        units.append(response.json()['id'])
        unit_details.append(response.json())
    grant = f'/farms/{farm_id}/units/{units[0]}/staff-access'
    assert client.post(grant, headers=staff, json={'email': email}).status_code == 404
    assigned = client.post(grant, headers=owner, json={'email': email})
    assert assigned.status_code == 201
    assert client.post(grant, headers=owner, json={'email': email}).status_code == 409
    scoped = client.get('/staff/assigned-units', headers=staff).json()
    assert [unit['unit_id'] for unit in scoped] == [units[0]]
    assert client.get(f'/farms/{farm_id}/units', headers=staff).status_code == 404
    assert client.get(f'/farms/{farm_id}/staff-unit-access', headers=staff).status_code == 404
    with SessionLocal.begin() as db:
        feed = FeedProduct(farm_id=farm_id, name='Pellets')
        db.add(feed)
        db.flush()
        feed_id = feed.id
        db.add(FeedLedger(feed_id=feed.id, event_type='receipt', quantity_delta_kg=20, occurred_on=date.today()))
        cycle_ids = []
        for unit_id, amount in zip(units, (2, 7)):
            cycle = StockingCycle(unit_id=unit_id, species='Tilapia', stocked_count=100,
                                  initial_average_weight_g=10, stocked_on=date.today())
            db.add(cycle)
            db.flush()
            cycle_ids.append(cycle.id)
            db.add(FeedLedger(feed_id=feed.id, cycle_id=cycle.id, event_type='feeding',
                              quantity_delta_kg=-amount, cost_ghs=100, occurred_on=date.today()))
    feeding_path = f'/staff/assigned-units/{units[0]}/feeding'
    feeding = client.get(feeding_path, headers=staff)
    assert feeding.status_code == 200, feeding.text
    entries = feeding.json()['items']
    assert len(entries) == 1 and entries[0]['quantity_kg'] == 2
    assert 'cost_ghs' not in entries[0]
    assert client.get(f'/staff/assigned-units/{units[1]}/feeding', headers=staff).status_code == 404
    entry_path = f'/farms/{farm_id}/units/{units[0]}/cycles/{cycle_ids[0]}/feeding'
    data = {'feed_id': feed_id, 'quantity_kg': 1, 'fed_on': date.today().isoformat()}
    assert client.post(entry_path, headers=staff, params={'evidence_id': 1}, json=data).status_code == 404
    assert client.post(grant, headers=owner, json={'email': email, 'can_record_feeding': True}).status_code == 201
    assert client.post(f'/farms/{farm_id}/evidence-challenges', headers=staff,
                       json={'unit_id': units[1], 'activity_type': 'feeding'}).status_code == 404
    assert client.post(f'/farms/{farm_id}/evidence-challenges', headers=staff,
                       json={'unit_id': units[0], 'activity_type': 'stocking'}).status_code == 404
    owner_video = upload_operation_evidence(farm_id, unit_details[0], owner, 'feeding', cycle_ids[0])
    assert owner_video.status_code == 201, owner_video.text
    assert client.post(entry_path, headers=staff, params={'evidence_id': owner_video.json()['id']}, json=data).status_code == 422
    staff_video = upload_operation_evidence(farm_id, unit_details[0], staff, 'feeding', cycle_ids[0])
    assert staff_video.status_code == 201, staff_video.text
    entry = client.post(entry_path, headers=staff, params={'evidence_id': staff_video.json()['id']}, json=data)
    assert entry.status_code == 201, entry.text
    assert entry.json()['recorded_by'] == assigned.json()['user_id']
    assert client.delete(f"{grant}/{assigned.json()['user_id']}", headers=owner).status_code == 204
    assert client.get('/staff/assigned-units', headers=staff).json() == []
    assert client.get(feeding_path, headers=staff).status_code == 404
    history = client.get(f'/farms/{farm_id}/staff-unit-access', headers=owner).json()
    assert len(history) == 1 and history[0]['is_active'] is False
    activity_path = f'/farms/{farm_id}/staff-unit-access/activity'
    assert client.get(activity_path, headers=staff).status_code == 404
    activity = client.get(activity_path, headers=owner).json()
    assert [event['action'] for event in activity['items']] == ['revoke_unit_view', 'grant_unit_view', 'grant_unit_view']
    assert all(event['unit_id'] == units[0] for event in activity['items'])
