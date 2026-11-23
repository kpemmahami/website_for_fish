"""Explicitly seed the designated local test database."""

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.development import DEVELOPMENT_ACCOUNTS, TEST_DATABASE, enabled, seeded_account

DATABASE_MARKER = 0x41514654
PASSWORDS = {'admin': 'user1234', 'farmer': 'farmer12', 'bank': 'bank1234'}
ROLES = {'admin': 'admin', 'farmer': 'farmer', 'bank': 'institution'}


def main():
    if not enabled(os.environ.get('DATABASE_URL', 'sqlite:///./aquafarm.db')):
        raise SystemExit('Set AQUAFARM_ENV=local-test and DATABASE_URL to the designated aquafarm.local-test.db')
    if len(os.environ.get('SECRET_KEY', '')) < 32:
        raise SystemExit('Set an independent local-test SECRET_KEY before seeding.')
    if TEST_DATABASE.exists():
        with sqlite3.connect(TEST_DATABASE.as_uri() + '?mode=ro', uri=True) as connection:
            if connection.execute('PRAGMA application_id').fetchone()[0] != DATABASE_MARKER:
                raise SystemExit('Refusing to modify an existing database without the local-test marker.')
    else:
        with TEST_DATABASE.open('xb'):
            pass
        with sqlite3.connect(TEST_DATABASE) as connection:
            connection.execute(f'PRAGMA application_id = {DATABASE_MARKER}')

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'migrations'))
    command.upgrade(config, 'head')

    from sqlalchemy import select
    from app.administration import AdminSetup
    from app.lending import Institution, InstitutionIn, InstitutionMember, add_institution
    from app.main import Register, SessionLocal, User, audit, new_user

    messages = []
    with SessionLocal.begin() as db:
        existing = {}
        for username, email in DEVELOPMENT_ACCOUNTS.items():
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                if user.account_type != ROLES[username] or not seeded_account(db, user.id):
                    raise SystemExit(f'Account conflict for {username}. No account was changed.')
                existing[username] = user
        setup = db.get(AdminSetup, 1)
        if (setup is None) != ('admin' not in existing) or (
            setup is not None and setup.admin_user_id != existing['admin'].id
        ):
            raise SystemExit('Platform Owner setup conflicts with the test account.')
        if 'bank' in existing:
            institution = db.scalar(select(Institution).join(InstitutionMember).where(
                Institution.owner_user_id == existing['bank'].id,
                InstitutionMember.user_id == existing['bank'].id,
                InstitutionMember.role == 'owner',
                Institution.status == 'verified',
            ))
            if institution is None:
                raise SystemExit('Existing test institution is missing its verified owner membership.')

        for username, email in DEVELOPMENT_ACCOUNTS.items():
            if username in existing:
                messages.append(f'{username}: already provisioned')
                continue
            data = Register(full_name={'admin': 'Test Administrator', 'farmer': 'Test Farmer', 'bank': 'Test Bank Representative'}[username],
                            email=email, password=PASSWORDS[username])
            user = new_user(data, ROLES[username])
            db.add(user)
            db.flush()
            audit(db, user, 'seed_local_test', 'user', user.id)
            if username == 'admin':
                db.add(AdminSetup(id=1, admin_user_id=user.id))
                audit(db, user, 'bootstrap', 'platform_admin', user.id)
            elif username == 'bank':
                institution = add_institution(InstitutionIn(
                    name='Local Test Bank', institution_type='bank', account_number='LOCAL-TEST-BANK',
                ), user, db)
                institution.status = 'verified'
                owner_id = db.get(AdminSetup, 1).admin_user_id
                audit(db, db.get(User, owner_id), 'verify', 'finance_institution', institution.id,
                      '{"reason":"Isolated local development institution"}')
            messages.append(f'{username}: created')
    for message in messages:
        print(message)


if __name__ == '__main__':
    main()
