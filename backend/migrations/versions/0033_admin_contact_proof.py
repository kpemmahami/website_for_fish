"""Store bounded contact verification challenges for pending administrators."""
from alembic import op
import sqlalchemy as sa

revision = '0033_admin_contact_proof'
down_revision = '0032_administrator_access'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'administrator_contact_proofs',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('link_digest', sa.String(64), nullable=False, unique=True),
        sa.Column('code_digest', sa.String(64), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('enrollment_digest', sa.String(64), unique=True),
        sa.Column('authenticator_nonce', sa.String(43)),
        sa.Column('last_authenticator_step', sa.BigInteger()),
        sa.Column('authenticator_window', sa.BigInteger()),
        sa.Column('authenticator_attempts', sa.Integer()),
    )


def downgrade():
    raise RuntimeError('Downgrade would discard administrator contact verification history.')
