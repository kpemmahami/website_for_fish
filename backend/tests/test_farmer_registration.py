import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from .test_api import client
from app.main import SessionLocal, User, app, configure_cors, get_db, password_hash
from app.processing import ProcessingBusiness

PATH = '/auth/farmer/register'
PASSWORD = 'Example-Registration-Password'
FRONTEND = 'https://frontend.example.invalid'


def test_registration_persists_farmer_and_processing_business():
    with SessionLocal() as db:
        dialect = db.bind.dialect.name
    for business_type, phone in zip(('farmer', 'processor', 'integrated'), ('0245550121', '+233245550122', '233245550123')):
        email = f'registration-{business_type}-{dialect}@example.com'
        body = {'full_name': 'New account', 'email': email, 'password': PASSWORD, 'phone_number': phone, 'business_type': business_type}
        result = client.post(PATH, json=body)
        assert result.status_code == 201, result.text
        user = result.json()
        assert user['phone_number'].startswith('+233')
        assert user['account_type'] == 'pending_farmer' and user['is_platform_admin'] is False
        assert 'password' not in user and 'password_hash' not in user
        with SessionLocal() as db:
            stored = db.get(User, user['id'])
            assert stored.email == email and stored.password_hash != PASSWORD
            assert password_hash.verify(PASSWORD, stored.password_hash)
            business = db.scalar(select(ProcessingBusiness).where(ProcessingBusiness.owner_id == stored.id))
            assert (business.business_type if business else 'farmer') == business_type
        login = client.post('/auth/farmer/login', json={'email': email, 'password': PASSWORD})
        assert login.status_code == 200
        duplicate = client.post(PATH, json={**body, 'email': email.upper()})
        assert duplicate.status_code == 409
        assert duplicate.json() == {'detail': 'Email already registered'}


def test_registration_validation_does_not_echo_sensitive_input():
    data = {'full_name':'Account', 'email':'validation-test@example.com', 'password':PASSWORD, 'phone_number':'0245550108'}
    invalid = (
        ({'password': PASSWORD}, 'email'),
        ({key: value for key, value in data.items() if key != 'phone_number'}, 'phone_number'),
        ({**data, 'phone_number': '123'}, 'phone_number'),
        ({**data, 'business_type':'admin'}, 'business_type'),
        ({**data, 'password':'short'}, 'password'),
        ({**data, 'account_type':'admin'}, 'account_type'),
    )
    for payload, field in invalid:
        response = client.post(PATH, json=payload)
        assert response.status_code == 422
        assert any(field in item['loc'] for item in response.json()['detail'])
        assert all(set(item) == {'loc','type'} for item in response.json()['detail'])
        assert PASSWORD not in response.text


def test_registration_rolls_back_and_reports_database_error_safely(monkeypatch, caplog):
    email = 'registration-rollback@example.com'
    with SessionLocal() as db:
        def fail():
            raise OperationalError('private query', {'secret': PASSWORD}, RuntimeError('private URI'))

        monkeypatch.setattr(db, 'commit', fail)
        app.dependency_overrides[get_db] = lambda: db
        try:
            response = client.post(PATH, json={'full_name':'Account','email':email,
                                               'password':PASSWORD,'phone_number':'0245550109','business_type':'integrated'})
        finally:
            app.dependency_overrides.pop(get_db)
        assert response.status_code == 503
        assert response.json() == {'detail':'Registration is temporarily unavailable'}
        assert 'private URI' not in caplog.text and PASSWORD not in caplog.text
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == email)) is None


def test_cors_allows_only_configured_origins():
    wrapper = FastAPI()
    wrapper.mount('/', app)
    configure_cors(wrapper, FRONTEND + '/')
    cors = TestClient(wrapper)
    headers = {'Origin':FRONTEND,'Access-Control-Request-Method':'POST',
               'Access-Control-Request-Headers':'content-type,authorization'}
    allowed = cors.options(PATH, headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers['Access-Control-Allow-Origin'] == FRONTEND
    refused = cors.options(PATH, headers={**headers, 'Origin':'https://unlisted.example.invalid'})
    assert refused.status_code == 400
    assert 'Access-Control-Allow-Origin' not in refused.headers
    invalid = cors.post(PATH, json={}, headers={'Origin':FRONTEND})
    assert invalid.status_code == 422
    assert invalid.headers['Access-Control-Allow-Origin'] == FRONTEND

def test_readiness_verifies_registration_schema_without_exposing_details(monkeypatch, caplog):
    assert client.get('/ready').json() == {'status': 'ok'}
    with SessionLocal() as db:
        def fail(*args, **kwargs):
            raise OperationalError('private query', {}, RuntimeError('connection refused while using private URI'))

        monkeypatch.setattr(db, 'execute', fail)
        app.dependency_overrides[get_db] = lambda: db
        try:
            result = client.get('/ready')
        finally:
            app.dependency_overrides.pop(get_db)
        assert result.status_code == 503
        assert result.json() == {'detail': 'Service is temporarily unavailable'}
        assert 'reason=database_network_unreachable' in caplog.text
        assert 'private URI' not in caplog.text

def test_deployed_frontend_preflight_on_actual_application():
    origin = 'https://aquafarm-ghana-frontend.onrender.com'
    headers = {'Origin': origin, 'Access-Control-Request-Method': 'POST',
               'Access-Control-Request-Headers': 'content-type,authorization'}
    preflight = client.options(PATH, headers=headers)
    assert preflight.status_code == 200
    assert preflight.headers['Access-Control-Allow-Origin'] == origin
    assert 'POST' in preflight.headers['Access-Control-Allow-Methods']
    assert {'content-type', 'authorization'} <= {
        item.strip() for item in preflight.headers['Access-Control-Allow-Headers'].lower().split(',')
    }
    assert 'access-control-allow-credentials' not in preflight.headers
    assert 'x-request-id' not in preflight.headers
    denied = client.options(PATH, headers={**headers, 'Origin': origin + '.example.invalid'})
    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers
    if os.getenv('RENDER', '').lower() != 'true':
        local = client.options(PATH, headers={**headers, 'Origin': 'http://localhost:5173'})
        assert local.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'
