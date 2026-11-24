"""Track password recovery cooldown and session revocation."""
from alembic import op
import sqlalchemy as sa

revision = '0031_password_recovery'
down_revision = '0030_expand_loan_status'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('recovery_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_reset_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_column('password_reset_at')
        batch.drop_column('recovery_requested_at')
