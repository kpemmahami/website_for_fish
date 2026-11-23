"""Allow the existing loan offer workflow states on PostgreSQL."""
from alembic import op
import sqlalchemy as sa

revision = '0030_expand_loan_status'
down_revision = '0029_processing_byproducts'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite already accepts these values regardless of the declared width.
    if op.get_bind().dialect.name == 'postgresql':
        op.alter_column('loan_accounts', 'status', existing_type=sa.String(20),
                        type_=sa.String(32), existing_nullable=False)


def downgrade():
    raise RuntimeError('Downgrade disabled because existing loan status values may exceed the old width.')
