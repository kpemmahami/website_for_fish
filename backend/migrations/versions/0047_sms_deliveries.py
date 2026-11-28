"""Add metadata-only SMS delivery history."""
from alembic import op
import sqlalchemy as sa

revision = '0047_sms_deliveries'
down_revision = '0046_disbursement_reviews'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('sms_financial_alerts_enabled', sa.Boolean(),
                                    nullable=False, server_default=sa.false()))
    op.create_table(
        'sms_otp_quotas',
        sa.Column('bucket', sa.String(64), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), primary_key=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
    )
    op.create_index('ix_sms_otp_quotas_window_start', 'sms_otp_quotas', ['window_start'])
    op.create_table(
        'sms_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('message_id', sa.String(36), unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message_count', sa.Integer()),
        sa.Column('provider_sent_at', sa.String(19)),
        sa.Column('operator_id', sa.Integer()),
    )
    op.create_index('ix_sms_deliveries_created_at', 'sms_deliveries', ['created_at'])
    op.create_table(
        'sms_outbox',
        sa.Column('event_key', sa.String(80), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('template', sa.String(20), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message_id', sa.String(120)),
        sa.Column('attempts', sa.Integer(), nullable=False),
    )
    op.create_index('ix_sms_outbox_state', 'sms_outbox', ['state'])


def downgrade():
    op.drop_table('sms_outbox')
    op.drop_table('sms_deliveries')
    op.drop_table('sms_otp_quotas')
    op.drop_column('users', 'sms_financial_alerts_enabled')
