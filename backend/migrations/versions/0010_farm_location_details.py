"""Farm address and nearest landmark (Phase 0010 frontend extension)."""
from alembic import op
import sqlalchemy as sa
revision = '0010_farm_location_details'
down_revision = '0009_loan_servicing'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('farms') as batch:
        batch.add_column(sa.Column('farm_address', sa.String(length=500), nullable=True))
        batch.add_column(sa.Column('nearest_landmark', sa.String(length=200), nullable=True))

def downgrade():
    with op.batch_alter_table('farms') as batch:
        batch.drop_column('nearest_landmark')
        batch.drop_column('farm_address')
