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
    assert client.patch('/auth/me', headers=headers, json={'phone_number': new_phone}).status_code == 409
    with SessionLocal.begin() as db:
        challenge = db.get(phone_verification.AccountPhoneChallenge, registration.json()['id'])
        challenge.sent_at -= timedelta(minutes=6)
    replace_request = '/auth/me/phone-replacement/request'
    replace_confirm = '/auth/me/phone-replacement/confirm'
    replacement = {'phone_number': new_phone, 'password': password}
    assert client.post(replace_request, headers=headers, json={**replacement, 'password': 'wrong'}).status_code == 403
    assert client.post(replace_request, headers=headers, json=replacement).status_code == 200
    assert [message[0] for message in messages[-2:]] == [phone, new_phone]
    old_code, new_code = (message[1].split(': ')[1].split('.')[0] for message in messages[-2:])
    assert client.post(confirm, headers=headers, json={'code': new_code}).status_code == 400
    assert client.get('/auth/me', headers=headers).json()['phone_number'] == phone
    wrong = '999999' if old_code != '999999' else '000000'
    assert client.post(replace_confirm, headers=headers, json={'previous_code': wrong, 'code': new_code}).status_code == 400
    assert client.post(replace_confirm, headers=headers, json={'previous_code': old_code, 'code': new_code}).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/auth/farmer/login', json={'email': phone, 'password': password}).status_code == 401
    result = client.post('/auth/farmer/login', json={'email': new_phone, 'password': password})
    assert result.status_code == 200
    new_headers = {'Authorization': f"Bearer {result.json()['access_token']}"}
    account = client.get('/auth/me', headers=new_headers).json()
    assert account['phone_number'] == new_phone and account['phone_verified_at']
    assert client.post(replace_confirm, headers=new_headers, json={'previous_code': old_code, 'code': new_code}).status_code == 400
