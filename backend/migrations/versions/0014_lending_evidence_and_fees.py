"""Add loan transaction video evidence, fee balances, and loan SMS consent.

Revision ID: 0014_lending_evidence_and_fees
Revises: 0013_phase_one_completion
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_lending_evidence_and_fees'
down_revision = '0013_phase_one_completion'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('sms_loan_reminders_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'loan_accounts',
        sa.Column('commitment_fee_pesewas', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'loan_accounts',
        sa.Column('processing_fee_pesewas', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'loan_accounts',
        sa.Column('insurance_fee_pesewas', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'loan_installments',
        sa.Column('fees_pesewas', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'loan_repayments',
        sa.Column('fees_pesewas', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_table(
        'loan_evidence',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('loan_id', sa.Integer(), sa.ForeignKey('loan_accounts.id'), nullable=True),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('loan_applications.id'), nullable=True),
        sa.Column('record_type', sa.String(length=30), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('storage_name', sa.String(length=80), nullable=False, unique=True),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('device_recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('server_received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('farm_id', 'sha256', name='uq_loan_evidence_farm_sha256'),
    )
    op.create_index('ix_loan_evidence_farm_id', 'loan_evidence', ['farm_id'])
    op.create_index('ix_loan_evidence_loan_id', 'loan_evidence', ['loan_id'])
    op.create_index('ix_loan_evidence_application_id', 'loan_evidence', ['application_id'])
    op.create_table(
        'loan_sms_reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('loan_id', sa.Integer(), sa.ForeignKey('loan_accounts.id'), nullable=False),
        sa.Column('installment_number', sa.Integer(), nullable=False),
        sa.Column('reminder_key', sa.String(length=120), nullable=False, unique=True),
        sa.Column('reminder_type', sa.String(length=20), nullable=False),
        sa.Column('reminder_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('provider_message_id', sa.String(length=120), nullable=True),
        sa.Column('last_error', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_loan_sms_reminders_user_id', 'loan_sms_reminders', ['user_id'])
    op.create_index('ix_loan_sms_reminders_loan_id', 'loan_sms_reminders', ['loan_id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve loan transaction and evidence history.')
