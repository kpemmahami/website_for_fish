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
