"""Add institution staff lifecycle and scoped invitations."""

from alembic import op
import sqlalchemy as sa

revision = '0020_institution_staff'
down_revision = '0019_harvest_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('finance_institution_members', sa.Column('status', sa.String(20), nullable=False, server_default='active'))
    for field in ('department', 'job_title'):
        op.add_column('finance_institution_members', sa.Column(field, sa.String(120)))
    op.create_table(
        'institution_staff_invitations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(120), nullable=False),
        sa.Column('phone_number', sa.String(16)),
        sa.Column('department', sa.String(120)),
        sa.Column('job_title', sa.String(120)),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('accepted_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('accepted_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('institution_id', 'email', name='uq_staff_invite_institution_email'),
    )
    op.create_index('ix_staff_invitation_email', 'institution_staff_invitations', ['email'])


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve staff invitation and access records.')
