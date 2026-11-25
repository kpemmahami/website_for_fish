"""Daily feeding-record status, opt-in and Hubtel reminder behavior."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from .test_api import client
from .test_foundation import signup, upload_operation_evidence
from app.daily_reminders import (
    DailyRecordReminder,
    SmsDeliveryError,
    daily_status,
    deliver_daily_record_reminders,
    hubtel_send_sms,
)
from app.main import SessionLocal


GHANA_TZ = ZoneInfo('Africa/Accra')


def test_missing_feeding_flag_and_opted_in_sms_is_sent_once():
    farmer = signup('daily-reminder-farmer@example.com')
    farm = client.post(
        '/farms',
        json={'name':'Daily Reminder Farm','region':'North East','district':'Yunyoo','farm_type':'pond','species':'Tilapia','latitude':9.4,'longitude':-0.8},
        headers=farmer,
    )
    assert farm.status_code == 201, farm.text
    farm_id = farm.json()['id']
    unit = client.post(
        f'/farms/{farm_id}/units',
        json={'name':'Reminder Pond','unit_type':'pond'},
        headers=farmer,
    )
    assert unit.status_code == 201, unit.text
    stocking = upload_operation_evidence(farm_id, unit.json(), farmer, 'stocking')
    assert stocking.status_code == 201, stocking.text
    cycle = client.post(
        f"/farms/{farm_id}/units/{unit.json()['id']}/cycles",
        params={'evidence_id':stocking.json()['id']},
        json={'species':'Tilapia','stocked_count':1000,'initial_average_weight_g':10,'stocked_on':date.today().isoformat()},
        headers=farmer,
    )
    assert cycle.status_code == 201, cycle.text

    before_cutoff = datetime.combine(date.today(), time(7, 59), GHANA_TZ)
    after_cutoff = datetime.combine(date.today(), time(8, 0), GHANA_TZ)
    with SessionLocal() as db:
        before = daily_status(db, farm_id, before_cutoff)
        after = daily_status(db, farm_id, after_cutoff)
    assert before['cycles'][0]['status'] == 'due'
    assert before['cycles'][0]['is_overdue'] is False
    assert after['cycles'][0]['status'] == 'missing'
    assert after['cycles'][0]['is_overdue'] is True

    no_phone = client.patch(
        '/auth/me',
        json={'phone_number':None,'sms_daily_records_enabled':True},
        headers=farmer,
    )
    assert no_phone.status_code == 422
    contact = client.patch(
        '/auth/me',
        json={'phone_number':'+233545550171','sms_daily_records_enabled':True},
        headers=farmer,
    )
    assert contact.status_code == 200, contact.text
    assert contact.json()['sms_daily_records_enabled'] is True

    sent = []

    def sender(phone_number, message):
        sent.append((phone_number, message))
        return 'hubtel-message-123'

    with SessionLocal() as db:
        assert deliver_daily_record_reminders(db, after_cutoff, sender) == 1
        assert deliver_daily_record_reminders(db, after_cutoff, sender) == 0
        reminder = db.query(DailyRecordReminder).one()
        assert reminder.status == 'sent'
        assert reminder.provider_message_id == 'hubtel-message-123'
    assert len(sent) == 1
    assert sent[0][0] == '+233545550171'
    assert 'no feeding record' in sent[0][1]


def test_hubtel_sender_uses_configured_credentials_and_rejects_errors(monkeypatch):
    monkeypatch.setenv('HUBTEL_CLIENT_ID','test-client')
    monkeypatch.setenv('HUBTEL_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('HUBTEL_SMS_SENDER_ID','AquaFarm')
    requests = []

    class Response:
        is_success = True
        status_code = 200

        def json(self):
            return {'Status':0,'MessageId':'hubtel-123'}

    def fake_get(url, *, params, timeout):
        requests.append((url, params, timeout))
        return Response()

    monkeypatch.setattr('app.daily_reminders.httpx.get',fake_get)
    assert hubtel_send_sms('+233541234567','Reminder') == 'hubtel-123'
    assert requests[0][0] == 'https://smsc.hubtel.com/v1/messages/send'
    assert requests[0][1]['to'] == '233541234567'
    assert requests[0][1]['clientsecret'] == 'test-secret'

    class RejectedResponse(Response):
        def json(self):
            return {'Status':1}

    monkeypatch.setattr('app.daily_reminders.httpx.get',lambda *args,**kwargs: RejectedResponse())
    with pytest.raises(SmsDeliveryError,match='rejected'):
        hubtel_send_sms('+233541234567','Reminder')
