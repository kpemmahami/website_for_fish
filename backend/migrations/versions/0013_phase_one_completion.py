"""Complete Phase One operational records and review metadata.

Revision ID: 0013_phase_one_completion
Revises: 0012_daily_record_sms_reminders
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = '0013_phase_one_completion'
down_revision = '0012_daily_record_sms_reminders'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'stocking_cycles',
        sa.Column('fingerling_supplier', sa.String(length=200), nullable=True),
    )
    op.add_column(
        'harvest_lots',
        sa.Column('fish_count', sa.Integer(), nullable=True),
    )
    op.add_column('harvest_lots', sa.Column('grade', sa.String(length=80), nullable=True))
    op.add_column('harvest_lots', sa.Column('buyer_name', sa.String(length=150), nullable=True))

    op.add_column('feed_ledger', sa.Column('supplier', sa.String(length=120), nullable=True))
    op.add_column('feed_ledger', sa.Column('batch_number', sa.String(length=100), nullable=True))
    op.add_column('feed_ledger', sa.Column('expiry_date', sa.Date(), nullable=True))
    op.add_column('feed_ledger', sa.Column('reference_number', sa.String(length=120), nullable=True))
    op.add_column('feed_ledger', sa.Column('evidence_id', sa.Integer(), nullable=True))

    op.add_column('fish_sales', sa.Column('receipt_reference', sa.String(length=120), nullable=True))
    op.add_column('fish_sales', sa.Column('evidence_id', sa.Integer(), nullable=True))

    op.add_column('production_units', sa.Column('evidence_tag', sa.String(length=32), nullable=True))
    bind = op.get_bind()
    unit_ids = bind.execute(sa.text('SELECT id FROM production_units')).fetchall()
    for (unit_id,) in unit_ids:
        bind.execute(
            sa.text('UPDATE production_units SET evidence_tag = :tag WHERE id = :id'),
            {'tag': uuid.uuid4().hex, 'id': unit_id},
        )
    with op.batch_alter_table('production_units') as batch:
        batch.alter_column('evidence_tag', existing_type=sa.String(length=32), nullable=False)
        batch.create_unique_constraint('uq_production_units_evidence_tag', ['evidence_tag'])

    op.create_table(
        'activity_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('activity_type', sa.String(length=30), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('issued_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_activity_challenges_farm_unit', 'activity_challenges', ['farm_id', 'unit_id'])

    with op.batch_alter_table('record_evidence') as batch:
        batch.alter_column(
            'cycle_id',
            existing_type=sa.Integer(),
            existing_nullable=False,
            nullable=True,
        )
        batch.add_column(sa.Column('latitude', sa.Float(), nullable=True))
        batch.add_column(sa.Column('longitude', sa.Float(), nullable=True))
        batch.add_column(sa.Column('gps_accuracy_m', sa.Float(), nullable=True))
        batch.add_column(sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('device_recorded_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('server_received_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('offline_delay_seconds', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('geofence_distance_m', sa.Float(), nullable=True))
        batch.add_column(sa.Column('geofence_status', sa.String(length=30), nullable=True))
        batch.add_column(sa.Column('activity_reference', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column(
            'challenge_id',
            sa.Integer(),
            sa.ForeignKey('activity_challenges.id', name='fk_record_evidence_challenge'),
            nullable=True,
        ))
        batch.add_column(sa.Column('sha256', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column(
            'verification_status',
            sa.String(length=20),
            nullable=False,
            server_default='pending',
        ))
        batch.add_column(sa.Column('verification_notes', sa.Text(), nullable=True))
        batch.add_column(sa.Column(
            'verified_by',
            sa.Integer(),
            sa.ForeignKey('users.id', name='fk_record_evidence_verified_by_users'),
            nullable=True,
        ))
        batch.add_column(sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        'uq_record_evidence_farm_sha256',
        'record_evidence',
        ['farm_id', 'sha256'],
        unique=True,
        sqlite_where=sa.text('sha256 IS NOT NULL'),
        postgresql_where=sa.text('sha256 IS NOT NULL'),
    )

    op.create_table(
        'farm_evidence_policies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False, unique=True),
        sa.Column('required_activities', sa.Text(), nullable=False, server_default=json.dumps([
            'feeding', 'growth', 'mortality', 'water_quality', 'stocking',
            'feed_delivery', 'feed_stock_count', 'fish_transfer', 'treatment',
            'inspection', 'harvest', 'sale_dispatch',
        ])),
        sa.Column('challenge_activities', sa.Text(), nullable=False, server_default=json.dumps([
            'feeding', 'growth', 'mortality', 'stocking', 'feed_stock_count',
            'fish_transfer', 'harvest', 'treatment',
        ])),
        sa.Column('geofence_radius_m', sa.Float(), nullable=False, server_default='500'),
        sa.Column('max_gps_accuracy_m', sa.Float(), nullable=False, server_default='100'),
        sa.Column('max_offline_delay_seconds', sa.Integer(), nullable=False, server_default='86400'),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('geofence_radius_m > 0', name='ck_evidence_policy_radius_positive'),
        sa.CheckConstraint('max_gps_accuracy_m > 0', name='ck_evidence_policy_accuracy_positive'),
        sa.CheckConstraint('max_offline_delay_seconds >= 0', name='ck_evidence_policy_offline_nonnegative'),
    )

    op.create_table(
        'fish_transfers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('target_cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('fish_count', sa.Integer(), nullable=False),
        sa.Column('loss_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transferred_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('source_cycle_id != target_cycle_id', name='ck_fish_transfer_distinct_cycles'),
        sa.CheckConstraint('fish_count > 0', name='ck_fish_transfer_count_positive'),
        sa.CheckConstraint('loss_count >= 0', name='ck_fish_transfer_loss_nonnegative'),
    )
    op.create_index('ix_fish_transfers_source_cycle_id', 'fish_transfers', ['source_cycle_id'])
    op.create_index('ix_fish_transfers_target_cycle_id', 'fish_transfers', ['target_cycle_id'])

    op.create_table(
        'farm_supervisors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assigned_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('farm_id', 'user_id', name='uq_farm_supervisor'),
    )
    op.create_index('ix_farm_supervisors_farm_id', 'farm_supervisors', ['farm_id'])
    op.create_index('ix_farm_supervisors_user_id', 'farm_supervisors', ['user_id'])

    op.create_table(
        'record_corrections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('record_type', sa.String(length=30), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('corrected_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('before_values', sa.Text(), nullable=False),
        sa.Column('after_values', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_record_corrections_farm_id', 'record_corrections', ['farm_id'])

    op.create_table(
        'feed_reconciliations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feed_id', sa.Integer(), sa.ForeignKey('feed_products.id'), nullable=False),
        sa.Column('ledger_entry_id', sa.Integer(), sa.ForeignKey('feed_ledger.id'), nullable=False, unique=True),
        sa.Column('system_stock_before_kg', sa.Float(), nullable=False),
        sa.Column('physical_stock_kg', sa.Float(), nullable=False),
        sa.Column('variance_kg', sa.Float(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('counted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('record_evidence.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('system_stock_before_kg >= 0', name='ck_feed_reconciliation_system_nonnegative'),
        sa.CheckConstraint('physical_stock_kg >= 0', name='ck_feed_reconciliation_physical_nonnegative'),
    )

    op.create_table(
        'fish_treatments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('product', sa.String(length=160), nullable=False),
        sa.Column('dose', sa.Float(), nullable=False),
        sa.Column('dose_unit', sa.String(length=40), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('prescriber', sa.String(length=160), nullable=True),
        sa.Column('withdrawal_period_days', sa.Integer(), nullable=False),
        sa.Column('treated_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('dose > 0', name='ck_fish_treatment_dose_positive'),
        sa.CheckConstraint('withdrawal_period_days >= 0', name='ck_fish_treatment_withdrawal_nonnegative'),
    )
    op.create_index('ix_fish_treatments_cycle_id', 'fish_treatments', ['cycle_id'])

    op.create_table(
        'farm_inspections',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('inspected_on', sa.Date(), nullable=False),
        sa.Column('checklist_json', sa.Text(), nullable=False),
        sa.Column('observations', sa.Text(), nullable=False),
        sa.Column('issues', sa.Text(), nullable=True),
        sa.Column('corrective_actions', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_farm_inspections_unit_id', 'farm_inspections', ['unit_id'])

    op.create_table(
        'farm_feeding_profile_approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('species', sa.String(length=20), nullable=False),
        sa.Column('profile_version', sa.String(length=40), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        'ix_farm_feeding_profile_approvals_lookup',
        'farm_feeding_profile_approvals',
        ['farm_id', 'species', 'active'],
    )

    op.create_table(
        'feeding_recommendations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('farm_id', sa.Integer(), sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('production_units.id'), nullable=False),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('feed_id', sa.Integer(), sa.ForeignKey('feed_products.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('profile_version', sa.String(length=40), nullable=False),
        sa.Column('profile_approval_id', sa.Integer(), sa.ForeignKey('farm_feeding_profile_approvals.id'), nullable=False),
        sa.Column('sampling_id', sa.Integer(), sa.ForeignKey('fish_samples.id'), nullable=True),
        sa.Column('water_quality_id', sa.Integer(), sa.ForeignKey('water_quality_records.id'), nullable=True),
        sa.Column('estimated_live_count', sa.Integer(), nullable=False),
        sa.Column('average_weight_g', sa.Float(), nullable=False),
        sa.Column('estimated_biomass_kg', sa.Float(), nullable=False),
        sa.Column('daily_rate_pct', sa.Float(), nullable=False),
        sa.Column('daily_ration_kg', sa.Float(), nullable=False),
        sa.Column('session_count', sa.Integer(), nullable=False),
        sa.Column('session_ration_kg', sa.Float(), nullable=False),
        sa.Column('pellet_size_min_mm', sa.Float(), nullable=False),
        sa.Column('pellet_size_max_mm', sa.Float(), nullable=False),
        sa.Column('inputs_json', sa.Text(), nullable=False),
        sa.Column('warnings_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_feeding_recommendations_cycle_id', 'feeding_recommendations', ['cycle_id'])

    with op.batch_alter_table('feed_ledger') as batch_op:
        batch_op.add_column(sa.Column('recommendation_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('session_number', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_feed_ledger_recommendation_id_feeding_recommendations',
            'feeding_recommendations',
            ['recommendation_id'],
            ['id'],
        )


def downgrade():
    raise RuntimeError(
        'Downgrade disabled to protect Phase One operational and review records. '
        'Restore a verified backup instead.'
    )
