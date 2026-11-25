from .test_api import client
from .test_account_access import admin_headers, complete_initial_password, login, register_institution
from .test_foundation import signup
from app.lending import LoanApplication
from app.main import SessionLocal


def test_institution_staff_lifecycle():
    owner, registration = register_institution('staff-owner@example.com', {
        'name': 'Staff Test Bank', 'institution_type': 'bank', 'account_number': 'STAFF-TEST',
    })
    institution_id = registration.json()['id']
    assert client.post(f'/finance/institutions/{institution_id}/verify', headers=admin_headers()).status_code == 200
    root = f'/finance/institutions/{institution_id}/staff'
    staff_email = 'new-bank-staff@example.com'
    payload = {'email': staff_email, 'full_name': 'Ali', 'role': 'loan_officer',
               'phone_number': '+233545550173', 'password': 'eight123'}
    existing = signup('existing-bank-staff@example.com')
    assert client.post(root, json=payload).status_code == 401
    assert client.post(root, json=payload, headers=existing).status_code == 404
    assert client.post(root, json={**payload, 'role': 'owner'}, headers=owner).status_code == 422
    assert client.post(root+'/invitations', json=payload, headers=owner).status_code == 405
    for action in ('preview', 'activate'):
        assert client.post('/auth/institution/staff-invitations/'+action, json={'token': 'A' * 43}).status_code == 404
    created = client.post(root, json=payload, headers=owner)
    assert created.status_code == 201, created.text
    staff_id = created.json()['user_id']
    assert client.post(root, json=payload, headers=owner).status_code == 409
    assert payload['password'] not in client.get(root, headers=owner).text
    staff = complete_initial_password(staff_email, payload['password'])
    assert client.get('/finance/institutions/mine', headers=staff).json()[0]['role'] == 'loan_officer'
    assert client.get(f'/finance/institutions/{institution_id}/applications', headers=staff).status_code == 200
    farm = client.post('/farms',json={
        'name':'Staff Role Farm','region':'Northern','district':'Tamale','farm_type':'pond','species':'Tilapia',
    },headers=existing).json()
    with SessionLocal.begin() as db:
        application = LoanApplication(
            farm_id=farm['id'], institution_id=institution_id, requested_pesewas=15000,
            term_months=6, purpose='Staff role approval test', report_snapshot_json='{}',
        )
        db.add(application)
        db.flush()
        application_id = application.id
    decision = {'decision':'approved','rationale':'Review permission check', 'approved_ghs':100}
    appraisal = f'/finance/institutions/{institution_id}/applications/{application_id}/appraise'
    assert client.post(appraisal,json=decision,headers=staff).status_code == 404
    assert client.post(appraisal,json={'decision':'more_information','rationale':'Please provide more evidence'},headers=staff).status_code == 200
    assert client.patch(root+f'/{staff_id}',json={'role':'credit_manager'},headers=staff).status_code == 404
    assert client.patch(root+f'/{staff_id}',json={'role':'credit_manager'},headers=owner).status_code == 200
    assert client.post(appraisal,json=decision,headers=staff).status_code == 200
    owner_id = client.get('/auth/me',headers=owner).json()['id']
    assert client.patch(root+f'/{owner_id}',json={'status':'removed'},headers=owner).status_code == 403
    assert client.patch(root+f'/{staff_id}',json={'status':'suspended'},headers=owner).status_code == 200
    assert client.get(f'/finance/institutions/{institution_id}/applications',headers=staff).status_code == 404
    assert client.get('/finance/institutions/mine',headers=staff).json() == []
    assert client.patch(root+f'/{staff_id}',json={'status':'active'},headers=owner).status_code == 200
    assert client.get(f'/finance/institutions/{institution_id}/applications',headers=staff).status_code == 200

    existing_payload = {**payload, 'email': 'existing-bank-staff@example.com', 'role': 'viewer'}
    assert client.post(root, json=existing_payload, headers=owner).status_code == 409
    assert client.get('/finance/institutions/mine', headers=existing).json() == []
    assert client.get(root, headers=owner).json()['activity']
    assert client.get('/auth/me', headers=login('farmer', 'existing-bank-staff@example.com')).status_code == 200
