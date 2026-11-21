"""Store private videos linked to daily farm operation records."""
from alembic import op
import sqlalchemy as sa

revision = '0011_daily_record_evidence'
down_revision = '0010_farm_location_details'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'record_evidence',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('record_type', sa.String(length=30), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('storage_name', sa.String(length=80), nullable=False, unique=True),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_record_evidence_farm_id', 'record_evidence', ['farm_id'])
    op.create_index('ix_record_evidence_unit_id', 'record_evidence', ['unit_id'])
    op.create_index('ix_record_evidence_cycle_id', 'record_evidence', ['cycle_id'])


def downgrade():
    op.drop_index('ix_record_evidence_cycle_id', table_name='record_evidence')
    op.drop_index('ix_record_evidence_unit_id', table_name='record_evidence')
    op.drop_index('ix_record_evidence_farm_id', table_name='record_evidence')
    op.drop_table('record_evidence')
