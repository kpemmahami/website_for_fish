"""Isolation rules for the explicitly seeded local test database."""

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import URL, make_url

TEST_DATABASE = Path(__file__).resolve().parent.parent / 'aquafarm.local-test.db'
DEVELOPMENT_ACCOUNTS = {
    'admin': 'admin@aquafarm-test.example.com',
    'farmer': 'farmer@aquafarm-test.example.com',
    'bank': 'bank@aquafarm-test.example.com',
}


def enabled(database_url: str | URL) -> bool:
    if os.environ.get('AQUAFARM_ENV') != 'local-test':
        return False
    url = make_url(database_url)
    return (
        url.drivername == 'sqlite' and not url.query and bool(url.database)
        and Path(url.database).resolve() == TEST_DATABASE
    )


def auto_approve_signup(database_url: str | URL) -> bool:
    return os.environ.get('AQUAFARM_LOCAL_TEST_AUTO_APPROVE') == '1' and enabled(database_url)


def seeded_account(db, user_id: int) -> bool:
    from .main import AuditLog

    return db.scalar(select(AuditLog.id).where(
        AuditLog.actor_id == user_id,
        AuditLog.action == 'seed_local_test',
        AuditLog.entity_type == 'user',
        AuditLog.entity_id == user_id,
    ).limit(1)) is not None
