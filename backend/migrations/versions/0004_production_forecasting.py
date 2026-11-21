"""Production plans and cycle expenses.
Revision ID: 0004_production_forecasting
Revises: 0003_feeding_inventory
"""
from alembic import op
import sqlalchemy as sa
revision = '0004_production_forecasting'
down_revision = '0003_feeding_inventory'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('production_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=True),
        sa.Column('species', sa.String(100), nullable=False),
        sa.Column('fingerling_count', sa.Integer(), nullable=False),
        sa.Column('initial_weight_g', sa.Float(), nullable=False),
        sa.Column('target_weight_g', sa.Float(), nullable=False),
        sa.Column('survival_pct', sa.Float(), nullable=False),
        sa.Column('expected_fcr', sa.Float(), nullable=False),
        sa.Column('feed_price_ghs_per_kg', sa.Float(), nullable=False),
        sa.Column('bag_size_kg', sa.Float(), nullable=False),
        sa.Column('fingerling_cost_ghs', sa.Float(), nullable=False),
        sa.Column('other_budget_ghs', sa.Float(), nullable=False),
        sa.Column('desired_profit_pct', sa.Float(), nullable=False),
        sa.Column('profit_method', sa.String(12), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_production_plans_farm_id', 'production_plans', ['farm_id'])
    op.create_index('ix_production_plans_cycle_id', 'production_plans', ['cycle_id'])
    op.create_table('cycle_expenses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('production_plans.id'), nullable=False),
        sa.Column('category', sa.String(40), nullable=False),
        sa.Column('amount_ghs', sa.Float(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_cycle_expenses_plan_id', 'cycle_expenses', ['plan_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect farm records. Restore a verified backup instead.')
