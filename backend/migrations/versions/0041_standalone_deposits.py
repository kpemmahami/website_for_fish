"""Record standalone institution deposits without changing loan balances."""
from alembic import op
import sqlalchemy as sa

revision = '0041_standalone_deposits'
down_revision = '0040_collection_deposits'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'standalone_collection_deposits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reference', sa.String(48), nullable=False, unique=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('loan_evidence.id'), nullable=False, unique=True),
        sa.Column('recorded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('amount_pesewas', sa.Integer(), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('amount_pesewas > 0', name='ck_standalone_deposit_positive'),
    )
    op.create_index('ix_standalone_collection_deposits_customer_id', 'standalone_collection_deposits', ['customer_id'])
    op.create_index('ix_standalone_collection_deposits_institution_id', 'standalone_collection_deposits', ['institution_id'])


def downgrade():
    op.drop_table('standalone_collection_deposits')
