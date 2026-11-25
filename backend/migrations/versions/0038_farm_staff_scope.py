"""Store delegated access to specific production units."""
from alembic import op
import sqlalchemy as sa

revision = '0038_farm_staff_scope'
down_revision = '0037_admin_recovery_codes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'farm_staff_unit_access',
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
    )
    op.create_index('ix_farm_staff_unit_access_user_id', 'farm_staff_unit_access', ['user_id'])


def downgrade():
    raise RuntimeError('Downgrade would discard unit assignment history.')
