"""Require new institution accounts to replace their initial password."""
from alembic import op
import sqlalchemy as sa

revision = '0035_initial_password'
down_revision = '0034_phone_claims'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column(
        'initial_password_required', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade():
    raise RuntimeError('Downgrade would discard outstanding first-sign-in credential requirements.')
