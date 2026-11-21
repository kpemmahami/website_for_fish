"""Add farmer SMS contacts and daily record reminders.
Revision ID: 0012_daily_record_sms_reminders
Revises: 0011_daily_record_evidence
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_daily_record_sms_reminders'
down_revision = '0011_daily_record_evidence'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('phone_number', sa.String(length=16), nullable=True))
    op.add_column(
        'users',
        sa.Column('sms_daily_records_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'daily_record_reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reminder_date', sa.Date(), nullable=False),
        sa.Column('missing_cycle_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('provider_message_id', sa.String(length=120), nullable=True),
        sa.Column('last_error', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'reminder_date', name='uq_daily_reminder_user_date'),
    )
    op.create_index('ix_daily_record_reminders_user_id', 'daily_record_reminders', ['user_id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve reminder delivery history and farmer contact settings.')
