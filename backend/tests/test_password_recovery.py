from datetime import datetime, timedelta, timezone

import jwt
import pytest

from .test_api import client
from app import password_recovery
from app.main import SECRET_KEY, Register, SessionLocal, new_user, password_binding


@pytest.mark.parametrize('portal', ['farmer', 'institution', 'admin'])
def test_password_recovery(portal, monkeypatch):
    email = f'recover-{portal}@example.com'
    old_password = 'Original account password'
    new_password = 'Replacement account password'
    login_path = f'/auth/{portal}/login'
    request_path = '/auth/password-recovery/request'
    reset_path = '/auth/password-recovery/reset'
    deliveries = []
    monkeypatch.setattr(password_recovery, 'recovery_mail_settings', lambda: ('smtp.invalid', 'test@example.com', 'https://example.com'))
    monkeypatch.setattr(password_recovery, 'send_recovery_email', lambda *args: deliveries.append(args))
    with SessionLocal.begin() as db:
        user = new_user(Register(full_name='Recovery Test', email=email, password=old_password), portal)
        db.add(user)
        db.flush()
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        legacy = jwt.encode({'sub': str(user.id), 'exp': expires}, SECRET_KEY, algorithm='HS256')
        expired = jwt.encode({
            'sub': str(user.id), 'purpose': password_recovery.PURPOSE,
            'binding': password_binding(user, password_recovery.PURPOSE),
            'iat': datetime.now(timezone.utc) - timedelta(minutes=16),
            'exp': datetime.now(timezone.utc) - timedelta(minutes=1),
        }, SECRET_KEY, algorithm='HS256')
    session = client.post(login_path, json={'email': email, 'password': old_password}).json()['access_token']
    legacy_headers = {'Authorization': f'Bearer {legacy}'}
    assert client.get('/auth/me', headers=legacy_headers).status_code == 200
    request = {'email': email, 'portal': portal}
    response = client.post(request_path, json=request)
    assert response.status_code == 202
    assert client.post(request_path, json={**request, 'email': 'unknown@example.com'}).json() == response.json()
    assert client.post(request_path, json=request).json() == response.json()
    assert len(deliveries) == 1
    token = deliveries[0][2]
    assert token not in response.text
    assert client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401
    assert client.post(reset_path, json={'token': expired, 'password': new_password}).status_code == 400
    assert client.post(reset_path, json={'token': session, 'password': new_password}).status_code == 400
    reset = {'token': token, 'password': new_password}
    assert client.post(reset_path, json=reset).status_code == 200
    assert client.post(reset_path, json=reset).status_code == 400
    assert client.get('/auth/me', headers=legacy_headers).status_code == 401
    assert client.get('/auth/me', headers={'Authorization': f'Bearer {session}'}).status_code == 401
    assert client.post(login_path, json={'email': email, 'password': old_password}).status_code == 401
    assert client.post(login_path, json={'email': email, 'password': new_password}).status_code == 200
