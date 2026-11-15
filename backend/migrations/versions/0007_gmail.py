"""User/workspace-scoped Gmail OAuth and delivery attempt tracking."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    for name in ['gmail_connections','gmail_oauth_states','gmail_send_attempts']:
        if name not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables[name].create(c,checkfirst=False)
    roles=sa.table('roles',sa.column('name',sa.String),sa.column('permissions',sa.JSON))
    catalog=sa.table('permissions',sa.column('name',sa.String))
    if not c.execute(sa.select(catalog).where(catalog.c.name=='mail.send')).first():c.execute(catalog.insert().values(name='mail.send'))
    for name,perms in c.execute(sa.select(roles.c.name,roles.c.permissions)).all():
        if name in ('Admin','Manager') and 'mail.send' not in perms:c.execute(roles.update().where(roles.c.name==name).values(permissions=perms+['mail.send']))

def downgrade():
    c=op.get_bind()
    for name in ['gmail_connections','gmail_oauth_states','gmail_send_attempts']:
        if c.execute(sa.text('SELECT count(*) FROM '+name)).scalar():raise RuntimeError('Gmail records exist; retain a verified backup before removing connection history.')
    for name in ['gmail_send_attempts','gmail_oauth_states','gmail_connections']:op.drop_table(name)
