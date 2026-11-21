from datetime import date, datetime, timedelta, timezone
from .test_api import client
from .test_foundation import upload_operation_evidence


def auth(email):
    data = {'full_name': 'Operations Tester', 'email': email, 'password': 'a-very-long-password-123'}
    assert client.post('/auth/register', json=data).status_code == 201
    token = client.post('/auth/login', json={'email': email, 'password': data['password']}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_operations_and_ownership():
    owner = auth('ops-owner@example.com')
    other = auth('ops-other@example.com')
    farm = client.post('/farms', json={'name':'Operations Farm','region':'Northern','district':'Tamale', 'farm_type':'pond', 'species':'Tilapia', 'latitude':9.4, 'longitude':-0.8}, headers=owner)
    assert farm.status_code == 201, farm.text
    fid = farm.json()['id']
    unit = client.post(f'/farms/{fid}/units', json={'name':'Pond A', 'unit_type':'pond', 'capacity_m3':150}, headers=owner)
    assert unit.status_code == 201, unit.text
    uid = unit.json()['id']
    unit_data = unit.json()
    root = f'/farms/{fid}/units/{uid}'
    payload = {'species':'Nile Tilapia','stocked_count':1000, 'initial_average_weight_g':20, 'stocked_on':date.today().isoformat()}
    future_payload = {**payload, 'stocked_on':(date.today()+timedelta(days=1)).isoformat()}
    stocking = upload_operation_evidence(fid, unit_data, owner, 'stocking')
    assert stocking.status_code == 201, stocking.text
    stocking_params = {'evidence_id': stocking.json()['id']}
    assert client.post(f'{root}/cycles', params=stocking_params, json=future_payload, headers=owner).status_code == 422
    assert client.post(f'{root}/cycles', params=stocking_params, json=payload, headers=other).status_code == 404
    cycle = client.post(f'{root}/cycles', params=stocking_params, json=payload, headers=owner)
    assert cycle.status_code == 201, cycle.text
    cid = cycle.json()['id']
    path = f'{root}/cycles/{cid}'
    assert client.post(f'{root}/cycles', params=stocking_params, json=payload, headers=owner).status_code == 409
    assert client.get(f'{path}/population', headers=owner).json()['estimated_biomass_kg'] == 20
    mortality_evidence = upload_operation_evidence(fid, unit_data, owner, 'mortality', cid)
    assert mortality_evidence.status_code == 201, mortality_evidence.text
    mortality_params = {'evidence_id': mortality_evidence.json()['id']}
    mortality = client.post(f'{path}/mortality', params=mortality_params, json={'dead_count':25,'observed_on':date.today().isoformat()}, headers=owner)
    assert mortality.status_code == 201, mortality.text
    assert client.post(f'{path}/mortality', params=mortality_params, json={'dead_count':1000,'observed_on':date.today().isoformat()}, headers=owner).status_code == 409
    sample_evidence = upload_operation_evidence(fid, unit_data, owner, 'growth', cid)
    assert sample_evidence.status_code == 201, sample_evidence.text
    sample = client.post(f'{path}/samples', params={'evidence_id':sample_evidence.json()['id']}, json={'sampled_on':date.today().isoformat(),'weights_g':[30,40,50]}, headers=owner)
    assert sample.status_code == 201, sample.text
    assert sample.json()['average_weight_g'] == 40
    pop = client.get(f'{path}/population', headers=owner).json()
    assert pop['estimated_live_count'] == 975
    assert pop['estimated_biomass_kg'] == 39
    water_evidence = upload_operation_evidence(fid, unit_data, owner, 'water_quality', cid)
    assert water_evidence.status_code == 201, water_evidence.text
    water = client.post(f'{root}/water-quality', params={'cycle_id':cid, 'evidence_id':water_evidence.json()['id']}, json={'observed_at':datetime.now(timezone.utc).isoformat(), 'temperature_c':28, 'dissolved_oxygen_mg_l':5.5, 'ph':7.2}, headers=owner)
    assert water.status_code == 201, water.text
    assert len(client.get(f'{root}/water-quality', headers=owner).json()) == 1

    treatment_evidence = upload_operation_evidence(fid, unit_data, owner, 'treatment', cid)
    assert treatment_evidence.status_code == 201, treatment_evidence.text
    treatment = client.post(
        f'{path}/treatments',
        params={'evidence_id':treatment_evidence.json()['id']},
        json={
            'product':'Salt bath','dose':2,'dose_unit':'g/L','reason':'External parasite observation',
            'prescriber':'Aquaculture officer','withdrawal_period_days':0,
            'treated_on':date.today().isoformat(),
        },
        headers=owner,
    )
    assert treatment.status_code == 201, treatment.text
    assert client.get(f'{path}/treatments', headers=owner).json()[0]['evidence_id'] == treatment_evidence.json()['id']

    inspection_evidence = upload_operation_evidence(fid, unit_data, owner, 'inspection')
    assert inspection_evidence.status_code == 201, inspection_evidence.text
    inspection = client.post(
        f'/farms/{fid}/units/{uid}/inspections',
        params={'evidence_id':inspection_evidence.json()['id']},
        json={
            'inspected_on':date.today().isoformat(),
            'checklist':{'water_inlet':True,'aeration':False},
            'observations':'Routine pond inspection',
            'issues':'Backup aerator unavailable',
            'corrective_actions':'Repair the backup aerator',
        },
        headers=owner,
    )
    assert inspection.status_code == 201, inspection.text
    assert client.get(f'/farms/{fid}/units/{uid}/inspections', headers=owner).json()[0]['evidence_id'] == inspection_evidence.json()['id']

    assert client.get(f'{root}/activity', headers=other).status_code == 404
    activity = client.get(f'{root}/activity', headers=owner)
    assert activity.status_code == 200, activity.text
    assert {'production_unit','stocking_cycle','mortality_record','fish_sample','water_quality_record'} <= {r['entity_type'] for r in activity.json()}
    assert client.post(f'{path}/close', headers=owner).status_code == 200
    assert client.post(f'{path}/mortality', params=mortality_params, json={'dead_count':1,'observed_on':date.today().isoformat()}, headers=owner).status_code == 409
    next_stocking = upload_operation_evidence(fid, unit_data, owner, 'stocking')
    assert next_stocking.status_code == 201, next_stocking.text
    assert client.post(f'{root}/cycles', params={'evidence_id':next_stocking.json()['id']}, json=payload, headers=owner).status_code == 201


def test_fish_transfer_reconciles_source_and_destination_population():
    owner = auth('transfer-owner@example.com')
    farm = client.post('/farms', json={
        'name':'Transfer Farm','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Catfish','latitude':9.4,'longitude':-0.8,
    }, headers=owner)
    assert farm.status_code == 201, farm.text
    farm_id = farm.json()['id']
    units = []
    cycles = []
    for name in ('Source Pond','Destination Pond'):
        unit = client.post(f'/farms/{farm_id}/units', json={'name':name,'unit_type':'pond'}, headers=owner)
        assert unit.status_code == 201, unit.text
        units.append(unit.json())
        evidence = upload_operation_evidence(farm_id, unit.json(), owner, 'stocking')
        assert evidence.status_code == 201, evidence.text
        cycle = client.post(
            f"/farms/{farm_id}/units/{unit.json()['id']}/cycles",
            params={'evidence_id':evidence.json()['id']},
            json={
                'species':'Catfish','stocked_count':1000,'initial_average_weight_g':10,
                'stocked_on':date.today().isoformat(),
            },
            headers=owner,
        )
        assert cycle.status_code == 201, cycle.text
        cycles.append(cycle.json())

    evidence = upload_operation_evidence(farm_id, units[0], owner, 'fish_transfer', cycles[0]['id'])
    assert evidence.status_code == 201, evidence.text
    transfer = client.post(
        f'/farms/{farm_id}/fish-transfers',
        params={'evidence_id':evidence.json()['id']},
        json={
            'source_cycle_id':cycles[0]['id'],
            'target_cycle_id':cycles[1]['id'],
            'fish_count':100,
            'loss_count':5,
            'transferred_on':date.today().isoformat(),
        },
        headers=owner,
    )
    assert transfer.status_code == 201, transfer.text
    source = client.get(
        f"/farms/{farm_id}/units/{units[0]['id']}/cycles/{cycles[0]['id']}/population",
        headers=owner,
    )
    target = client.get(
        f"/farms/{farm_id}/units/{units[1]['id']}/cycles/{cycles[1]['id']}/population",
        headers=owner,
    )
    assert source.json()['estimated_live_count'] == 895
    assert target.json()['estimated_live_count'] == 1100
    assert client.get(f'/farms/{farm_id}/fish-transfers', headers=owner).json()[0]['evidence_id'] == evidence.json()['id']
