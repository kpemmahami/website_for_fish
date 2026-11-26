"""Assign institutions' staff and facility records to branches."""
from alembic import op
import sqlalchemy as sa

revision = '0043_branch_assignments'
down_revision = '0042_institution_branches'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('finance_institution_members', 'loan_applications'):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
            batch.create_foreign_key(f'fk_{table}_branch', 'institution_branches', ['branch_id'], ['id'])
            batch.create_index(f'ix_{table}_branch_id', ['branch_id'])


def downgrade():
    for table in ('loan_applications', 'finance_institution_members'):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f'ix_{table}_branch_id')
            batch.drop_constraint(f'fk_{table}_branch', type_='foreignkey')
            batch.drop_column('branch_id')
