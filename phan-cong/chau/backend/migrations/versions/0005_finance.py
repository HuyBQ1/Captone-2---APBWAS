"""Cost history, order identifiers and monthly finance inputs."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind()
    schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    columns={x['name'] for x in sa.inspect(c).get_columns('sales',schema=schema)}
    for column in [sa.Column('unit_cost',sa.Numeric(15,0),nullable=True),sa.Column('order_number',sa.String(100),nullable=True)]:
        if column.name not in columns:op.add_column('sales',column)
    if 'ix_sales_order_number' not in {i['name'] for i in sa.inspect(c).get_indexes('sales',schema=schema)}:
        op.create_index('ix_sales_order_number','sales',['order_number'])
    for name in ['expenses','finance_periods','finance_imports']:
        if name not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables[name].create(c,checkfirst=False)

def downgrade():
    raise RuntimeError('Restore a verified backup to retain financial inputs.')
