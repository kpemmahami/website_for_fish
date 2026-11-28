"""Arkesel contract, sandbox isolation and durable dispatch tests."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select, update

from .test_api import client, next_test_phone
from .test_account_access import PASSWORD, admin_headers, credentials
from .test_operations import auth
from app.main import Register, SessionLocal, User, new_user
from app.phone_verification import AccountPhoneChallenge
from app.sms_gateway import SmsDeliveryError, arkesel_send, recipient_number
from app.sms_management import record_delivery
from app.sms_outbox import SmsOutbox, deliver_outbox, enqueue_financial_sms

MESSAGE_ID = 'f3be70c1-3545-4677-b607-6b5f32202652'
OTHER_ID = '9b61686b-b7a9-4167-bebe-808467635c05'


@pytest.fixture
def arkesel(monkeypatch):
    for key, value in {
        'SMS_PROVIDER': 'arkesel', 'SMS_ENABLED': 'true', 'ARKESEL_API_KEY': 'mock-api-key',
        'ARKESEL_SENDER_ID': 'AquaFarmGH', 'ARKESEL_SANDBOX': 'true', 'OTP_MODE': 'local',
        'ARKESEL_BASE_URL': 'https://sms.arkesel.com',
    }.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize('status', [401, 402, 403, 422, 429, 500])
def test_provider_errors_are_sanitized(arkesel, monkeypatch, status):
    monkeypatch.setattr(httpx, 'request', lambda *args, **kwargs: httpx.Response(status, text='private value'))
    with pytest.raises(SmsDeliveryError) as error:
        arkesel_send('0241234567', 'test message', sandbox=True)
    assert 'private value' not in str(error.value)
    assert error.value.state == ('unknown' if status >= 500 else 'failed')


def test_recipient_validation_and_timeout(arkesel, monkeypatch):
    assert recipient_number('024 123 4567') == recipient_number('+233241234567') == '233241234567'
    for phone in ('23324123456', '02412', '+442079460123', '024abcdefg'):
        with pytest.raises(SmsDeliveryError):
            recipient_number(phone)
    monkeypatch.setenv('ARKESEL_ALLOW_INTERNATIONAL', 'true')
    assert recipient_number('+442079460123') == '442079460123'
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout('private value')

    monkeypatch.setattr(httpx, 'request', timeout)
    with pytest.raises(SmsDeliveryError) as error:
        arkesel_send('0241234567', 'test message', sandbox=True)
    assert error.value.state == 'unknown' and len(calls) == 1 and 'private value' not in str(error.value)


@pytest.mark.parametrize('body', [
    None, {'status': 'success'}, {'status': 'error'},
    {'status': 'success', 'data': [{'recipient': '233241234567', 'id': MESSAGE_ID},
                                   {'invalid numbers': ['233241234568']}]},
    {'status': 'success', 'data': [{'recipient': '233241234567', 'id': 'invalid'}]},
])
def test_http_200_without_complete_acceptance_is_rejected(arkesel, monkeypatch, body):
    result = httpx.Response(200, text='not-json') if body is None else httpx.Response(200, json=body)
    monkeypatch.setattr(httpx, 'request', lambda *args, **kwargs: result)
    with pytest.raises(SmsDeliveryError):
        arkesel_send('0241234567', 'test message', sandbox=True)


def test_owner_sandbox_balance_and_delivery_poll(arkesel, monkeypatch):
    owner = admin_headers()
    farmer = auth('sms-gateway-farmer@example.com')
    assert client.get('/admin/sms/gateway', headers=farmer).status_code == 403
    assert client.post('/admin/sms/sandbox-test', headers=farmer, json={'phone_number': '0241234567'}).status_code == 403
    assert client.get('/admin/sms/gateway', headers=owner).json()['sandbox'] is True

    def provider(method, url, **kwargs):
        assert kwargs['headers']['api-key'] == 'mock-api-key'
        assert not kwargs['follow_redirects']
        assert url.startswith('https://sms.arkesel.com/api/v2/')
        if url.endswith('/send'):
            assert method == 'POST'
            assert kwargs['json'] == {'sender': 'AquaFarmGH', 'message': 'AquaFarm Ghana sandbox connectivity test.',
                                      'recipients': ['233241234567'], 'sandbox': True}
            data = [{'recipient': '233241234567', 'id': MESSAGE_ID}]
        elif url.endswith('/balance-details'):
            data = {'sms_balance': '3', 'main_balance': 'GHS 20.99'}
        elif url.endswith('/message-reports'):
            ids = kwargs['json']['msg_ids']
            data = {item: {'status': 'DELIVERED', 'message_count': 1, 'message': 'private code'} for item in ids}
        else:
            assert url.endswith('/'+OTHER_ID)
            data = {'ID': OTHER_ID, 'status': 'DELIVERED', 'message_count': 1, 'message': 'private code'}
        return httpx.Response(200, json={'status': 'success', 'data': data})

    monkeypatch.setattr(httpx, 'request', provider)
    result = client.post('/admin/sms/sandbox-test', headers=owner, json={'phone_number': '0241234567'})
    assert result.json() == {'state': 'sandbox', 'message_id': MESSAGE_ID}
    assert client.get('/admin/sms/balance', headers=owner).json() == {
        'sms_balance': '3', 'main_balance': 'GHS 20.99', 'low_balance': True,
    }
    record_delivery('otp', 'accepted', OTHER_ID)
    response = client.post('/admin/sms/delivery-reports', headers=owner, json={'message_ids': [MESSAGE_ID, OTHER_ID]})
    assert [row['state'] for row in response.json()['items']] == ['sandbox', 'delivered']
    assert 'private code' not in response.text and '233241234567' not in response.text
    batch_ids = ['550e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440002']
    for item in batch_ids:
        record_delivery('test', 'accepted', item)
    batch = client.post('/admin/sms/delivery-reports', headers=owner, json={'message_ids': batch_ids})
    assert batch.status_code == 200
    assert [row['state'] for row in batch.json()['items']] == ['delivered', 'delivered']
    usage = client.get('/admin/sms/usage', headers=owner).json()
    assert usage['states']['delivered'] >= 3 and usage['states']['sandbox'] >= 1
    assert client.get('/admin/sms/usage?start=2000-01-01&end=2000-01-01', headers=owner).json()['requests'] == 0


def test_named_financial_notice_uses_documented_mapping(arkesel, monkeypatch):
    from app.sms_gateway import send_sms
    monkeypatch.setenv('ARKESEL_SANDBOX', 'false')

    def provider(method, url, **kwargs):
        assert method == 'POST' and url.endswith('/sms/template/send')
        assert kwargs['json']['message'] == 'Hello <%name%>, A deposit was recorded.'
        assert kwargs['json']['recipients'] == {'233241234567': {'name': 'Test Farmer'}}
        return httpx.Response(200, json={'status': 'success', 'data': [
            {'recipient': '233241234567', 'id': '550e8400-e29b-41d4-a716-446655440003'},
        ]})

    monkeypatch.setattr(httpx, 'request', provider)
    assert send_sms('0241234567', 'A deposit was recorded.', category='financial',
                    recipient_name='Test Farmer') == '550e8400-e29b-41d4-a716-446655440003'


def test_otp_sandbox_fails_closed_and_resend_is_limited(arkesel, monkeypatch):
    phone = next_test_phone()
    owner = auth('arkesel-phone@example.com')
    user_id = client.get('/auth/me', headers=owner).json()['id']
    with SessionLocal.begin() as db:
        db.get(User, user_id).phone_number = phone
    root = '/auth/me/phone-verification'
    calls = []

    def provider(method, url, **kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200, json={'status': 'success', 'data': [
            {'recipient': phone[1:], 'id': '550e8400-e29b-41d4-a716-446655440000'},
        ]})

    monkeypatch.setattr(httpx, 'request', provider)
    assert client.post(root+'/request', headers=owner).status_code == 503
    assert not calls
    assert client.post(root+'/confirm', headers=owner, json={'code': '000000'}).status_code == 400
    monkeypatch.setenv('ARKESEL_SANDBOX', 'false')
    monkeypatch.setenv('OTP_SENDS_PER_ACCOUNT_HOUR', '1')
    request = client.post(root+'/request', headers=owner)
    assert request.status_code == 200
    code = calls[0]['message'].split(': ')[1].split('.')[0]
    assert calls[0]['sandbox'] is False and code not in request.text
    assert client.post(root+'/request', headers=owner).status_code == 429
    with SessionLocal.begin() as db:
        db.execute(update(AccountPhoneChallenge).where(AccountPhoneChallenge.user_id == user_id).values(
            sent_at=datetime.now(timezone.utc)-timedelta(seconds=61),
        ))
    assert client.post(root+'/request', headers=owner).status_code == 429
    assert len(calls) == 1
    wrong = '000000' if code != '000000' else '000001'
    assert client.post(root+'/confirm', headers=owner, json={'code': wrong}).status_code == 400
    with SessionLocal.begin() as db:
        db.execute(update(AccountPhoneChallenge).where(AccountPhoneChallenge.user_id == user_id).values(
            sent_at=datetime.now(timezone.utc)-timedelta(seconds=301),
        ))
    assert client.post(root+'/confirm', headers=owner, json={'code': code}).status_code == 400
    with SessionLocal.begin() as db:
        db.execute(update(AccountPhoneChallenge).where(AccountPhoneChallenge.user_id == user_id).values(
            sent_at=datetime.now(timezone.utc)-timedelta(seconds=61),
        ))
    assert client.post(root+'/confirm', headers=owner, json={'code': code}).status_code == 200
    assert client.post(root+'/confirm', headers=owner, json={'code': code}).status_code == 400


def test_institution_login_unlocks_only_after_arkesel_code_confirmation(arkesel, monkeypatch):
    email = 'arkesel-institution-sign-in@example.com'
    phone = next_test_phone()
    with SessionLocal.begin() as db:
        user = new_user(Register(**credentials(email)), 'institution')
        user.phone_number = phone
        user.phone_verified_at = datetime.now(timezone.utc)
        db.add(user)

    messages = []

    def provider(method, url, **kwargs):
        assert method == 'POST' and url == 'https://sms.arkesel.com/api/v2/sms/send'
        assert kwargs['json']['recipients'] == [phone[1:]]
        assert kwargs['json']['sandbox'] is False
        messages.append(kwargs['json']['message'])
        return httpx.Response(200, json={'status': 'success', 'data': [
            {'recipient': phone[1:], 'id': '550e8400-e29b-41d4-a716-446655440004'},
        ]})

    monkeypatch.setattr(httpx, 'request', provider)
    login = client.post('/auth/institution/login', json={'email': email, 'password': PASSWORD})
    assert login.status_code == 200 and 'access_token' not in login.json()
    challenge = {'token': login.json()['institution_mfa_token']}
    challenge_headers = {'Authorization': f"Bearer {challenge['token']}"}
    assert client.get('/auth/me', headers=challenge_headers).status_code == 401
    assert client.post('/auth/institution/mfa/request', json=challenge).status_code == 503
    assert messages == []

    monkeypatch.setenv('ARKESEL_SANDBOX', 'false')
    sent = client.post('/auth/institution/mfa/request', json=challenge)
    assert sent.status_code == 200 and len(messages) == 1
    code = messages[0].split(': ')[1].split('.')[0]
    assert code not in sent.text
    assert client.get('/auth/me', headers=challenge_headers).status_code == 401
    confirmation = {**challenge, 'code': code}
    result = client.post('/auth/institution/mfa/confirm', json=confirmation)
    assert result.status_code == 200
    access_headers = {'Authorization': f"Bearer {result.json()['access_token']}"}
    assert client.get('/auth/me', headers=access_headers).json()['email'] == email
    assert client.post('/auth/institution/mfa/confirm', json=confirmation).status_code == 400


def test_financial_queue_deduplicates_and_does_not_resend_unknown(monkeypatch):
    monkeypatch.setenv('AQUAFARM_FINANCIAL_SMS_ENABLED', 'true')
    owner = auth('sms-outbox-owner@example.com')
    user_id = client.get('/auth/me', headers=owner).json()['id']
    with SessionLocal.begin() as db:
        user = db.get(User, user_id)
        user.phone_number = next_test_phone()
        user.phone_verified_at = datetime.now(timezone.utc)
        user.sms_loan_reminders_enabled = True
        enqueue_financial_sms(db, user_id, 'repayment', 999998)
        assert db.get(SmsOutbox, 'repayment:999998') is None
        user.sms_financial_alerts_enabled = True
        enqueue_financial_sms(db, user_id, 'repayment', 999999)
        enqueue_financial_sms(db, user_id, 'repayment', 999999)
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise SmsDeliveryError('Ambiguous failure', 'unknown')

    deliver_outbox(timeout)
    deliver_outbox(timeout)
    with SessionLocal() as db:
        row = db.scalar(select(SmsOutbox).where(SmsOutbox.event_key == 'repayment:999999'))
        assert row.state == 'unknown'
    assert len(calls) == 1
