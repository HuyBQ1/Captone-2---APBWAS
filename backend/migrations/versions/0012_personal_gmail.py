"""Personal Gmail connection is separate from campaign sending."""
from alembic import op
import sqlalchemy as sa

revision='0012'
down_revision='0011'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind()
    roles=sa.table('roles',sa.column('name',sa.String),sa.column('permissions',sa.JSON))
    catalog=sa.table('permissions',sa.column('name',sa.String))
    if not c.execute(sa.select(catalog).where(catalog.c.name=='mail.connect')).first():
        c.execute(catalog.insert().values(name='mail.connect'))
    for name,perms in c.execute(sa.select(roles.c.name,roles.c.permissions)).all():
        if name in ('Admin','Manager','Employee') and 'mail.connect' not in perms:
            c.execute(roles.update().where(roles.c.name==name).values(permissions=perms+['mail.connect']))

def downgrade():
    c=op.get_bind()
    roles=sa.table('roles',sa.column('name',sa.String),sa.column('permissions',sa.JSON))
    for name,perms in c.execute(sa.select(roles.c.name,roles.c.permissions)).all():
        c.execute(roles.update().where(roles.c.name==name).values(permissions=[p for p in perms if p!='mail.connect']))
    c.execute(sa.text("DELETE FROM permissions WHERE name='mail.connect'"))
