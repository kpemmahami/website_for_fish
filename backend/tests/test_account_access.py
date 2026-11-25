"""Account separation and administrator provisioning regression coverage."""
import json

import pytest
from sqlalchemy import select

from .test_api import client, next_test_phone
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
            bootstrap_admin(Register(**credentials(ADMIN_EMAIL)), db, phone_number='0271234567')
    return login('admin', ADMIN_EMAIL)


def register_institution(email, institution):
    response = client.post('/finance/admin/institutions', headers=admin_headers(), json={
        **credentials(email), 'phone_number': next_test_phone(), 'institution': institution,
    })
    assert response.status_code == 201, response.text
    return complete_initial_password(email, PASSWORD), response


def complete_initial_password(email, initial_password):
    from datetime import timedelta
    from unittest.mock import patch

    from app.phone_verification import AccountPhoneChallenge

    path = '/auth/institution/login'
    credentials_in = {'email': email, 'password': initial_password}
    first = client.post(path, json=credentials_in)
    assert first.status_code == 200, first.text
    challenge = first.json()
    assert 'access_token' not in challenge
    token = challenge['initial_password_token']
    assert client.get('/finance/institutions/mine', headers={'Authorization': f'Bearer {token}'}).status_code == 401
    setup_path = '/auth/institution/initial-password'
    password = 'a-private-institution-password-741'
    changed = {'token': token, 'password': password, 'code': '111111'}
    assert client.post(setup_path, json=changed).status_code == 400
    with patch('app.phone_verification.hubtel_send_sms') as send_sms:
        sent = client.post(f'{setup_path}/verification', json={'token': token})
        assert sent.status_code == 200
        phone, message = send_sms.call_args.args
        assert sent.json() == {'destination': '•••' + phone[-4:]}
        assert client.post(f'{setup_path}/verification', json={'token': token}).status_code == 429
        assert send_sms.call_count == 1
    code = message.split(': ')[1].split('.')[0]
    if len(initial_password) >= 12:
        assert client.post(setup_path, json={**changed, 'password': initial_password, 'code': code}).status_code == 422
    wrong = '999999' if code != '999999' else '000000'
    assert client.post(setup_path, json={**changed, 'code': wrong}).status_code == 400
    changed['code'] = code
    assert client.post(setup_path, json=changed).status_code == 200
    assert client.post(setup_path, json=changed).status_code == 400
    assert client.post(path, json=credentials_in).status_code == 401
    login_response = client.post(path, json={**credentials_in, 'password': password})
    assert login_response.status_code == 200, login_response.text
    login_challenge = login_response.json()
    assert 'access_token' not in login_challenge
    mfa_token = login_challenge['institution_mfa_token']
    assert client.get('/finance/institutions/mine',
                      headers={'Authorization': f'Bearer {mfa_token}'}).status_code == 401
    with SessionLocal.begin() as db:
        challenge = db.scalar(select(AccountPhoneChallenge).join(User).where(User.email == email))
        challenge.sent_at -= timedelta(minutes=3)
    with patch('app.phone_verification.hubtel_send_sms') as send_sms:
        assert client.post('/auth/institution/mfa/request', json={'token': token}).status_code == 400
        assert client.post('/auth/institution/mfa/request', json={'token': mfa_token}).status_code == 200
        code = send_sms.call_args.args[1].split(': ')[1].split('.')[0]
    confirm_path = '/auth/institution/mfa/confirm'
    wrong = '000000' if code != '000000' else '999999'
    assert client.post(confirm_path, json={'token': mfa_token, 'code': wrong}).status_code == 400
    confirmed = client.post(confirm_path, json={'token': mfa_token, 'code': code})
    assert confirmed.status_code == 200
    assert client.post(confirm_path, json={'token': mfa_token, 'code': code}).status_code == 400
    headers = {'Authorization': f"Bearer {confirmed.json()['access_token']}"}
    assert client.get('/auth/me', headers=headers).json()['phone_verified_at']
    return headers


