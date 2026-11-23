"""Add farm expense register, supplier payments, and private attachments."""

from alembic import op
import sqlalchemy as sa

revision = '0023_farm_expenses'
down_revision = '0022_feeding_sessions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('farm_expenses',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('unit_id',sa.Integer(),sa.ForeignKey('production_units.id')),
        sa.Column('cycle_id',sa.Integer(),sa.ForeignKey('stocking_cycles.id')),
        sa.Column('category',sa.String(80),nullable=False),
        sa.Column('description',sa.String(300),nullable=False),
        sa.Column('supplier',sa.String(150)),sa.Column('notes',sa.Text()),
        sa.Column('classification',sa.String(20),nullable=False),
        sa.Column('occurred_on',sa.Date(),nullable=False),
        sa.Column('amount_pesewas',sa.Integer(),nullable=False),
        sa.Column('exception_reason',sa.Text()),
        sa.Column('review_status',sa.String(20),nullable=False),
        sa.Column('recorded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index('ix_farm_expenses_farm_id','farm_expenses',['farm_id'])
    op.create_table('expense_payments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('expense_id',sa.Integer(),sa.ForeignKey('farm_expenses.id'),nullable=False),
        sa.Column('paid_on',sa.Date(),nullable=False),
        sa.Column('amount_pesewas',sa.Integer(),nullable=False),
        sa.Column('method',sa.String(30),nullable=False),
        sa.Column('reference',sa.String(120)),
        sa.Column('recorded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
    )
    op.create_index('ix_expense_payments_expense_id','expense_payments',['expense_id'])
    op.create_table('expense_attachments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('expense_id',sa.Integer(),sa.ForeignKey('farm_expenses.id'),nullable=False),
        sa.Column('media_type',sa.String(50),nullable=False),
        sa.Column('content',sa.LargeBinary(),nullable=False),
        sa.Column('uploaded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index('ix_expense_attachments_expense_id','expense_attachments',['expense_id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve expense records and evidence.')
