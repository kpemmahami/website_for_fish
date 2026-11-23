"""Persist daily feeding schedules and identify the recorder of new ledger entries."""

from alembic import op
import sqlalchemy as sa

revision = '0022_feeding_sessions'
down_revision = '0021_sales_entry'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'daily_feeding_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('fed_on', sa.Date(), nullable=False),
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('feeding_recommendations.id'), nullable=False),
        sa.Column('times_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('skipped_json', sa.Text(), nullable=False, server_default='{}'),
        sa.UniqueConstraint('cycle_id', 'fed_on', name='uq_daily_feeding_cycle_date'),
    )
    op.add_column('feed_ledger', sa.Column('actual_fed_at', sa.DateTime(timezone=True)))
    op.add_column('feed_ledger', sa.Column('recorded_by', sa.Integer()))
    op.add_column('feed_ledger', sa.Column('feeding_response', sa.String(200)))


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve feeding session records.')
