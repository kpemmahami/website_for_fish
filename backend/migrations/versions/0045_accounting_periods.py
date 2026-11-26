"""Add auditable monthly accounting period states."""
from alembic import op
import sqlalchemy as sa

revision = '0045_accounting_periods'
down_revision = '0044_institution_accounting'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'institution_accounting_periods',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('institution_id', sa.Integer(), sa.ForeignKey('finance_institutions.id'), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('closed', sa.Boolean(), nullable=False),
        sa.Column('changed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('institution_id', 'starts_on', name='uq_accounting_period_month'),
    )


def downgrade():
    op.drop_table('institution_accounting_periods')
