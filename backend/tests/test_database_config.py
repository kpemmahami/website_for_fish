import pytest

from app.database import database_url


def test_local_database_falls_back_to_sqlite(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    assert str(database_url()) == 'sqlite:///./aquafarm.db'


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_supabase_uses_psycopg_and_ssl(monkeypatch, scheme):
    monkeypatch.setenv('DATABASE_URL', scheme + '://postgres.project:p%40ss@aws-0-example.pooler.supabase.com:5432/postgres')
    url = database_url()
    assert url.drivername == 'postgresql+psycopg'
    assert url.username == 'postgres.project'
    assert url.password == 'p@ss'
    assert url.port == 5432
    assert url.query['sslmode'] == 'require'


def test_supabase_preserves_certificate_verification(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://host.pooler.supabase.com/postgres?sslmode=verify-full&sslrootcert=%2Ftmp%2Fca.crt')
    assert dict(database_url().query) == {'sslmode': 'verify-full', 'sslrootcert': '/tmp/ca.crt'}


def test_supabase_refuses_unencrypted_ssl_mode(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://host.pooler.supabase.com/postgres?sslmode=disable')
    with pytest.raises(RuntimeError, match='Supabase DATABASE_URL must use sslmode'):
        database_url()


def test_render_requires_configured_postgres(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='Set DATABASE_URL'):
        database_url()
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    with pytest.raises(RuntimeError, match='requires a PostgreSQL'):
        database_url()


def test_local_postgres_ssl_policy_is_unchanged(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://127.0.0.1/aquafarm_test_local?sslmode=disable')
    assert database_url().query['sslmode'] == 'disable'
