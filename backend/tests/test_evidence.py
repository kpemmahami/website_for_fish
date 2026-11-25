from datetime import date
from pathlib import Path
from .test_api import approve_test_registration, client
from .test_foundation import upload_operation_evidence


def auth(email):
    password = 'a-very-long-password-123'
    approve_test_registration(client.post('/auth/register', json={
        'full_name': 'Evidence Tester', 'phone_number': '0245550104', 'email': email, 'password': password
    }))
    token = client.post('/auth/login', json={'email': email, 'password': password}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_daily_record_evidence_is_private_linked_and_deletable(tmp_path, monkeypatch):
    monkeypatch.setenv('AQUAFARM_EVIDENCE_DIR', str(tmp_path))
    owner = auth('evidence-owner@example.com')
    other = auth('evidence-other@example.com')
    unauthorized = auth('evidence-private@example.com')
    farm = client.post('/farms', headers=owner, json={
        'name': 'Evidence Farm', 'region': 'Northern', 'district': 'Tamale',
        'farm_type': 'pond', 'species': 'Catfish', 'latitude': 9.4, 'longitude': -0.8,
    })
    assert farm.status_code == 201, farm.text
    farm_id = farm.json()['id']
    supervisor_user = client.get('/auth/me', headers=other)
    assert supervisor_user.status_code == 200
    assigned = client.post(
        f'/farms/{farm_id}/supervisors',
        headers=owner,
        json={'user_id':supervisor_user.json()['id']},
    )
    assert assigned.status_code == 201, assigned.text
    unit = client.post(f'/farms/{farm_id}/units', headers=owner, json={
        'name': 'Pond 1', 'unit_type': 'pond'
    })
    assert unit.status_code == 201, unit.text
    unit_id = unit.json()['id']
    stocking = upload_operation_evidence(farm_id, unit.json(), owner, 'stocking')
    assert stocking.status_code == 201, stocking.text
    cycle = client.post(f'/farms/{farm_id}/units/{unit_id}/cycles', headers=owner, params={
        'evidence_id': stocking.json()['id'],
    }, json={
        'species': 'Catfish', 'stocked_count': 100, 'initial_average_weight_g': 10,
        'stocked_on': date.today().isoformat()
    })
    assert cycle.status_code == 201, cycle.text
    cycle_id = cycle.json()['id']

    uploaded = upload_operation_evidence(farm_id, unit.json(), owner, 'mortality', cycle_id)
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()['id']
    evidence_path = next(Path(tmp_path).glob('*.webm'))
    assert evidence_path.read_bytes().startswith(b'\x1a\x45\xdf\xa3')
    assert client.get(f'/farms/{farm_id}/evidence/{evidence_id}/video', headers=unauthorized).status_code == 404

    mortality = client.post(
        f'/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/mortality',
        headers=owner,
        params={'evidence_id': evidence_id},
        json={'dead_count': 1, 'observed_on': date.today().isoformat()},
    )
    assert mortality.status_code == 201, mortality.text
    evidence_rows = client.get(
        f'/farms/{farm_id}/evidence',
        headers=owner,
        params={'cycle_id': cycle_id, 'record_type': 'mortality'},
    )
    assert evidence_rows.status_code == 200, evidence_rows.text
    attached = next(item for item in evidence_rows.json() if item['id'] == evidence_id)
    assert attached['record_id'] == mortality.json()['id']
    review_queue = client.get(f'/farms/{farm_id}/evidence-review', headers=other)
    assert review_queue.status_code == 200, review_queue.text
    correction = client.post(
        f'/farms/{farm_id}/evidence/{evidence_id}/correction-requests',
        headers=other,
        json={'reason':'Mortality count needs supervisor clarification'},
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()['verification_status'] == 'flagged'
    verified = client.post(
        f'/farms/{farm_id}/evidence/{evidence_id}/verification',
        headers=other,
        json={'verification_status':'verified','notes':'Correction reviewed with farmer.'},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()['verified_by'] == supervisor_user.json()['id']
    assert client.post(
        f'/farms/{farm_id}/evidence/{evidence_id}/attach',
        headers=other,
        json={'record_id':mortality.json()['id']},
    ).status_code == 404
    assert client.delete(
        f'/farms/{farm_id}/evidence/{evidence_id}',
        headers=other,
    ).status_code == 404
    video_response = client.get(f'/farms/{farm_id}/evidence/{evidence_id}/video', headers=owner)
    assert video_response.status_code == 200
    assert video_response.content.startswith(b'\x1a\x45\xdf\xa3')
    assert client.delete(f'/farms/{farm_id}/evidence/{evidence_id}', headers=owner).status_code == 409
    assert evidence_path.exists()
