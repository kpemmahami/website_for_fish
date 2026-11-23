"""Add operational feeding schedules independent of ration approval."""
from alembic import op
import sqlalchemy as sa

revision = '0024_operational_feeding'
down_revision = '0023_farm_expenses'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'operational_feeding_schedules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('stocking_cycles.id'), nullable=False),
        sa.Column('effective_on', sa.Date(), nullable=False),
        sa.Column('windows_json', sa.Text(), nullable=False),
        sa.UniqueConstraint('cycle_id', 'effective_on'),
    )
    op.create_index('ix_operational_feeding_schedules_cycle_id', 'operational_feeding_schedules', ['cycle_id'])
    with op.batch_alter_table('daily_feeding_plans') as batch:
        batch.alter_column('recommendation_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('schedule_id', sa.Integer()))
        batch.create_foreign_key('fk_daily_feeding_schedule', 'operational_feeding_schedules', ['schedule_id'], ['id'])


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve operational schedules and linked feeding records.')
