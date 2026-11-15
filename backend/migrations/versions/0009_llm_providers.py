"""Workspace-scoped encrypted LLM connections and per-run model selection."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    if 'llm_providers' not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables['llm_providers'].create(c,checkfirst=False)
    if 'model_ref' not in {i['name'] for i in sa.inspect(c).get_columns('workflows',schema=schema)}:
        op.add_column('workflows',sa.Column('model_ref',sa.String(256),nullable=True))

def downgrade():
    c=op.get_bind()
    if c.execute(sa.text('SELECT count(*) FROM llm_providers')).scalar() or c.execute(sa.text('SELECT count(*) FROM workflows WHERE model_ref IS NOT NULL')).scalar():
        raise RuntimeError('LLM configuration/history exists; preserve a verified backup before removal.')
    op.drop_column('workflows','model_ref');op.drop_table('llm_providers')
