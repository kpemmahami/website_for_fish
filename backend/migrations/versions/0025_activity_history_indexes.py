
"""Index existing operational history dates and record links."""
from alembic import op

revision = '0025_activity_history_indexes'
down_revision = '0024_operational_feeding'
branch_labels = None
depends_on = None

INDEXES = (
    ('ix_audit_entity_record_action', 'audit_logs', ['entity_type','entity_id','action']),
    ('ix_evidence_farm_record', 'record_evidence', ['farm_id','record_type','record_id']),
    ('ix_ledger_cycle_event_day', 'feed_ledger', ['cycle_id','event_type','occurred_on']),
    ('ix_mortality_cycle_day', 'mortality_records', ['cycle_id','observed_on']),
    ('ix_samples_cycle_day', 'fish_samples', ['cycle_id','sampled_on']),
    ('ix_water_unit_observed', 'water_quality_records', ['unit_id','observed_at']),
    ('ix_harvest_farm_day', 'harvest_lots', ['farm_id','harvested_on']),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
