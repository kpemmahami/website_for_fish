"""Add opt-in independent authorization for disbursement records."""
from alembic import op
import sqlalchemy as sa

revision = '0046_disbursement_reviews'
down_revision = '0045_accounting_periods'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('finance_institutions', sa.Column(
        'require_disbursement_approval', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.create_table(
        'loan_disbursement_reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('loan_id', sa.Integer(), sa.ForeignKey('loan_accounts.id'), nullable=False),
        sa.Column('amount_pesewas', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(100), nullable=False),
        sa.Column('disbursed_on', sa.Date(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('loan_evidence.id'), nullable=False, unique=True),
        sa.Column('prepared_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('decided_at', sa.DateTime(timezone=True)),
        sa.Column('reason', sa.String(500)),
        sa.UniqueConstraint('loan_id', 'reference', name='uq_disbursement_review_reference'),
        sa.CheckConstraint('amount_pesewas > 0', name='ck_disbursement_review_amount'),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name='ck_disbursement_review_status'),
    )


def downgrade():
    op.drop_table('loan_disbursement_reviews')
    with op.batch_alter_table('finance_institutions') as batch:
        batch.drop_column('require_disbursement_approval')
