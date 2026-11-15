"""Product descriptions and database-backed images."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    connection=op.get_bind()
    schema=connection.execute(sa.text('SELECT current_schema()')).scalar() if connection.dialect.name=='postgresql' else None
    if 'description' not in {c['name'] for c in sa.inspect(connection).get_columns('products',schema=schema)}:
        op.add_column('products',sa.Column('description',sa.Text(),nullable=False,server_default=''))
    if 'product_images' not in sa.inspect(connection).get_table_names(schema=schema):
        Base.metadata.tables['product_images'].create(connection,checkfirst=False)

def downgrade():
    raise RuntimeError('Restore a verified backup to retain product images.')
