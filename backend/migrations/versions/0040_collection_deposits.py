"""Record excess field collections separately from loan principal."""
from alembic import op
import sqlalchemy as sa

revision = '0040_collection_deposits'
down_revision = '0039_staff_feeding_access'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'collection_deposits',
        sa.Column('repayment_id', sa.Integer(), sa.ForeignKey('loan_repayments.id'), primary_key=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('amount_pesewas', sa.Integer(), nullable=False),
        sa.CheckConstraint('amount_pesewas > 0', name='ck_collection_deposit_positive'),
    )
    op.create_index('ix_collection_deposits_customer_id', 'collection_deposits', ['customer_id'])


def downgrade():
    op.drop_index('ix_collection_deposits_customer_id', table_name='collection_deposits')
    op.drop_table('collection_deposits')
