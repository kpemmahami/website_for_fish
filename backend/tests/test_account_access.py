"""Account separation and administrator provisioning regression coverage."""
import json

import pytest
from sqlalchemy import select

from .test_api import client
from app.administration import AdminSetup, bootstrap_admin
from app.main import AuditLog, Register, SessionLocal, User, new_user

PASSWORD = 'a-very-long-password-123'
ADMIN_EMAIL = 'bootstrap-admin@example.com'


def credentials(email):
    return {'full_name': 'Test Account', 'email': email, 'password': PASSWORD}


def login(portal, email):
    response = client.post(f'/auth/{portal}/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize(('portal', 'phone', 'identifiers'), [
    ('farmer', '+233241234567', ('0241234567', '233241234567', '+233 24 123 4567')),
    ('institution', '+442079460123', ('+44 (20) 7946-0123',)),
    ('admin', '+233201234567', ('0201234567',)),
])
def test_sign_in_by_email_or_registered_phone(portal, phone, identifiers):
    email = f'phone-login-{portal}@example.com'
    with SessionLocal.begin() as db:
        user = new_user(Register(**credentials(email)), portal)
        user.phone_number = phone
        db.add(user)
        db.flush()
        user_id = user.id
    for identifier in (*identifiers, phone, email):
        assert client.get('/auth/me', headers=login(portal, identifier)).json()['id'] == user_id
    assert client.post(f'/auth/{portal}/login', json={'email': phone, 'password': 'incorrect'}).status_code == 401
    wrong_portal = 'farmer' if portal != 'farmer' else 'institution'
    assert client.post(f'/auth/{wrong_portal}/login', json={'email': phone, 'password': PASSWORD}).status_code == 401


def test_duplicate_phone_requires_email_login():
    phone = '+233261234567'
    emails = ['duplicate-phone-first@example.com', 'duplicate-phone-second@example.com']
    with SessionLocal.begin() as db:
        for email in emails:
            user = new_user(Register(**credentials(email)), 'farmer')
            user.phone_number = phone
            db.add(user)
    response = client.post('/auth/farmer/login', json={'email': phone, 'password': PASSWORD})
    assert response.status_code == 401
    assert client.get('/auth/me', headers=login('farmer', emails[0])).json()['email'] == emails[0]


def admin_headers():
    with SessionLocal() as db:
        if db.get(AdminSetup, 1) is None:
            bootstrap_admin(Register(**credentials(ADMIN_EMAIL)), db)
    return login('admin', ADMIN_EMAIL)


def register_institution(email, institution):
    response = client.post('/finance/admin/institutions', headers=admin_headers(), json={
        **credentials(email), 'institution': institution,
    })
    assert response.status_code == 201, response.text
    return login('institution', email), response


def test_account_boundaries_and_institution_rejection(monkeypatch):
    email = 'access-farmer@example.com'
    monkeypatch.setenv('AQUAFARM_PLATFORM_ADMIN_EMAIL', email)
    registration = client.post('/auth/farmer/register', json={**credentials(email), 'account_type': 'admin'})
    assert registration.status_code == 422
    registration = client.post('/auth/farmer/register', json=credentials(email))
    assert registration.status_code == 201
    assert registration.json()['is_platform_admin'] is False
    farmer = login('farmer', email)
    assert client.post('/auth/admin/login', json={'email': email, 'password': PASSWORD}).status_code == 401
    assert client.get('/finance/admin/institutions/pending', headers=farmer).status_code == 403
    assert client.post('/auth/admin/invitations', headers=farmer, json={'email': 'abc@example.com'}).status_code == 404

    institution = {'name': 'Pending Test Bank', 'institution_type': 'bank', 'account_number': 'TEST-001'}
    payload = {**credentials('unapproved-institution@example.com'), 'institution': institution}
    assert client.post('/auth/institution/register', json=payload).status_code == 404
    assert client.post('/finance/institutions', json=payload).status_code == 405
    assert client.post('/finance/admin/institutions', json=payload).status_code == 401
    assert client.post('/finance/admin/institutions', headers=farmer, json=payload).status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == payload['email'])) is None
    lender_email = 'access-lender@example.com'
    lender, response = register_institution(lender_email, institution)
    assert client.post('/finance/admin/institutions', headers=admin_headers(), json={
        **credentials(lender_email), 'institution': institution,
    }).status_code == 409
    institution_id = response.json()['id']
    base = f'/finance/institutions/{institution_id}'
    assert client.post('/auth/farmer/login', json={'email': lender_email, 'password': PASSWORD}).status_code == 401
    assert client.post('/farms', headers=lender, json={
        'name': 'Example Farm', 'region': 'Northern', 'district': 'Tamale',
        'farm_type': 'pond', 'species': 'Tilapia',
    }).status_code == 403
    assert client.get(f'{base}/applications', headers=lender).status_code == 404
    assert client.post(f'{base}/verify', headers=lender).status_code == 403
    admin = admin_headers()
    queue = client.get('/finance/admin/institutions/pending', headers=admin).json()
    assert institution_id in {row['id'] for row in queue}
    assert client.post(f'{base}/reject', headers=admin, json={'reason': 'Registration could not be verified'}).json()['status'] == 'rejected'
    assert client.post(f'{base}/verify', headers=admin).status_code == 409
    assert client.get(f'{base}/loans', headers=lender).status_code == 404
    with SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(
            AuditLog.entity_type == 'finance_institution',
            AuditLog.entity_id == institution_id, AuditLog.action == 'reject',
        ))
        assert json.loads(log.details)['reason'] == 'Registration could not be verified'


