"""Apply only the password recovery migration to a confirmed Neon database."""
import argparse
import os
import secrets
import subprocess
import sys
from getpass import getpass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

PREVIOUS = '0030_expand_loan_status'
TARGET = '0031_password_recovery'


def current_revision(engine):
    with engine.connect() as connection:
        return connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()


def neon_target(raw_url):
    raw_url = raw_url.strip()
    if raw_url[:1] in ("'", '"') and raw_url[-1:] == raw_url[:1]:
        raw_url = raw_url[1:-1].strip()
    try:
        target = make_url(raw_url)
    except (ArgumentError, ValueError):
        raise SystemExit('Stopped. Paste only the connection URL, beginning with postgresql://.') from None
    if target.drivername not in ('postgresql', 'postgresql+psycopg'):
        raise SystemExit('Stopped. The connection URL must use PostgreSQL.')
    if not (target.host or '').lower().endswith('.neon.tech'):
        raise SystemExit('Stopped. The connection URL must point to a Neon hostname.')
    if not target.username or not target.database or not target.password:
        raise SystemExit('Stopped. The connection URL must include a username, password and database name.')
    if target.query.keys() - {'sslmode', 'channel_binding'}:
        raise SystemExit('Stopped. Use the Neon URL with only sslmode and channel_binding options.')
    mode = target.query.get('sslmode')
    if mode is None:
        target = target.update_query_dict({'sslmode': 'require'})
    elif mode not in ('require', 'verify-ca', 'verify-full'):
        raise SystemExit('Stopped. Set sslmode to require, verify-ca or verify-full.')
    return target.set(drivername='postgresql+psycopg')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clipboard', action='store_true', help='Read the connection URL from the Windows clipboard')
    args = parser.parse_args()
    if args.clipboard:
        getpass('Copy DATABASE_URL in Render, then press Enter here without pasting (input hidden): ')
        try:
            raw_url = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                 '[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-Clipboard -Raw'],
                capture_output=True, encoding='utf-8', check=True, timeout=10,
            ).stdout
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise SystemExit('Stopped. Could not read the Windows clipboard.') from None
        if not raw_url.strip().lstrip("'\"").startswith(('postgresql://', 'postgresql+psycopg://')):
            raise SystemExit('Stopped. The clipboard does not begin with a PostgreSQL URL. Copy the value beside DATABASE_URL in Render Environment.') from None
    else:
        raw_url = getpass('Paste the intended Neon PostgreSQL URL (input hidden): ')
    target = neon_target(raw_url)
    engine = create_engine(target, connect_args={'connect_timeout': 10})
    try:
        revision = current_revision(engine)
        print(f'Target: {target.host} / {target.database}')
        print(f'Current revision: {revision}')
        if revision not in (PREVIOUS, TARGET):
            raise SystemExit('Stopped. The current revision is outside the expected upgrade path.')
        if revision == PREVIOUS:
            if input(f'Type {target.host} to confirm this database: ').strip() != target.host:
                raise SystemExit('Stopped. Database confirmation did not match.')
            env = {**os.environ, 'DATABASE_URL': target.render_as_string(hide_password=False)}
            if not env.get('SECRET_KEY'):
                env['SECRET_KEY'] = secrets.token_hex(32)
            result = subprocess.run(
                [sys.executable, '-m', 'alembic', 'upgrade', TARGET], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if result.returncode:
                raise SystemExit(f'Alembic exited with status {result.returncode}. Verify the database before retrying.')
        columns = {column['name'] for column in inspect(engine).get_columns('users')}
        if current_revision(engine) != TARGET or not {'recovery_requested_at', 'password_reset_at'} <= columns:
            raise SystemExit('Migration verification failed.')
        print(f'Verified {TARGET} and both recovery columns.')
    except (SQLAlchemyError, ValueError) as error:
        raise SystemExit(f'Database verification failed ({type(error).__name__}).') from None
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
