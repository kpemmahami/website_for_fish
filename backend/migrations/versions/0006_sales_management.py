"""Phase 0006 sales, harvest inventory and payments.
Revision ID: 0006_sales_management
Revises: 0005_automated_costing
"""
from alembic import op
import sqlalchemy as sa
revision = '0006_sales_management'
down_revision = '0005_automated_costing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sales_customers',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('name',sa.String(150),nullable=False),
        sa.Column('customer_type',sa.String(30),nullable=False),
        sa.Column('phone',sa.String(40)),sa.Column('notes',sa.String(1000)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_sales_customers_farm_id','sales_customers',['farm_id'])
    op.create_table('harvest_lots',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('cycle_id',sa.Integer(),sa.ForeignKey('stocking_cycles.id'),nullable=False),
        sa.Column('harvested_on',sa.Date(),nullable=False),
        sa.Column('quantity_kg',sa.Float(),nullable=False),
        sa.Column('loss_kg',sa.Float(),nullable=False),
        sa.Column('notes',sa.String(1000)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_harvest_lots_farm_id','harvest_lots',['farm_id'])
    op.create_index('ix_harvest_lots_cycle_id','harvest_lots',['cycle_id'])
    op.create_table('fish_sales',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('harvest_lot_id',sa.Integer(),sa.ForeignKey('harvest_lots.id'),nullable=False),
        sa.Column('customer_id',sa.Integer(),sa.ForeignKey('sales_customers.id'),nullable=False),
        sa.Column('sold_on',sa.Date(),nullable=False),
        sa.Column('quantity_kg',sa.Float(),nullable=False),
        sa.Column('unit_price_pesewas',sa.Integer(),nullable=False),
        sa.Column('total_pesewas',sa.Integer(),nullable=False),
        sa.Column('notes',sa.String(1000)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    for col in ('farm_id','harvest_lot_id','customer_id'):
        op.create_index('ix_fish_sales_'+col,'fish_sales',[col])
    op.create_table('sale_payments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('sale_id',sa.Integer(),sa.ForeignKey('fish_sales.id'),nullable=False),
        sa.Column('paid_on',sa.Date(),nullable=False),
        sa.Column('amount_pesewas',sa.Integer(),nullable=False),
        sa.Column('method',sa.String(30),nullable=False),
        sa.Column('reference',sa.String(120)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_sale_payments_farm_id','sale_payments',['farm_id'])
    op.create_index('ix_sale_payments_sale_id','sale_payments',['sale_id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to protect sales records. Restore a verified backup instead.')
