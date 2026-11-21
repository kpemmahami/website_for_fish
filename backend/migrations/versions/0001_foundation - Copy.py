"""Initial schema and additive upgrade of existing starter database.

Existing users and farms are preserved. This migration supports both a new
empty database and the original two-table starter database.
"""
from alembic import op
import sqlalchemy as sa
revision = '0001_foundation'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if 'users' not in existing:
        op.create_table('users',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('full_name',sa.String(120),nullable=False),
            sa.Column('email',sa.String(255),nullable=False),
            sa.Column('password_hash',sa.String(255),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
        op.create_index('ix_users_email','users',['email'],unique=True)
    if 'farms' not in existing:
        op.create_table('farms',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('name',sa.String(150),nullable=False),
            sa.Column('region',sa.String(100),nullable=False),
            sa.Column('district',sa.String(100),nullable=False),
            sa.Column('farm_type',sa.String(30),nullable=False),
            sa.Column('species',sa.String(100),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
        op.create_index('ix_farms_owner_id','farms',['owner_id'])
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('farms')}
    for name, typ in [
        ('latitude',sa.Float()),('longitude',sa.Float()),
        ('gps_accuracy_m',sa.Float()),('location_method',sa.String(20)),
        ('gps_captured_at',sa.DateTime(timezone=True)),
        ('archived_at',sa.DateTime(timezone=True))]:
        if name not in existing_columns:
            op.add_column('farms',sa.Column(name,typ,nullable=True))
    if 'production_units' not in existing:
        op.create_table('production_units',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('farm_id',sa.Integer(),sa.ForeignKey('farms.id'),nullable=False),
            sa.Column('name',sa.String(120),nullable=False),
            sa.Column('unit_type',sa.String(20),nullable=False),
            sa.Column('capacity_m3',sa.Float(),nullable=True),
            sa.Column('latitude',sa.Float(),nullable=True),
            sa.Column('longitude',sa.Float(),nullable=True),
            sa.Column('notes',sa.Text(),nullable=True),
            sa.Column('is_active',sa.Boolean(),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
        op.create_index('ix_production_units_farm_id','production_units',['farm_id'])
    if 'audit_logs' not in existing:
        op.create_table('audit_logs',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('action',sa.String(40),nullable=False),
            sa.Column('entity_type',sa.String(40),nullable=False),
            sa.Column('entity_id',sa.Integer(),nullable=False),
            sa.Column('details',sa.Text(),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
        op.create_index('ix_audit_logs_actor_id','audit_logs',['actor_id'])

def downgrade():
    raise RuntimeError('Downgrade disabled to protect existing farm records; restore a backup instead.')
