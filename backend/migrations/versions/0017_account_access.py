"""Add account types and platform administrator provisioning."""
from alembic import op
import sqlalchemy as sa

revision = '0017_account_access'
down_revision = '0016_institution_account_number'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('account_type', sa.String(20), nullable=False,
                                     server_default='legacy'))
    op.create_table(
        'platform_admin_setup',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_table(
        'platform_admin_invitations',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    raise RuntimeError('Downgrade disabled to protect account access records.')
