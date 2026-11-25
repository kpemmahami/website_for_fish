"""Track verification of saved account phone numbers."""
from alembic import op
import sqlalchemy as sa

revision = '0036_phone_verification'
down_revision = '0035_initial_password'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('phone_verified_at', sa.DateTime(timezone=True)))
    op.add_column('administrator_contact_proofs', sa.Column('existing_enrollment_proof', sa.String(64)))
    op.create_table(
        'account_phone_challenges',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('phone_number', sa.String(16), nullable=False),
        sa.Column('nonce', sa.String(43), nullable=False),
        sa.Column('code_digest', sa.String(64), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.Column('previous_phone', sa.String(16)),
        sa.Column('previous_code_digest', sa.String(64)),
        sa.Column('password_proof', sa.String(64)),
    )


def downgrade():
    raise RuntimeError('Downgrade would discard phone verification history.')
