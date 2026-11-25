from .test_api import client
from .test_foundation import signup


def test_unit_assignments_are_scoped_and_revocable():
    owner = signup('staff-scope-owner@example.com')
    email = 'staff-scope-viewer@example.com'
    staff = signup(email)
    farm = client.post('/farms', headers=owner, json={
        'name': 'Assignment Test Farm', 'region': 'Northern', 'district': 'Tamale',
        'farm_type': 'pond', 'species': 'Tilapia',
    })
    assert farm.status_code == 201
    farm_id = farm.json()['id']
    units = []
    for name in ('Granted pond', 'Private pond'):
        response = client.post(f'/farms/{farm_id}/units', headers=owner, json={'name': name, 'unit_type': 'pond'})
        assert response.status_code == 201
        units.append(response.json()['id'])
    grant = f'/farms/{farm_id}/units/{units[0]}/staff-access'
    assert client.post(grant, headers=staff, json={'email': email}).status_code == 404
    assigned = client.post(grant, headers=owner, json={'email': email})
    assert assigned.status_code == 201
    assert client.post(grant, headers=owner, json={'email': email}).status_code == 409
    scoped = client.get('/staff/assigned-units', headers=staff).json()
    assert [unit['unit_id'] for unit in scoped] == [units[0]]
    assert client.get(f'/farms/{farm_id}/units', headers=staff).status_code == 404
    assert client.get(f'/farms/{farm_id}/staff-unit-access', headers=staff).status_code == 404
    assert client.delete(f"{grant}/{assigned.json()['user_id']}", headers=owner).status_code == 204
    assert client.get('/staff/assigned-units', headers=staff).json() == []
    history = client.get(f'/farms/{farm_id}/staff-unit-access', headers=owner).json()
    assert len(history) == 1 and history[0]['is_active'] is False
