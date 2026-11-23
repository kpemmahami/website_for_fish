"""Add optional processing businesses and extend the existing ledgers."""
from alembic import op
import sqlalchemy as sa

revision = "0026_fish_processing"
down_revision = "0025_activity_history_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('processing_businesses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('business_type', sa.String(length=20), nullable=False),
        sa.Column('methods_json', sa.Text(), nullable=False),
    )
    op.create_table('processing_suppliers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('contact', sa.String(length=150)),
    )
    op.create_index('ix_processing_suppliers_business_id', 'processing_suppliers', ['business_id'])
    op.create_table('processing_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('facility', sa.String(length=150), nullable=False),
        sa.Column('method', sa.String(length=150), nullable=False),
        sa.Column('started_on', sa.Date(), nullable=False),
        sa.Column('completed_on', sa.Date()),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.Column('steps', sa.Text(), nullable=False),
        sa.Column('mass_balance', sa.Text(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_index('ix_processing_batches_business_id', 'processing_batches', ['business_id'])
    op.create_table('processing_raw_lots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('processing_suppliers.id'), nullable=False),
        sa.Column('expense_id', sa.Integer(), sa.ForeignKey('farm_expenses.id'), nullable=False, unique=True),
        sa.Column('species', sa.String(length=150), nullable=False),
        sa.Column('received_on', sa.Date(), nullable=False),
        sa.Column('quantity_kg', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('storage', sa.String(length=150), nullable=False),
        sa.Column('observations', sa.Text()),
    )
    op.create_index('ix_processing_raw_lots_business_id', 'processing_raw_lots', ['business_id'])
    op.create_table('processing_inputs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('processing_batches.id'), nullable=False),
        sa.Column('raw_lot_id', sa.Integer(), sa.ForeignKey('processing_raw_lots.id')),
        sa.Column('harvest_id', sa.Integer(), sa.ForeignKey('harvest_lots.id')),
        sa.Column('quantity_kg', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('cost_pesewas', sa.Integer()),
        sa.Column('allocated_on', sa.Date(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.CheckConstraint('(raw_lot_id IS NULL) <> (harvest_id IS NULL)',name='ck_processing_input_one_source'),
    )
    op.create_index('ix_processing_inputs_batch_id', 'processing_inputs', ['batch_id'])
    op.create_index('ix_processing_inputs_harvest_id', 'processing_inputs', ['harvest_id'])
    op.create_index('ix_processing_inputs_raw_lot_id', 'processing_inputs', ['raw_lot_id'])
    op.create_table('processing_outputs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('processing_batches.id'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('quantity_kg', sa.Numeric(precision=14, scale=4), nullable=False),
    )
    op.create_index('ix_processing_outputs_batch_id', 'processing_outputs', ['batch_id'])
    op.create_table('processing_materials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
    )
    op.create_index('ix_processing_materials_business_id', 'processing_materials', ['business_id'])
    op.create_table('processing_material_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('material_id', sa.Integer(), sa.ForeignKey('processing_materials.id'), nullable=False),
        sa.Column('expense_id', sa.Integer(), sa.ForeignKey('farm_expenses.id'), nullable=False, unique=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
    )
    op.create_index('ix_processing_material_receipts_material_id', 'processing_material_receipts', ['material_id'])
    op.create_table('processing_finished_lots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('output_id', sa.Integer(), sa.ForeignKey('processing_outputs.id'), nullable=False),
        sa.Column('material_id', sa.Integer(), sa.ForeignKey('processing_materials.id')),
        sa.Column('material_used', sa.Integer(), nullable=False),
        sa.Column('material_cost_pesewas', sa.Integer(), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('weight_per_unit_kg', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('packaged_on', sa.Date(), nullable=False),
        sa.Column('best_before', sa.Date()),
        sa.Column('shelf_life_basis', sa.Text()),
        sa.Column('packaging', sa.String(length=150), nullable=False),
        sa.Column('storage', sa.String(length=150), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_index('ix_processing_finished_lots_business_id', 'processing_finished_lots', ['business_id'])
    op.create_index('ix_processing_finished_lots_material_id', 'processing_finished_lots', ['material_id'])
    op.create_index('ix_processing_finished_lots_output_id', 'processing_finished_lots', ['output_id'])
    op.create_table('processing_quality',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('processing_batches.id'), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('checked_on', sa.Date(), nullable=False),
        sa.Column('observations', sa.Text(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_index('ix_processing_quality_batch_id', 'processing_quality', ['batch_id'])
    op.create_table('processing_expense_allocations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('expense_id', sa.Integer(), sa.ForeignKey('farm_expenses.id'), nullable=False),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('processing_batches.id'), nullable=False),
        sa.Column('amount_pesewas', sa.Integer(), nullable=False),
        sa.Column('basis', sa.Text(), nullable=False),
    )
    op.create_index('ix_processing_expense_allocations_batch_id', 'processing_expense_allocations', ['batch_id'])
    op.create_index('ix_processing_expense_allocations_expense_id', 'processing_expense_allocations', ['expense_id'])
    op.create_table('processing_finished_movements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('processing_finished_lots.id'), nullable=False),
        sa.Column('sale_id', sa.Integer(), sa.ForeignKey('fish_sales.id')),
        sa.Column('quantity_delta', sa.Integer(), nullable=False),
        sa.Column('credit_pesewas', sa.Integer(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_index('ix_processing_finished_movements_lot_id', 'processing_finished_movements', ['lot_id'])
    op.create_table('processing_evidence',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('processing_businesses.id'), nullable=False),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('processing_batches.id'), nullable=False),
        sa.Column('stage', sa.String(25), nullable=False),
        sa.Column('recorded_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.Column('media_type', sa.String(50), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_index('ix_processing_evidence_business_id', 'processing_evidence', ['business_id'])
    op.create_index('ix_processing_evidence_batch_id', 'processing_evidence', ['batch_id'])
    with op.batch_alter_table('farm_expenses') as batch:
        batch.alter_column('farm_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('business_id', sa.Integer()))
        batch.create_foreign_key('fk_farm_expenses_business_id', 'processing_businesses', ['business_id'], ['id'])
        batch.create_index('ix_farm_expenses_business_id', ['business_id'])
        batch.add_column(sa.Column('processing_batch_id', sa.Integer()))
        batch.create_foreign_key('fk_farm_expenses_processing_batch_id', 'processing_batches', ['processing_batch_id'], ['id'])
        batch.create_index('ix_farm_expenses_processing_batch_id', ['processing_batch_id'])
        batch.add_column(sa.Column('finished_lot_id', sa.Integer()))
        batch.create_foreign_key('fk_farm_expenses_finished_lot_id', 'processing_finished_lots', ['finished_lot_id'], ['id'])
        batch.add_column(sa.Column('activity', sa.String(length=20)))
        batch.add_column(sa.Column('usage', sa.String(length=24)))
        batch.add_column(sa.Column('quantity', sa.Numeric(precision=14, scale=4)))
        batch.add_column(sa.Column('unit_label', sa.String(length=30)))
        batch.add_column(sa.Column('unit_price_pesewas', sa.Integer()))
        batch.create_check_constraint('ck_expense_farm_or_business','farm_id IS NOT NULL OR business_id IS NOT NULL')
    with op.batch_alter_table('sales_customers') as batch:
        batch.alter_column('farm_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('business_id', sa.Integer()))
        batch.create_foreign_key('fk_sales_customers_business_id', 'processing_businesses', ['business_id'], ['id'])
        batch.create_index('ix_sales_customers_business_id', ['business_id'])
    with op.batch_alter_table('fish_sales') as batch:
        batch.alter_column('farm_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('harvest_lot_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('business_id', sa.Integer()))
        batch.create_foreign_key('fk_fish_sales_business_id', 'processing_businesses', ['business_id'], ['id'])
        batch.create_index('ix_fish_sales_business_id', ['business_id'])
        batch.add_column(sa.Column('finished_lot_id', sa.Integer()))
        batch.create_foreign_key('fk_fish_sales_finished_lot_id', 'processing_finished_lots', ['finished_lot_id'], ['id'])
        batch.create_index('ix_fish_sales_finished_lot_id', ['finished_lot_id'])
        batch.add_column(sa.Column('packages_sold', sa.Integer()))
        batch.add_column(sa.Column('processing_cost_pesewas', sa.Integer()))
        batch.add_column(sa.Column('processing_request_key', sa.String(length=80)))
        batch.create_unique_constraint('uq_processed_sale_request', ['business_id','processing_request_key'])
        batch.create_check_constraint('ck_sale_stock_source',
            '(harvest_lot_id IS NOT NULL AND farm_id IS NOT NULL AND finished_lot_id IS NULL AND business_id IS NULL) OR '
            '(finished_lot_id IS NOT NULL AND business_id IS NOT NULL AND harvest_lot_id IS NULL AND farm_id IS NULL)')
    with op.batch_alter_table('sale_payments') as batch:
        batch.alter_column('farm_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    raise RuntimeError("Downgrade disabled to preserve processing records and accounting links.")
