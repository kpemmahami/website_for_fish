from datetime import timedelta

from .test_api import approve_test_registration, client, next_test_phone
from app import phone_verification
from app.main import SessionLocal


def test_saved_phone_verification_and_replacement(monkeypatch):
    phone = next_test_phone()
    email = 'verified-phone@example.com'
    password = 'private-test-password-202'
    registration = client.post('/auth/farmer/register', json={
        'email': email, 'password': password, 'full_name': 'Test Account', 'phone_number': phone,
    })
    assert registration.status_code == 201
    token = client.post('/auth/farmer/login', json={'email': email, 'password': password}).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    messages = []
    monkeypatch.setattr(phone_verification, 'hubtel_send_sms', lambda *args: messages.append(args))
    request = '/auth/me/phone-verification/request'
    confirm = '/auth/me/phone-verification/confirm'
    assert client.post(request).status_code == 401
    response = client.post(request, headers=headers)
    assert response.json() == {'verified': False, 'destination': '•••' + phone[-4:]}
    assert client.post(request, headers=headers).status_code == 429
    assert messages[0][0] == phone
    code = messages[0][1].split(': ')[1].split('.')[0]
    wrong = '999999' if code != '999999' else '000000'
    assert client.post(confirm, headers=headers, json={'code': wrong}).status_code == 400
    assert client.post(confirm, headers=headers, json={'code': code}).status_code == 200
    assert client.post(confirm, headers=headers, json={'code': code}).status_code == 400
    assert client.get('/auth/me', headers=headers).json()['phone_verified_at']
    assert client.get('/farms', headers=headers).status_code == 403
    approve_test_registration(registration)
    new_phone = next_test_phone()
    changed = client.patch('/auth/me', headers=headers, json={'phone_number': new_phone}).json()
    assert changed['phone_number'] == new_phone
    assert changed['phone_verified_at'] is None
    with SessionLocal.begin() as db:
        challenge = db.get(phone_verification.AccountPhoneChallenge, registration.json()['id'])
        challenge.sent_at -= timedelta(minutes=6)
    assert client.post(request, headers=headers).status_code == 200
    code = messages[-1][1].split(': ')[1].split('.')[0]
    wrong = '999999' if code != '999999' else '000000'
    for _ in range(5):
        assert client.post(confirm, headers=headers, json={'code': wrong}).status_code == 400
    assert client.post(confirm, headers=headers, json={'code': code}).status_code == 400
    assert client.get('/auth/me', headers=headers).json()['phone_verified_at'] is None
