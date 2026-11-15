"""Persistent employee accounts, original documents, and business records."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    connection=op.get_bind()
    schema=connection.execute(sa.text('SELECT current_schema()')).scalar() if connection.dialect.name=='postgresql' else None
    additions={
        'users': [sa.Column('phone',sa.String(30),nullable=False,server_default=''),sa.Column('department',sa.String(100),nullable=False,server_default=''),
                  sa.Column('job_title',sa.String(100),nullable=False,server_default=''),sa.Column('preferences',sa.JSON(),nullable=False,server_default='{}'),
                  sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column('last_login_at',sa.DateTime(timezone=True),nullable=True)],
        'auth_sessions':[sa.Column('device',sa.String(250),nullable=False,server_default=''),sa.Column('ip_address',sa.String(64),nullable=False,server_default='')],
        'products':[sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column('version',sa.Integer(),nullable=False,server_default='1')],
        'sales':[sa.Column('reference',sa.String(100),nullable=True)]}
    for table,columns in additions.items():
        existing={c['name'] for c in sa.inspect(connection).get_columns(table,schema=schema)}
        for column in columns:
            if column.name not in existing:op.add_column(table,column)
    indexes={i['name'] for i in sa.inspect(connection).get_indexes('sales',schema=schema)}
    if 'sales_reference_unique' not in indexes:op.create_index('sales_reference_unique','sales',['reference'],unique=True)
    for table in ['account_tokens','document_files','inventory_movements','notifications']:
        if table not in sa.inspect(connection).get_table_names(schema=schema):Base.metadata.tables[table].create(connection,checkfirst=False)
    roles=sa.table('roles',sa.column('name',sa.String),sa.column('permissions',sa.JSON))
    permissions=connection.execute(sa.select(roles.c.permissions).where(roles.c.name=='Admin')).scalar()
    if permissions is not None and 'business.manage' not in permissions:
        connection.execute(roles.update().where(roles.c.name=='Admin').values(permissions=permissions+['business.manage']))
    catalog=sa.table('permissions',sa.column('name',sa.String))
    if not connection.execute(sa.select(catalog).where(catalog.c.name=='business.manage')).first():
        connection.execute(catalog.insert().values(name='business.manage'))

def downgrade():
    raise RuntimeError('0003 contains business/account data; restore a verified backup instead of dropping data.')
