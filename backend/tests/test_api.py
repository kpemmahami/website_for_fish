import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlencode

test_postgres_url = os.getenv('AQUAFARM_TEST_POSTGRES_URL')
if test_postgres_url:
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.engine import make_url

    url = make_url(test_postgres_url)
    if (url.drivername != 'postgresql+psycopg' or url.host not in ('127.0.0.1', '::1')
        or not (url.database or '').startswith('aquafarm_test_')):
        raise RuntimeError('Use a disposable loopback PostgreSQL database named aquafarm_test_*.')
    test_engine = create_engine(url)
    try:
        if inspect(test_engine).get_table_names(schema='public'):
            raise RuntimeError('The PostgreSQL test database must be empty.')
    finally:
        test_engine.dispose()
    os.environ['DATABASE_URL'] = test_postgres_url
else:
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.environ['DATABASE_URL'] = f'sqlite:///{path}'
os.environ['SECRET_KEY'] = 'test-secret-key-that-is-at-least-32-characters'
os.environ['AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED'] = 'false'
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command
config = Config("alembic.ini")
command.upgrade(config, "head")
from app.main import app

client = TestClient(app)
_loan_video_number = 0

def upload_loan_video(headers, farm_id, record_type, loan_id=None):
    global _loan_video_number
    _loan_video_number += 1
    now = datetime.now(timezone.utc).isoformat()
    params = urlencode({
        'record_type': record_type,
        'captured_at': now,
        'device_recorded_at': now,
        'duration_seconds': 15,
    })
    path = f'/farms/{farm_id}/loan-evidence?{params}' if loan_id is None else f'/finance/loans/{loan_id}/evidence?{params}'
    video = b'\x1a\x45\xdf\xa3' + _loan_video_number.to_bytes(4, 'big') + bytes(32)
    response = client.post(path, content=video, headers={**headers, 'Content-Type': 'video/webm'})
    assert response.status_code == 201, response.text
    return response.json()['id']

def test_farm_ownership():
    def signup(email):
        r = client.post('/auth/register', json={'full_name':'Test Farmer','email':email,'password':'a-very-long-password-123'})
        assert r.status_code == 201, r.text
        token = client.post('/auth/login', json={'email':email,'password':'a-very-long-password-123'}).json()['access_token']
        return {'Authorization': f'Bearer {token}'}
    a = signup('farmer1@example.com')
    b = signup('farmer2@example.com')
    payload = {'name':'Nasia Fish Farm','region':'North East','district':'West Mamprusi','farm_type':'pond','species':'Catfish'}
    r = client.post('/farms', json=payload, headers=a)
    assert r.status_code == 201, r.text
    farm_id = r.json()['id']
    assert len(client.get('/farms', headers=a).json()) == 1
    assert client.get('/farms', headers=b).json() == []
    assert client.get(f'/farms/{farm_id}', headers=b).status_code == 404
    assert client.put(f'/farms/{farm_id}', json=payload, headers=b).status_code == 404
    assert client.delete(f'/farms/{farm_id}', headers=b).status_code == 404
    assert client.delete(f'/farms/{farm_id}', headers=a).status_code == 204
