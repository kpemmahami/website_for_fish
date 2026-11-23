"""Add customer contact details and invoice due dates."""

from alembic import op
import sqlalchemy as sa

revision = '0021_sales_entry'
down_revision = '0020_institution_staff'
branch_labels = None
depends_on = None


def upgrade():
    for name, length in [('email', 255), ('region', 100), ('district', 100), ('address', 250)]:
        op.add_column('sales_customers', sa.Column(name, sa.String(length)))
    op.add_column('fish_sales', sa.Column('due_on', sa.Date()))


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve customer contact and invoice due-date history.')
