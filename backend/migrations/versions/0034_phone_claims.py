"""Reserve phone numbers on new writes without rewriting legacy accounts."""
from alembic import op
import sqlalchemy as sa

revision = '0034_phone_claims'
down_revision = '0033_admin_contact_proof'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('phone_number_claim', sa.String(16), nullable=True))
    op.create_index('uq_users_phone_number_claim', 'users', ['phone_number_claim'], unique=True)


def downgrade():
    op.drop_index('uq_users_phone_number_claim', table_name='users')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('phone_number_claim')
