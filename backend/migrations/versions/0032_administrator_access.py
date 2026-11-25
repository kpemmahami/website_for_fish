"""Support administrator suspension and session revocation."""
from alembic import op
import sqlalchemy as sa

revision = '0032_administrator_access'
down_revision = '0031_password_recovery'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_suspended', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('users', sa.Column('session_generation', sa.String(32), nullable=True))


def downgrade():
    raise RuntimeError('Downgrade would discard account suspensions and session revocations.')
