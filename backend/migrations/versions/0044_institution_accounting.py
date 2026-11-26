"""Add institution accounting accounts and balanced journal storage."""
from alembic import op
import sqlalchemy as sa

revision = '0044_institution_accounting'
down_revision = '0043_branch_assignments'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'institution_accounting_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('category', sa.String(16), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('institution_id', 'code', name='uq_accounting_institution_code'),
        sa.CheckConstraint("category IN ('asset','liability','equity','income','expense','contra')",
                           name='ck_accounting_account_category'),
    )
    op.create_table(
        'institution_accounting_journals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('source_type', sa.String(40), nullable=False),
        sa.Column('source_reference', sa.String(120), nullable=False),
        sa.Column('effective_on', sa.Date(), nullable=False),
        sa.Column('posted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.UniqueConstraint('institution_id', 'source_type', 'source_reference', name='uq_accounting_journal_source'),
    )
    op.create_table(
        'institution_accounting_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('journal_id', sa.Integer(), sa.ForeignKey('institution_accounting_journals.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('institution_accounting_accounts.id'), nullable=False),
        sa.Column('debit_pesewas', sa.BigInteger(), nullable=False),
        sa.Column('credit_pesewas', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('(debit_pesewas > 0 AND credit_pesewas = 0) OR '
                           '(credit_pesewas > 0 AND debit_pesewas = 0)', name='ck_accounting_line_one_side'),
    )
    for column in ('journal_id', 'account_id'):
        op.create_index('ix_institution_accounting_lines_'+column, 'institution_accounting_lines', [column])


def downgrade():
    op.drop_table('institution_accounting_lines')
    op.drop_table('institution_accounting_journals')
    op.drop_table('institution_accounting_accounts')
