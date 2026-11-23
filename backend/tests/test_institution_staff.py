from datetime import timedelta
from unittest.mock import patch

from .test_api import client
from .test_account_access import admin_headers, login, register_institution
from .test_foundation import signup
from app.administration import token_digest
from app.institution_staff import StaffInvitation, utcnow
from app.lending import LoanApplication
from app.main import SessionLocal


def test_institution_staff_lifecycle():
    owner, registration = register_institution('staff-owner@example.com', {
        'name': 'Staff Test Bank', 'institution_type': 'bank', 'account_number': 'STAFF-TEST',
    })
    institution_id = registration.json()['id']
    assert client.post(f'/finance/institutions/{institution_id}/verify', headers=admin_headers()).status_code == 200
    root = f'/finance/institutions/{institution_id}/staff'
    invited_email = 'new-bank-staff@example.com'
    payload = {'email': invited_email, 'full_name': 'Ali', 'role': 'loan_officer'}
    existing = signup('existing-bank-staff@example.com')
    preview = '/auth/institution/staff-invitations/preview'
    activate = '/auth/institution/staff-invitations/activate'
    assert client.post(root+'/invitations', json=payload, headers=existing).status_code == 404
    assert client.post(root+'/invitations', json={**payload, 'role':'owner'}, headers=owner).status_code == 422
    with patch('app.institution_staff.enabled', return_value=True):
        issued = client.post(root+'/invitations', json=payload, headers=owner)
        assert issued.status_code == 201, issued.text
        invitation = issued.json()
        token = invitation['invitation_token']
        assert token not in client.get(root, headers=owner).text
        assert client.post(root+'/invitations', json=payload, headers=owner).status_code == 409
        with SessionLocal.begin() as db:
            row = db.get(StaffInvitation, invitation['id'])
            assert row.token_hash == token_digest(token)
            row.expires_at = utcnow() - timedelta(minutes=1)
        assert client.post(preview, json={'token':token}).status_code == 404
        resent = client.post(root+f'/invitations/{invitation["id"]}/resend', headers=owner).json()
        assert resent['invitation_token'] != token
        token = resent['invitation_token']
    assert client.post(preview, json={'token':token}).json()['role'] == 'loan_officer'
    assert client.post(activate, json={'token':token,'full_name':'Ali','password':'eight123'}).status_code == 201
    assert client.post(activate, json={'token':token,'full_name':'Ali','password':'eight123'}).status_code == 404
    logged_in = client.post('/auth/institution/login', json={'email':invited_email,'password':'eight123'}).json()
    staff = {'Authorization': 'Bearer '+logged_in['access_token']}
    staff_id = client.get('/auth/me', headers=staff).json()['id']
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

    existing_payload = {**payload,'email':'existing-bank-staff@example.com','role':'viewer'}
    first = client.post(root+'/invitations',json=existing_payload,headers=owner).json()
    assert 'invitation_token' not in first
    assert client.post(root+f'/invitations/{first["id"]}/cancel',headers=owner).status_code == 200
    inbox = '/auth/institution/staff-invitations'
    assert client.get(inbox,headers=existing).json() == []
    second = client.post(root+'/invitations',json=existing_payload,headers=owner).json()
    assert client.post(inbox+f'/{second["id"]}/respond',json={'decision':'accept'},headers=staff).status_code == 404
    assert client.post(inbox+f'/{second["id"]}/respond',json={'decision':'accept'},headers=existing).status_code == 200
    assert client.get('/finance/institutions/mine',headers=existing).json()[0]['role'] == 'viewer'
    assert client.get(root,headers=owner).json()['activity']
    assert client.get('/auth/me',headers=login('farmer','existing-bank-staff@example.com')).status_code == 200
