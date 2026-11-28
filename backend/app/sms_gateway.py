"""Backend-only SMS transport selection and Arkesel V2 response validation."""

import logging
import os
import re
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy.exc import SQLAlchemyError

from .phone_numbers import normalize_phone_number

ARKESEL_ORIGIN = 'https://sms.arkesel.com'
logger = logging.getLogger(__name__)


class SmsDeliveryError(RuntimeError):
    """Safe to log. Never includes a provider body or request data."""

    def __init__(self, reason: str, state: str = 'failed', *, retryable: bool = False):
        super().__init__(reason)
        self.state = state
        self.retryable = retryable


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.strip().lower() in ('true', '1', 'yes', 'on'):
        return True
    if value.strip().lower() in ('false', '0', 'no', 'off'):
        return False
    raise SmsDeliveryError(f'Invalid {name} setting')


def configured_provider() -> str:
    value = os.getenv('SMS_PROVIDER', 'hubtel').strip().lower()
    if value not in ('hubtel', 'arkesel'):
        raise SmsDeliveryError('Unknown SMS_PROVIDER setting')
    return value


def sandbox_enabled() -> bool:
    return configured_provider() == 'arkesel' and env_flag('ARKESEL_SANDBOX', True)


def arkesel_settings() -> tuple[str, str, str]:
    origin = os.getenv('ARKESEL_BASE_URL', ARKESEL_ORIGIN).rstrip('/')
    key = os.getenv('ARKESEL_API_KEY', '').strip()
    sender = os.getenv('ARKESEL_SENDER_ID', '').strip()
    if origin != ARKESEL_ORIGIN:
        raise SmsDeliveryError('ARKESEL_BASE_URL must be the official HTTPS origin')
    if not key or not re.fullmatch(r'[A-Za-z0-9 ]{1,11}', sender):
        raise SmsDeliveryError('Arkesel key or sender ID is missing or invalid')
    return origin, key, sender


def validate_delivery_settings() -> str:
    provider = configured_provider()
    if not env_flag('SMS_ENABLED', provider == 'hubtel'):
        raise SmsDeliveryError('SMS delivery disabled')
    if provider == 'arkesel':
        arkesel_settings()
        sandbox_enabled()
    elif not all(os.getenv(key, '').strip() for key in (
        'HUBTEL_CLIENT_ID', 'HUBTEL_CLIENT_SECRET', 'HUBTEL_SMS_SENDER_ID',
    )):
        raise SmsDeliveryError('Hubtel credentials or sender ID are not configured')
    return provider


def recipient_number(value: str) -> str:
    phone = normalize_phone_number(value)
    if phone is None or (phone.startswith('+233') and not re.fullmatch(r'\+233[1-9]\d{8}', phone)):
        raise SmsDeliveryError('Invalid SMS recipient number')
    if not phone.startswith('+233') and not env_flag('ARKESEL_ALLOW_INTERNATIONAL', False):
        raise SmsDeliveryError('International SMS recipients are disabled')
    return phone[1:]


def arkesel_request(method: str, path: str, payload: dict | None = None):
    origin, key, _ = arkesel_settings()
    try:
        response = httpx.request(
            method, origin + path, headers={'api-key': key, 'Accept': 'application/json'},
            json=payload, timeout=httpx.Timeout(12, connect=5), follow_redirects=False,
        )
    except httpx.HTTPError:
        raise SmsDeliveryError('Arkesel network request failed', 'unknown') from None
    errors = {
        401: 'authentication failed', 402: 'insufficient balance or invalid coverage',
        403: 'inactive gateway or insufficient permission', 422: 'invalid request or sender ID',
        429: 'rate limit reached',
    }
    if response.status_code != 200:
        reason = errors.get(response.status_code, f'HTTP {response.status_code}')
        state = 'unknown' if response.status_code >= 500 else 'failed'
        raise SmsDeliveryError(f'Arkesel {reason}', state, retryable=response.status_code == 429)
    try:
        result = response.json()
    except ValueError:
        raise SmsDeliveryError('Arkesel returned invalid JSON', 'unknown') from None
    if not isinstance(result, dict) or result.get('status') != 'success':
        raise SmsDeliveryError('Arkesel did not confirm success', 'unknown')
    return result.get('data')


def arkesel_send(phone_number: str, message: str, *, sandbox: bool) -> str:
    _, _, sender = arkesel_settings()
    recipient = recipient_number(phone_number)
    rows = arkesel_request('POST', '/api/v2/sms/send', {
        'sender': sender, 'message': message, 'recipients': [recipient], 'sandbox': sandbox,
    })
    return accepted_recipient(rows, recipient)


def arkesel_send_named_notice(phone_number: str, name: str, notice: str) -> str:
    _, _, sender = arkesel_settings()
    recipient = recipient_number(phone_number)
    rows = arkesel_request('POST', '/api/v2/sms/template/send', {
        'sender': sender, 'message': 'Hello <%name%>, '+notice,
        'recipients': {recipient: {'name': name}}, 'sandbox': False,
    })
    return accepted_recipient(rows, recipient)


