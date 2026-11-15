"""Durable Word and Excel outputs owned by a workflow and workspace."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    if 'generated_files' not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables['generated_files'].create(c,checkfirst=False)

def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM generated_files')).scalar():raise RuntimeError('Generated files exist; preserve a verified backup before removing outputs.')
    op.drop_table('generated_files')
