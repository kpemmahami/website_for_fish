"""Resolve the database URL consistently for the API and Alembic."""

import os

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

LOCAL_DATABASE_URL = 'sqlite:///./aquafarm.db'


def database_url() -> URL:
    configured = os.getenv('DATABASE_URL', '').strip()
    on_render = os.getenv('RENDER', '').lower() == 'true'
    if on_render and not configured:
        raise RuntimeError('Set DATABASE_URL to the hosted PostgreSQL connection URL on Render.')

    try:
        url = make_url(configured or LOCAL_DATABASE_URL)
    except (ArgumentError, ValueError):
        raise RuntimeError('DATABASE_URL must be a valid SQLite or PostgreSQL connection URL.') from None

    if url.drivername in ('postgres', 'postgresql'):
        url = url.set(drivername='postgresql+psycopg')
    if url.get_backend_name() not in ('sqlite', 'postgresql'):
        raise RuntimeError('DATABASE_URL must select SQLite or PostgreSQL.')
    if on_render and url.get_backend_name() != 'postgresql':
        raise RuntimeError('Render requires a PostgreSQL DATABASE_URL.')

    host = (url.host or '').rstrip('.').lower()
    supabase = host.endswith(('.pooler.supabase.com', '.supabase.co'))
    if url.get_backend_name() == 'postgresql' and supabase:
        mode = url.query.get('sslmode')
        if mode is None:
            url = url.update_query_dict({'sslmode': 'require'})
        elif mode not in ('require', 'verify-ca', 'verify-full'):
            raise RuntimeError('Supabase DATABASE_URL must use sslmode=require, verify-ca, or verify-full.')
    return url

def database_failure_reason(url: URL, error: Exception) -> str:
    """Return a fixed label; driver error text can contain connection details."""
    original = getattr(error, 'orig', error)
    code = getattr(original, 'sqlstate', None)
    if code in ('42P01', '42703'):
        return 'registration_schema_missing'
    if code == '28P01':
        return 'database_password_rejected'
    if url.get_backend_name() == 'postgresql':
        if not url.password:
            return 'database_password_missing'
        if url.password in ('[YOUR-DATABASE-PASSWORD]', 'YOUR-DATABASE-PASSWORD'):
            return 'database_password_placeholder'
    message = str(original).lower()
    for phrases, reason in (
        (('tenant or user not found', 'tenant not found', 'invalid tenant'), 'pooler_project_or_username_rejected'),
        (('too many authentication errors', 'circuit breaker'), 'pooler_authentication_rate_limited'),
        (('password authentication failed', 'invalid user or password', 'sasl authentication'), 'database_login_rejected'),
        (('max client connections', 'maxclientsinsessionmode', 'too many connections'), 'pooler_connection_limit'),
        (('certificate verify failed', 'certificate', 'ssl error', 'ssl syscall'), 'tls_connection_failed'),
        (('could not translate host', 'name or service not known', 'nodename nor servname'), 'database_hostname_unresolved'),
        (('connection timeout', 'timeout expired', 'timed out'), 'database_connection_timed_out'),
        (('network is unreachable', 'no route to host', 'connection refused'), 'database_network_unreachable'),
        (('database does not exist', 'invalid catalog name'), 'database_name_rejected'),
        (('no pg_hba.conf entry', 'ip address is not allowed'), 'database_client_access_rejected'),
        (('server closed the connection', 'connection reset by peer'), 'database_connection_closed'),
    ):
        if any(phrase in message for phrase in phrases):
            return reason
    return 'database_error_unclassified'
