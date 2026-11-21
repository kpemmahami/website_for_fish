"""Financial institutions and loan appraisal (no disbursement or repayment).
Revision ID: 0008_financial_institutions
Revises: 0006_sales_management
"""
from alembic import op
import sqlalchemy as sa
revision='0008_financial_institutions'
down_revision='0006_sales_management'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('finance_institutions',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('name',sa.String(180),nullable=False),
        sa.Column('institution_type',sa.String(40),nullable=False),
        sa.Column('registration_number',sa.String(100),nullable=False),
        sa.Column('owner_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_finance_institutions_owner_user_id','finance_institutions',['owner_user_id'])
    op.create_table('finance_institution_members',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('institution_id',sa.Integer(),sa.ForeignKey('finance_institutions.id'),nullable=False),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('role',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('institution_id','user_id',name='uq_finance_membership'))
    op.create_index('ix_finance_institution_members_institution_id','finance_institution_members',['institution_id'])
    op.create_index('ix_finance_institution_members_user_id','finance_institution_members',['user_id'])
    op.create_table('loan_applications',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
        sa.Column('institution_id',sa.Integer(),sa.ForeignKey('finance_institutions.id'),nullable=False),
        sa.Column('requested_pesewas',sa.Integer(),nullable=False),
        sa.Column('purpose',sa.String(1000),nullable=False),
        sa.Column('term_months',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('report_snapshot_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loan_applications_farm_id','loan_applications',['farm_id'])
    op.create_index('ix_loan_applications_institution_id','loan_applications',['institution_id'])
    op.create_table('loan_appraisals',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('application_id',sa.Integer(),sa.ForeignKey('loan_applications.id'),nullable=False),
        sa.Column('reviewer_user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('decision',sa.String(30),nullable=False),
        sa.Column('rationale',sa.String(2000),nullable=False),
        sa.Column('approved_pesewas',sa.Integer()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_loan_appraisals_application_id','loan_appraisals',['application_id'])
    op.create_index('ix_loan_appraisals_reviewer_user_id','loan_appraisals',['reviewer_user_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect financial application records. Restore a verified backup instead.')
