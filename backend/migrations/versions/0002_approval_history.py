"""Persist approval parameter snapshots for revision history."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    connection=op.get_bind()
    # 0001's initial metadata also supports brand new databases on this release.
    if 'arguments' not in {column['name'] for column in sa.inspect(connection).get_columns('approval_decisions')}:
        op.add_column('approval_decisions',sa.Column('arguments',sa.JSON(),nullable=False,server_default='{}'))

def downgrade():
    op.drop_column('approval_decisions','arguments')
