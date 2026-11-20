"""Pending employee registrations and durable private recovery delivery."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0013'
down_revision='0012'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    if 'registration_pending' not in {x['name'] for x in sa.inspect(c).get_columns('users',schema=schema)}:
        op.add_column('users',sa.Column('registration_pending',sa.Boolean(),nullable=False,server_default=sa.false()))
    for name in ['auth_request_attempts','account_emails']:
        if name not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables[name].create(c,checkfirst=False)

def downgrade():
    c=op.get_bind()
    if c.execute(sa.text('SELECT count(*) FROM account_emails')).scalar() or c.execute(sa.text('SELECT count(*) FROM users WHERE registration_pending=true')).scalar():
        raise RuntimeError('Preserve registration and recovery history before downgrade.')
    op.drop_table('account_emails');op.drop_table('auth_request_attempts');op.drop_column('users','registration_pending')
