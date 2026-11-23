"""Add processing roles and configurable quality release checks."""
from alembic import op
import sqlalchemy as sa

revision = '0028_processing_quality_staff'
down_revision = '0027_processing_label_details'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('processing_members',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('processing_businesses.id'),nullable=False),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False,unique=True),
        sa.Column('permissions',sa.Text(),nullable=False),
    )
    op.create_index('ix_processing_members_business_id','processing_members',['business_id'])
    op.create_table('processing_quality_rules',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('processing_businesses.id'),nullable=False),
        sa.Column('method',sa.String(150),nullable=False),
        sa.Column('product',sa.String(150),nullable=False),
        sa.Column('checks',sa.Text(),nullable=False),
    )
    op.create_index('ix_processing_quality_rules_business_id','processing_quality_rules',['business_id'])
    op.add_column('processing_quality',sa.Column('checks',sa.Text(),nullable=False,server_default='[]'))


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve processing staff and quality decisions.')
