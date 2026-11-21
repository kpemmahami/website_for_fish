"""Add stocking, sampling, mortality and water-quality records.

Revision ID: 0002_operations
Revises: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_operations'
down_revision = '0001_foundation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('stocking_cycles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('species', sa.String(100), nullable=False),
        sa.Column('stocked_count', sa.Integer(), nullable=False),
        sa.Column('initial_average_weight_g', sa.Float(), nullable=False),
        sa.Column('stocked_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('stocked_count > 0', name='ck_stocked_count_positive'),
        sa.CheckConstraint('initial_average_weight_g > 0', name='ck_initial_weight_positive'))
    op.create_index('ix_stocking_cycles_unit_id', 'stocking_cycles', ['unit_id'])
    op.create_index('uq_open_cycle_per_unit', 'stocking_cycles', ['unit_id'], unique=True, sqlite_where=sa.text('closed_at IS NULL'), postgresql_where=sa.text('closed_at IS NULL'))

    op.create_table('mortality_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('dead_count', sa.Integer(), nullable=False),
        sa.Column('observed_on', sa.Date(), nullable=False),
        sa.Column('cause', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('dead_count > 0', name='ck_dead_count_positive'))
    op.create_index('ix_mortality_records_cycle_id', 'mortality_records', ['cycle_id'])

    op.create_table('fish_samples',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('sampled_on', sa.Date(), nullable=False),
        sa.Column('weights_g_json', sa.Text(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('average_weight_g', sa.Float(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('sample_count > 0', name='ck_sample_count_positive'),
        sa.CheckConstraint('average_weight_g > 0', name='ck_sample_weight_positive'))
    op.create_index('ix_fish_samples_cycle_id', 'fish_samples', ['cycle_id'])

    op.create_table('water_quality_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('dissolved_oxygen_mg_l', sa.Float(), nullable=True),
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('ammonia_mg_l', sa.Float(), nullable=True),
        sa.Column('nitrite_mg_l', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('ph IS NULL OR (ph >= 0 AND ph <= 14)', name='ck_ph_range'),
        sa.CheckConstraint('dissolved_oxygen_mg_l IS NULL OR dissolved_oxygen_mg_l >= 0', name='ck_do_nonnegative'))
    op.create_index('ix_water_quality_records_unit_id', 'water_quality_records', ['unit_id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to protect farm records. Restore a verified backup instead.')
