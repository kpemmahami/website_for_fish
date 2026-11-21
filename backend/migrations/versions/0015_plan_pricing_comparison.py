"""Persist farmer pricing assumptions for production plans.

Revision ID: 0015_plan_pricing_comparison
Revises: 0014_lending_evidence_and_fees
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_plan_pricing_comparison'
down_revision = '0014_lending_evidence_and_fees'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'production_plans',
        sa.Column('market_price_ghs_per_kg', sa.Float(), nullable=True),
    )


def downgrade():
    raise RuntimeError('Downgrade disabled to protect farm records. Restore a verified backup instead.')
