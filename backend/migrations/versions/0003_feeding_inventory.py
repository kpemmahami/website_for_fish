"""Feed products, stock ledger, and feeding records.

Revision ID: 0003_feeding_inventory
Revises: 0002_operations
"""
from alembic import op
import sqlalchemy as sa
revision = '0003_feeding_inventory'
down_revision = '0002_operations'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('feed_products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('supplier', sa.String(120), nullable=True),
        sa.Column('pellet_size_mm', sa.Float(), nullable=True),
        sa.Column('protein_pct', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_feed_products_farm_id', 'feed_products', ['farm_id'])
    op.create_table('feed_ledger',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feed_id', sa.Integer(), sa.ForeignKey('feed_products.id'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('quantity_delta_kg', sa.Float(), nullable=False),
        sa.Column('cost_ghs', sa.Float(), nullable=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=True),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('receipt','feeding','adjustment')", name='ck_feed_event_type'),
        sa.CheckConstraint("(event_type = 'receipt' AND quantity_delta_kg > 0) OR (event_type = 'feeding' AND quantity_delta_kg < 0) OR event_type = 'adjustment'", name='ck_feed_delta_sign'))
    op.create_index('ix_feed_ledger_feed_id', 'feed_ledger', ['feed_id'])
    op.create_index('ix_feed_ledger_cycle_id', 'feed_ledger', ['cycle_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect farm records. Restore a verified backup instead.')
