"""Phase 0005 shared cost allocations.
Revision ID: 0005_automated_costing
Revises: 0004_production_forecasting
"""
from alembic import op
import sqlalchemy as sa
revision = '0005_automated_costing'
down_revision = '0004_production_forecasting'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('shared_cost_allocations',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('plan_id',sa.Integer(),sa.ForeignKey('production_plans.id'),nullable=False),
        sa.Column('category',sa.String(40),nullable=False),
        sa.Column('amount_ghs',sa.Float(),nullable=False),
        sa.Column('occurred_on',sa.Date(),nullable=False),
        sa.Column('description',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_shared_cost_allocations_plan_id','shared_cost_allocations',['plan_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect farm records. Restore a verified backup instead.')
