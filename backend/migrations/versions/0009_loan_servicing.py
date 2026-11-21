"""Loan accounts and manually recorded disbursements/repayments.
Revision ID: 0009_loan_servicing
Revises: 0008_financial_institutions
"""
from alembic import op
import sqlalchemy as sa
revision='0009_loan_servicing'
down_revision='0008_financial_institutions'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('loan_accounts',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('application_id',sa.Integer(),sa.ForeignKey('loan_applications.id'),nullable=False,unique=True),
        sa.Column('institution_id',sa.Integer(),sa.ForeignKey('finance_institutions.id'),nullable=False),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('approved_pesewas',sa.Integer(),nullable=False),
        sa.Column('annual_flat_rate_bps',sa.Integer(),nullable=False),
        sa.Column('frequency',sa.String(20),nullable=False),
        sa.Column('first_due_date',sa.Date(),nullable=False),
        sa.Column('term_months',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loan_accounts_institution_id','loan_accounts',['institution_id'])
    op.create_index('ix_loan_accounts_farm_id','loan_accounts',['farm_id'])
    op.create_table('loan_disbursements',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('loan_id',sa.Integer(),sa.ForeignKey('loan_accounts.id'),nullable=False),
        sa.Column('amount_pesewas',sa.Integer(),nullable=False),
        sa.Column('reference',sa.String(100),nullable=False),
        sa.Column('disbursed_on',sa.Date(),nullable=False),
        sa.Column('recorded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('loan_id','reference',name='uq_loan_disbursement_reference'))
    op.create_index('ix_loan_disbursements_loan_id','loan_disbursements',['loan_id'])
    op.create_table('loan_installments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('loan_id',sa.Integer(),sa.ForeignKey('loan_accounts.id'),nullable=False),
        sa.Column('number',sa.Integer(),nullable=False),
        sa.Column('due_on',sa.Date(),nullable=False),
        sa.Column('principal_pesewas',sa.Integer(),nullable=False),
        sa.Column('interest_pesewas',sa.Integer(),nullable=False),
        sa.UniqueConstraint('loan_id','number',name='uq_loan_installment_number'))
    op.create_index('ix_loan_installments_loan_id','loan_installments',['loan_id'])
    op.create_table('loan_repayments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('loan_id',sa.Integer(),sa.ForeignKey('loan_accounts.id'),nullable=False),
        sa.Column('amount_pesewas',sa.Integer(),nullable=False),
        sa.Column('interest_pesewas',sa.Integer(),nullable=False),
        sa.Column('principal_pesewas',sa.Integer(),nullable=False),
        sa.Column('reference',sa.String(100),nullable=False),
        sa.Column('paid_on',sa.Date(),nullable=False),
        sa.Column('recorded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('loan_id','reference',name='uq_loan_repayment_reference'))
    op.create_index('ix_loan_repayments_loan_id','loan_repayments',['loan_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect loan transaction history; restore a verified backup.')