def test_admin_bootstrap_and_closed_public_provisioning():
    admin = admin_headers()
    email = 'unprovisioned-admin@example.com'
    for headers in ({}, admin):
        assert client.post('/auth/admin/invitations', headers=headers, json={'email': email}).status_code == 404
        for path in ('/auth/admin/accept-invitation', '/auth/admin/register', '/auth/platform-owner/register'):
            payload = {**credentials(email), 'invitation_token': 'A' * 43}
            assert client.post(path, headers=headers, json=payload).status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == email)) is None
        with pytest.raises(ValueError, match='already been completed'):
            bootstrap_admin(Register(**credentials('second-bootstrap@example.com')), db)
    assert client.get('/auth/me', headers=admin).json()['is_platform_owner'] is True


def test_institution_registration_rolls_back_partial_provisioning(monkeypatch):
    from sqlalchemy.exc import IntegrityError

    from app import lending

    create = lending.add_institution

    def fail_after_institution_creation(data, user, db):
        create(data, user, db)
        db.flush()
        raise IntegrityError('test insert', {}, RuntimeError('simulated constraint failure'))

    monkeypatch.setattr(lending, 'add_institution', fail_after_institution_creation)
    email = 'rollback-institution@example.com'
    name = 'Rollback Test Bank'
    response = client.post('/finance/admin/institutions', headers=admin_headers(), json={
        **credentials(email),
        'institution': {'name': name, 'institution_type': 'bank', 'account_number': 'TEST-ROLLBACK'},
    })
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == email)) is None
        assert db.scalar(select(lending.Institution.id).where(lending.Institution.name == name)) is None


def test_institution_review_and_suspension():
    lender, registered = register_institution('review-lender@example.com', {
        'name': 'Review Test Bank', 'institution_type': 'bank', 'account_number': 'TEST-REVIEW',
    })
    institution_id = registered.json()['id']
    admin = admin_headers()
    path = f'/finance/admin/institutions/{institution_id}/status'
    loans = f'/finance/institutions/{institution_id}/loans'
    assert client.post(path, headers=lender, json={'status': 'verified', 'reason': 'Self approval'}).status_code == 403
    for status, access in [('under_review', 404), ('more_info_required', 404), ('verified', 200), ('suspended', 404), ('verified', 200)]:
        response = client.post(path, headers=admin, json={'status': status, 'reason': 'Review test'})
        assert response.status_code == 200, response.text
        assert client.get(loans, headers=lender).status_code == access
    with SessionLocal() as db:
        changes = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == 'finance_institution',
            AuditLog.entity_id == institution_id,
            AuditLog.action == 'change_status',
        )).all()
        assert len(changes) == 5

@pytest.mark.parametrize('name', ['Ali', 'John Doe', "Anne-Marie O'Neill", 'Emmanuel Awuni', 'A'])
def test_registration_accepts_legitimate_names_and_eight_character_password(name):
    data = Register(full_name=f' {name} ', email='validation@example.com', password='Eight!12')
    assert data.full_name == name
    assert Register.model_validate({**data.model_dump(), 'password': 'longer password!'}).password == 'longer password!'
    from pydantic import ValidationError
    from app.main import AdminRegister

    with pytest.raises(ValidationError):
        Register.model_validate({**data.model_dump(), 'password': '1234567'})
    with pytest.raises(ValidationError):
        AdminRegister.model_validate(data.model_dump())


def test_local_aliases_unavailable_on_ordinary_database():
    assert client.post('/auth/admin/login', json={'email': 'admin', 'password': 'user1234'}).status_code == 401
