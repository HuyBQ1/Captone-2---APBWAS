"""Employee delivery addresses and confirmed, durable bulk mail."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    if 'delivery_email' not in {i['name'] for i in sa.inspect(c).get_columns('users',schema=schema)}:
        op.add_column('users',sa.Column('delivery_email',sa.String(180),nullable=True))
    for name in ['mail_campaigns','mail_deliveries']:
        if name not in sa.inspect(c).get_table_names(schema=schema):Base.metadata.tables[name].create(c,checkfirst=False)

def downgrade():
    c=op.get_bind()
    if c.execute(sa.text('SELECT count(*) FROM mail_campaigns')).scalar() or c.execute(sa.text('SELECT count(*) FROM users WHERE delivery_email IS NOT NULL')).scalar():
        raise RuntimeError('Mail data exists; retain a verified backup before removing history.')
    op.drop_table('mail_deliveries');op.drop_table('mail_campaigns');op.drop_column('users','delivery_email')
