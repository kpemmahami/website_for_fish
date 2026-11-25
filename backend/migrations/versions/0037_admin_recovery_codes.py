"""Store hashed one-time administrator recovery codes."""
from alembic import op
import sqlalchemy as sa

revision = '0037_admin_recovery_codes'
down_revision = '0036_phone_verification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'administrator_recovery_codes',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('code_digest', sa.String(64), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    raise RuntimeError('Downgrade would discard administrator recovery credentials.')
