"""Distinguish by-products and track retry-safe processing requests."""
from alembic import op
import sqlalchemy as sa

revision = '0029_processing_byproducts'
down_revision = '0028_processing_quality_staff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('processing_requests',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('business_id',sa.Integer(),sa.ForeignKey('processing_businesses.id'),nullable=False),
        sa.Column('request_key',sa.String(80),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('record_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('business_id','request_key'),
    )
    op.add_column('processing_outputs',sa.Column('is_byproduct',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve by-product traceability.')
