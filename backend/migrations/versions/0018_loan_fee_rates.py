"""Store the agreed loan fee percentages."""

from alembic import op
import sqlalchemy as sa

revision = '0018_loan_fee_rates'
down_revision = '0017_account_access'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('loan_accounts', sa.Column('processing_fee_rate_bps', sa.Integer()))
    op.add_column('loan_accounts', sa.Column('insurance_fee_rate_bps', sa.Integer()))


def downgrade():
    with op.batch_alter_table('loan_accounts') as batch:
        batch.drop_column('insurance_fee_rate_bps')
        batch.drop_column('processing_fee_rate_bps')
