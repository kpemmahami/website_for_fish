"""Add a tenant-owned financial institution branch directory."""
from alembic import op
import sqlalchemy as sa

revision = '0042_institution_branches'
down_revision = '0041_standalone_deposits'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'institution_branches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('code', sa.String(24), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('address', sa.String(260), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('institution_id', 'code', name='uq_institution_branch_code'),
    )


def downgrade():
    op.drop_table('institution_branches')