def test_account_boundaries_and_institution_rejection(monkeypatch):
    email = 'access-farmer@example.com'
    monkeypatch.setenv('AQUAFARM_PLATFORM_ADMIN_EMAIL', email)
    registration = client.post('/auth/farmer/register', json={**credentials(email), 'account_type': 'admin'})
    assert registration.status_code == 422
    registration = client.post('/auth/farmer/register', json={**credentials(email), 'phone_number': '0245550107'})
    assert registration.status_code == 201
    assert registration.json()['is_platform_admin'] is False
    farmer = login('farmer', email)
    assert client.post('/auth/admin/login', json={'email': email, 'password': PASSWORD}).status_code == 401
    assert client.get('/finance/admin/institutions/pending', headers=farmer).status_code == 403
    assert client.get('/auth/me', headers=farmer).json()['account_type'] == 'pending_farmer'
    assert client.get('/farms', headers=farmer).status_code == 403
    assert client.get('/processing/business', headers=farmer).status_code == 403
    approval_path = f"/admin/farmers/{registration.json()['id']}/approve"
    assert client.post(approval_path, headers=farmer).status_code == 403
    admin = admin_headers()
    assert registration.json()['id'] in {
        row['id'] for row in client.get('/admin/farmers/pending', headers=admin).json()['items']
    }
    assert client.post(approval_path, headers=admin).status_code == 200
    approved_path = '/admin/farmers/approved'
    assert client.get(approved_path, headers=farmer).status_code == 403
    assert registration.json()['id'] in {
        row['id'] for row in client.get(approved_path, headers=admin).json()['items']
    }
    assert registration.json()['id'] not in {
        row['id'] for row in client.get('/admin/farmers/pending', headers=admin).json()['items']
    }
    assert client.post(approval_path, headers=admin).status_code == 404
    assert client.get('/auth/me', headers=farmer).json()['account_type'] == 'farmer'
    assert client.get('/farms', headers=farmer).status_code == 200
    assert client.post('/auth/admin/invitations', headers=farmer, json={'email': 'abc@example.com'}).status_code == 404

    institution = {'name': 'Pending Test Bank', 'institution_type': 'bank', 'account_number': 'TEST-001'}
    payload = {**credentials('unapproved-institution@example.com'), 'phone_number': next_test_phone(), 'institution': institution}
    assert client.post('/auth/institution/register', json=payload).status_code == 404
    assert client.post('/finance/institutions', json=payload).status_code == 405
    assert client.post('/finance/admin/institutions', json=payload).status_code == 401
    assert client.post('/finance/admin/institutions', headers=farmer, json=payload).status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == payload['email'])) is None
    lender_email = 'access-lender@example.com'
    lender, response = register_institution(lender_email, institution)
    assert client.post('/finance/admin/institutions', headers=admin_headers(), json={
        **credentials(lender_email), 'phone_number': next_test_phone(), 'institution': institution,
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
            bootstrap_admin(Register(**credentials('second-bootstrap@example.com')), db, phone_number='0281234567')
    assert client.get('/auth/me', headers=admin).json()['is_platform_owner'] is True


def test_administrator_directory_is_owner_only():
    owner = admin_headers()
    email = 'directory-admin@example.com'
    with SessionLocal.begin() as db:
        db.add(new_user(Register(**credentials(email)), 'admin'))
    path = '/admin/administrators'
    assert client.get(path).status_code == 401
    assert client.get(path, headers=login('admin', email)).status_code == 403
    match = client.get(path, headers=owner, params={'search': 'DIRECTORY-ADMIN'}).json()
    assert match['total'] == 1
    assert match['items'][0]['role'] == 'Super Admin'
    assert match['items'][0]['email'] == email
    assert 'password_hash' not in match['items'][0]
    assert client.get(path, headers=owner, params={'search': '%'}).json()['total'] == 0
    owner_row = client.get(path, headers=owner, params={'search': ADMIN_EMAIL, 'limit': 1}).json()['items'][0]
    assert owner_row['role'] == 'Platform Owner'
    assert owner_row['phone_number'] == '+233271234567'


def test_only_owner_can_prepare_an_administrator_without_granting_access(monkeypatch):
    import base64
    import hmac
    from datetime import datetime, timezone
    from urllib.parse import parse_qs

    from app import administrator_verification as verification

    class TestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(1_800_000_015, tz)

    monkeypatch.setattr(verification, 'datetime', TestClock)
    monkeypatch.setenv('AQUAFARM_ADMIN_AUTHENTICATOR_KEY', 'fictional-authenticator-key-for-tests')

    owner = admin_headers()
    ordinary_email = 'normal-preparation-admin@example.com'
    with SessionLocal.begin() as db:
        db.add(new_user(Register(**credentials(ordinary_email)), 'admin'))
    payload = {'email': 'pending-preparation@example.com', 'full_name': 'Pending Admin',
               'phone_number': '0541234567'}
    path = '/admin/administrators'
    assert client.post(path, json=payload).status_code == 401
    assert client.post(path, headers=login('admin', ordinary_email), json=payload).status_code == 403
    assert client.post(path, headers=owner, json={**payload, 'role': 'owner'}).status_code == 422
    created = client.post(path, headers=owner, json=payload)
    assert created.status_code == 201
    account_id = created.json()['id']
    row = client.get(path, headers=owner, params={'search': payload['email']}).json()['items'][0]
    assert row['pending_activation'] is True
    assert row['phone_number'] == '+233541234567'
    assert client.post(path, headers=owner, json={**payload, 'email': 'other-pending@example.com',
                                                 'phone_number': '+233541234567'}).status_code == 409
    assert client.post(f'{path}/{account_id}/access', headers=owner,
                       json={'action': 'reactivate', 'reason': 'Test'}).status_code == 404
    assert client.post('/auth/admin/login', json={'email': payload['email'],
                                                 'password': PASSWORD}).status_code == 401
    emails, messages = [], []
    monkeypatch.setattr(verification, 'recovery_mail_settings', lambda: ('mock', 'test@example.com', 'https://example.com'))
    monkeypatch.setattr(verification, 'send_account_email', lambda *args: emails.append(args) or True)
    monkeypatch.setattr(verification, 'hubtel_send_sms', lambda *args: messages.append(args))
    send_path = f'{path}/{account_id}/contact-verification'
    assert client.post(send_path, headers=login('admin', ordinary_email)).status_code == 403
    assert client.post(send_path, headers=owner).status_code == 200
    assert client.post(send_path, headers=owner).status_code == 429
    assert emails[0][1] == payload['email']
    assert messages[0][0] == '+233541234567'
    contact_token = parse_qs(emails[0][-1])['administrator-contact'][0]
    code = messages[0][1].split(': ')[1].split('.')[0]
    verify_path = '/auth/admin/contact-verification'
    assert client.post(verify_path, json={'token': contact_token, 'code': '999999' if code != '999999' else '000000'}).status_code == 400
    verified = client.post(verify_path, json={'token': contact_token, 'code': code})
    assert verified.status_code == 200
    assert client.post(verify_path, json={'token': contact_token, 'code': code}).status_code == 400
    row = client.get(path, headers=owner, params={'search': payload['email']}).json()['items'][0]
    assert row['pending_activation'] and row['contacts_verified_at']
    enrollment = verified.json()
    key = base64.b32decode(enrollment['setup_key'])

    def totp(step):
        value = hmac.digest(key, step.to_bytes(8, 'big'), 'sha1')
        offset = value[-1] & 15
        return f'{(int.from_bytes(value[offset:offset + 4], "big") & 0x7fffffff) % 1_000_000:06d}'

    current = int(TestClock.now(timezone.utc).timestamp()) // 30
    activation = {'token': enrollment['enrollment_token'], 'code': totp(current - 1), 'password': PASSWORD}
    assert client.post('/auth/admin/activate', json=activation).status_code == 200
    assert client.post('/auth/admin/activate', json=activation).status_code == 400
    credentials_in = {'email': payload['email'], 'password': PASSWORD}
    assert client.post('/auth/admin/login', json=credentials_in).status_code == 428
    with_code = {**credentials_in, 'authenticator_code': totp(current)}
    assert client.post('/auth/admin/login', json=with_code).status_code == 200
    assert client.post('/auth/admin/login', json=with_code).status_code == 401


def test_existing_administrator_enrollment_revokes_old_sessions(monkeypatch):
    from urllib.parse import parse_qs

    from app import administrator_verification as verification

    email = 'existing-mfa-enrollment@example.com'
    phone = next_test_phone()
    with SessionLocal.begin() as db:
        user = new_user(Register(**credentials(email)), 'admin')
        user.phone_number = phone
        db.add(user)

    logged_in = login('admin', email)
    route = '/auth/admin/authenticator-enrollment'
    assert client.post(route, headers=logged_in, json={'password': 'incorrect'}).status_code == 403
    emails, messages = [], []
    monkeypatch.setenv('AQUAFARM_ADMIN_AUTHENTICATOR_KEY', 'fictional-authenticator-key-for-tests')
    monkeypatch.setattr(verification, 'recovery_mail_settings', lambda: ('mock', 'test@example.com', 'https://example.com'))
    monkeypatch.setattr(verification, 'send_account_email', lambda *args: emails.append(args) or True)
    monkeypatch.setattr(verification, 'hubtel_send_sms', lambda *args: messages.append(args))
    assert client.post(route, headers=logged_in, json={'password': PASSWORD}).status_code == 200
    assert client.get('/auth/me', headers=logged_in).json()['authenticator_enrolled'] is False
    login('admin', email)
    assert emails[0][1] == email and messages[0][0] == phone
    token = parse_qs(emails[0][-1])['administrator-contact'][0]
    code = messages[0][1].split(': ')[1].split('.')[0]
    proof = client.post('/auth/admin/contact-verification', json={'token': token, 'code': code}).json()
    assert proof['existing_account'] is True
    monkeypatch.setattr(verification, 'matching_step', lambda *args: 100)
    private_password = 'Replacement administrator password'
    assert client.post('/auth/admin/activate', json={
        'token': proof['enrollment_token'], 'password': private_password, 'code': '654321',
    }).status_code == 200
    assert client.get('/auth/me', headers=logged_in).status_code == 401
    sign_in = {'email': email, 'password': private_password}
    assert client.post('/auth/admin/login', json=sign_in).status_code == 428
    monkeypatch.setattr(verification, 'matching_step', lambda *args: 101)
    session = client.post('/auth/admin/login', json={**sign_in, 'authenticator_code': '123456'}).json()
    headers = {'Authorization': f"Bearer {session['access_token']}"}
    profile = client.get('/auth/me', headers=headers).json()
    assert profile['authenticator_enrolled'] and profile['account_type'] == 'admin'
    assert client.post(route, headers=headers, json={'password': private_password}).status_code == 409

    recovery_route = '/auth/admin/recovery-codes'
    recovery_request = {'password': private_password, 'authenticator_code': '123456'}
    assert client.post(recovery_route, json=recovery_request).status_code == 401
    assert client.post(recovery_route, headers=headers,
                       json={**recovery_request, 'password': 'incorrect'}).status_code == 403
    monkeypatch.setattr(verification, 'matching_step', lambda *args: 102)
    generated = client.post(recovery_route, headers=headers, json=recovery_request)
    assert generated.status_code == 200
    assert generated.headers['Cache-Control'] == 'no-store'
    codes = generated.json()['codes']
    assert len(codes) == len(set(codes)) == 8
    recovery_login = {**sign_in, 'recovery_code': codes[0].lower()}
    assert client.post('/auth/admin/login', json={**recovery_login, 'password': 'incorrect'}).status_code == 401
    assert client.post('/auth/admin/login', json=recovery_login).status_code == 200
    assert client.post('/auth/admin/login', json=recovery_login).status_code == 401
    monkeypatch.setattr(verification, 'matching_step', lambda *args: 103)
    assert client.post(recovery_route, headers=headers, json=recovery_request).status_code == 200
    assert client.post('/auth/admin/login', json={**sign_in, 'recovery_code': codes[1]}).status_code == 401


def test_owner_controls_administrator_access_and_invalidates_sessions():
    owner = admin_headers()
    email = 'managed-administrator@example.com'
    with SessionLocal.begin() as db:
        account = new_user(Register(**credentials(email)), 'admin')
        db.add(account)
        db.flush()
        account_id = account.id
    path = f'/admin/administrators/{account_id}/access'
    original = login('admin', email)
    suspend = {'action': 'suspend', 'reason': 'Access review'}
    assert client.post(path, headers=original, json=suspend).status_code == 403
    owner_id = client.get('/auth/me', headers=owner).json()['id']
    assert client.post(f'/admin/administrators/{owner_id}/access', headers=owner, json=suspend).status_code == 403
    assert client.post(path, headers=owner, json={**suspend, 'reason': ' '}).status_code == 422
    assert client.post(path, headers=owner, json={**suspend, 'action': 'revoke_sessions'}).status_code == 200
    assert client.get('/auth/me', headers=original).status_code == 401
    before_suspension = login('admin', email)
    assert client.post(path, headers=owner, json=suspend).status_code == 200
    assert client.post(path, headers=owner, json=suspend).status_code == 409
    assert client.get('/auth/me', headers=before_suspension).status_code == 401
    assert client.post('/auth/admin/login', json={'email': email, 'password': PASSWORD}).status_code == 401
    assert client.post(path, headers=owner, json={**suspend, 'action': 'reactivate'}).status_code == 200
    assert client.get('/auth/me', headers=before_suspension).status_code == 401
    assert client.get('/auth/me', headers=login('admin', email)).status_code == 200
    activity_path = f'/admin/administrators/{account_id}/activity'
    assert client.get(activity_path, headers=login('admin', email)).status_code == 403
    activity = client.get(activity_path, headers=owner).json()
    assert [event['action'] for event in activity['items']] == ['reactivate', 'suspend', 'revoke_sessions']
    assert all(event['reason'] == 'Access review' for event in activity['items'])
    assert client.get(activity_path, headers=owner, params={'offset': 3}).json()['items'] == []
    with SessionLocal() as db:
        logs = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == 'platform_admin', AuditLog.entity_id == account_id,
        ).order_by(AuditLog.id)).all()
        assert [entry.action for entry in logs] == ['revoke_sessions', 'suspend', 'reactivate']
        assert all(entry.actor_id == owner_id for entry in logs)


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
        **credentials(email), 'phone_number': next_test_phone(),
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
    history = f'/finance/admin/institutions/history?institution_id={institution_id}'
    assert client.get(history).status_code == 401
    assert client.get(history, headers=lender).status_code == 403
    response = client.get(history, headers=admin)
    assert response.status_code == 200, response.text
    latest = response.json()['items'][0]
    assert latest['institution'] == 'Review Test Bank'
    assert latest['previous_status'] == 'suspended'
    assert latest['status'] == 'verified'
    assert latest['reason'] == 'Review test'
    assert latest['actor']
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