def accepted_recipient(rows, recipient: str) -> str:
    if not isinstance(rows, list):
        raise SmsDeliveryError('Arkesel did not return recipient results', 'unknown')
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            raise SmsDeliveryError('Arkesel returned an invalid recipient result', 'unknown')
        if any(key in row for key in ('invalid numbers', 'invalid_numbers')):
            if row.get('invalid numbers') or row.get('invalid_numbers'):
                raise SmsDeliveryError('Arkesel rejected a recipient')
        if str(row.get('recipient', '')).lstrip('+') == recipient:
            matches.append(row)
    if len(matches) != 1:
        raise SmsDeliveryError('Arkesel did not confirm the requested recipient', 'unknown')
    if str(matches[0].get('status', '')).lower() in ('failed', 'error', 'rejected', 'invalid'):
        raise SmsDeliveryError('Arkesel rejected the requested recipient')
    try:
        return str(UUID(str(matches[0].get('id'))))
    except ValueError:
        raise SmsDeliveryError('Arkesel did not return a valid message ID', 'unknown') from None


def record_transport_result(category: str, state: str, message_id: str | None):
    from .sms_management import record_delivery
    try:
        record_delivery(category, state, message_id)
    except SQLAlchemyError:
        logger.error('Could not save SMS delivery metadata')


def send_sms(phone_number: str, message: str, *, category: str = 'otp', recipient_name: str | None = None) -> str | None:
    provider = None
    try:
        provider = validate_delivery_settings()
        if sandbox_enabled():
            raise SmsDeliveryError('Arkesel sandbox cannot deliver verification or notification SMS')
        if provider == 'arkesel':
            if category == 'financial' and recipient_name and re.fullmatch(r"[^<>{}\r\n\t]{1,80}", recipient_name):
                message_id = arkesel_send_named_notice(phone_number, recipient_name, message)
            else:
                message_id = arkesel_send(phone_number, message, sandbox=False)
            record_transport_result(category, 'accepted', message_id)
            return message_id
        from .daily_reminders import hubtel_send_sms
        return hubtel_send_sms(phone_number, message)
    except SmsDeliveryError as error:
        if provider == 'arkesel':
            record_transport_result(category, error.state, None)
        logger.warning('SMS transport failed (%s): %s', error.state, error)
        raise


def send_sandbox_test(phone_number: str) -> str:
    if validate_delivery_settings() != 'arkesel' or not sandbox_enabled():
        raise SmsDeliveryError('The Arkesel sandbox test requires sandbox mode')
    return arkesel_send(phone_number, 'AquaFarm Ghana sandbox connectivity test.', sandbox=True)


def arkesel_balance() -> dict:
    data = arkesel_request('GET', '/api/v2/clients/balance-details')
    credits = str(data.get('sms_balance', '')) if isinstance(data, dict) else ''
    main = str(data.get('main_balance', '')) if isinstance(data, dict) else ''
    if not re.fullmatch(r'\d+(?:\.\d+)?', credits) or not re.fullmatch(r'(?:[A-Z]{3} )?\d+(?:\.\d+)?', main):
        raise SmsDeliveryError('Arkesel returned invalid balance data', 'unknown')
    threshold = os.getenv('ARKESEL_LOW_BALANCE_THRESHOLD', '10').strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', threshold):
        raise SmsDeliveryError('Invalid ARKESEL_LOW_BALANCE_THRESHOLD setting')
    return {'sms_balance': credits, 'main_balance': main,
            'low_balance': Decimal(credits) <= Decimal(threshold)}


def delivery_view(message_id: UUID, row) -> dict:
    status = str(row.get('status', '')).upper() if isinstance(row, dict) else ''
    states = {'DELIVERED': 'delivered', 'QUEUED': 'accepted', 'SUBMITTED': 'accepted',
              'PROHIBITED': 'failed', 'NOT_DELIVERED': 'failed', 'EXPIRED': 'failed', 'FAILED': 'failed'}
    count = row.get('message_count') if isinstance(row, dict) else None
    sent_at = row.get('sent_at_time') if isinstance(row, dict) else None
    return {'message_id': str(message_id), 'state': states.get(status, 'unknown'),
            'message_count': count if type(count) is int and count >= 0 else None,
            'provider_sent_at': sent_at if isinstance(sent_at, str) and
            re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', sent_at) else None}


def arkesel_delivery(message_id: UUID) -> dict:
    row = arkesel_request('GET', f'/api/v2/sms/{message_id}')
    if not isinstance(row, dict) or str(row.get('ID', row.get('id', ''))).lower() != str(message_id):
        raise SmsDeliveryError('Arkesel did not confirm the requested message', 'unknown')
    return delivery_view(message_id, row)


def arkesel_delivery_batch(message_ids: list[UUID]) -> list[dict]:
    rows = arkesel_request('POST', '/api/v2/sms/message-reports', {'msg_ids': [str(item) for item in message_ids]})
    if not isinstance(rows, dict):
        raise SmsDeliveryError('Arkesel returned an invalid delivery report', 'unknown')
    return [delivery_view(message_id, rows.get(str(message_id))) for message_id in message_ids]
