"""Apply only the password recovery migration to a confirmed Neon database."""
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


def main():
    raw_url = getpass('Paste the intended Neon PostgreSQL URL (input hidden): ').strip()
    try:
        target = make_url(raw_url)
        if (
            target.drivername not in ('postgresql', 'postgresql+psycopg')
            or not (target.host or '').endswith('.neon.tech')
            or not target.database or not target.password
            or target.query.get('sslmode') not in ('require', 'verify-ca', 'verify-full')
        ):
            raise ValueError
    except (ArgumentError, ValueError):
        raise SystemExit('Stopped. Use a Neon PostgreSQL URL with SSL enabled.') from None

    engine = create_engine(target.set(drivername='postgresql+psycopg'), connect_args={'connect_timeout': 10})
    try:
        revision = current_revision(engine)
        print(f'Target: {target.host} / {target.database}')
        print(f'Current revision: {revision}')
        if revision not in (PREVIOUS, TARGET):
            raise SystemExit('Stopped. The current revision is outside the expected upgrade path.')
        if revision == PREVIOUS:
            if input(f'Type {target.host} to confirm this database: ').strip() != target.host:
                raise SystemExit('Stopped. Database confirmation did not match.')
            env = {**os.environ, 'DATABASE_URL': raw_url}
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
