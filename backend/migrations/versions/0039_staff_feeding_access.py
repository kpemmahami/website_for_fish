"""Give unit assignments an explicit feeding-record permission."""
from alembic import op
import sqlalchemy as sa

revision = '0039_staff_feeding_access'
down_revision = '0038_farm_staff_scope'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('farm_staff_unit_access', sa.Column(
        'can_record_feeding', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade():
    with op.batch_alter_table('farm_staff_unit_access') as batch:
        batch.drop_column('can_record_feeding')
