"""Add printable label details to finished lots."""
from alembic import op
import sqlalchemy as sa

revision = '0027_processing_label_details'
down_revision = '0026_fish_processing'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('processing_finished_lots',sa.Column('label_details',sa.Text(),nullable=False,server_default='{}'))


def downgrade():
    raise RuntimeError('Downgrade disabled to preserve recorded label details.')
