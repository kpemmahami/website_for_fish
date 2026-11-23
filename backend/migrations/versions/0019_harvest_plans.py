"""Add optional harvest plans to stocking cycles."""

from alembic import op
import sqlalchemy as sa

revision = '0019_harvest_plans'
down_revision = '0018_loan_fee_rates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stocking_cycles', sa.Column('harvest_duration_months', sa.Integer()))
    op.add_column('stocking_cycles', sa.Column('expected_harvest_on', sa.Date()))
    op.add_column('stocking_cycles', sa.Column('target_harvest_weight_g', sa.Float()))
    op.add_column('stocking_cycles', sa.Column('expected_survival_pct', sa.Float()))


def downgrade():
    with op.batch_alter_table('stocking_cycles') as batch:
        batch.drop_column('expected_survival_pct')
        batch.drop_column('target_harvest_weight_g')
        batch.drop_column('expected_harvest_on')
        batch.drop_column('harvest_duration_months')
