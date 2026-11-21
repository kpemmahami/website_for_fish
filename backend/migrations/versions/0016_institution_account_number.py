"""Add institution account numbers.

Revision ID: 0016_institution_account_number
Revises: 0015_plan_pricing_comparison
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_institution_account_number'
down_revision = '0015_plan_pricing_comparison'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'finance_institutions',
        sa.Column('account_number', sa.String(100), nullable=True),
    )
    op.execute(
        "UPDATE finance_institutions "
        "SET account_number = COALESCE(NULLIF(account_number, ''), registration_number)"
    )
    with op.batch_alter_table('finance_institutions') as batch_op:
        batch_op.alter_column(
            'account_number',
            existing_type=sa.String(100),
            nullable=False,
        )


def downgrade():
    raise RuntimeError('Downgrade disabled to protect institution records.')
