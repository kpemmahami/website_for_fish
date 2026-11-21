from datetime import datetime, timezone
import uuid

from .test_api import client

def signup(email):
    response = client.post('/auth/register',json={'full_name':'Farm Owner','email':email,'password':'a-very-long-password-123'})
    assert response.status_code == 201, response.text
    token = client.post('/auth/login',json={'email':email,'password':'a-very-long-password-123'}).json()['access_token']
    return {'Authorization':f'Bearer {token}'}


def upload_operation_evidence(farm_id, unit, headers, record_type, cycle_id=None):
    challenge_params = {}
    if record_type in {
        'feeding', 'growth', 'mortality', 'stocking', 'feed_stock_count',
        'fish_transfer', 'harvest', 'treatment',
    }:
        challenge = client.post(
            f'/farms/{farm_id}/evidence-challenges',
            headers=headers,
            json={'unit_id': unit['id'], 'activity_type': record_type},
        )
        assert challenge.status_code == 200, challenge.text
        challenge_params = {
            'challenge_id': challenge.json()['id'],
            'challenge_code': challenge.json()['code'],
        }
    captured_at = datetime.now(timezone.utc).isoformat()
    params = {
        'unit_id': unit['id'],
        'unit_tag': unit['evidence_tag'],
        'record_type': record_type,
        'captured_at': captured_at,
        'device_recorded_at': captured_at,
        'latitude': 9.4,
        'longitude': -0.8,
        'gps_accuracy_m': 5,
        'duration_seconds': 15,
        **challenge_params,
    }
    if cycle_id is not None:
        params['cycle_id'] = cycle_id
    return client.post(
        f'/farms/{farm_id}/evidence',
        params=params,
        headers={**headers, 'Content-Type': 'video/webm'},
        content=b'\x1a\x45\xdf\xa3' + uuid.uuid4().bytes,
    )


def test_gps_units_audit_and_archiving():
    a = signup('owner-gps@example.com')
    b = signup('other-gps@example.com')
    farm = {'name':'Tilapia Farm','region':'Northern','district':'Tamale Metro','farm_type':'pond','species':'Tilapia','latitude':9.4,'longitude':-0.8,'location_method':'manual'}
    bad = dict(farm, longitude=None)
    assert client.post('/farms',json=bad,headers=a).status_code == 422
    result = client.post('/farms',json=farm,headers=a)
    assert result.status_code == 201, result.text
    fid = result.json()['id']
    unit={'name':'Pond A','unit_type':'pond','capacity_m3':120,'latitude':9.4,'longitude':-0.8}
    assert client.post(f'/farms/{fid}/units',json=unit,headers=b).status_code == 404
    created=client.post(f'/farms/{fid}/units',json=unit,headers=a)
    assert created.status_code == 201,created.text
    uid=created.json()['id']
    assert len(client.get(f'/farms/{fid}/units',headers=a).json()) == 1
    assert client.get(f'/farms/{fid}/audit',headers=b).status_code == 404
    assert len(client.get(f'/farms/{fid}/audit',headers=a).json()) == 2
    assert client.delete(f'/farms/{fid}/units/{uid}',headers=a).status_code == 204
    assert client.get(f'/farms/{fid}/units',headers=a).json() == []
    assert client.delete(f'/farms/{fid}',headers=a).status_code == 204
    assert client.get(f'/farms/{fid}',headers=a).status_code == 404
