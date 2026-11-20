"""Owned generated files attached to confirmed mail drafts."""
from alembic import op
import sqlalchemy as sa
revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();schema=c.execute(sa.text('SELECT current_schema()')).scalar() if c.dialect.name=='postgresql' else None
    if 'attachment_ids' not in {v['name'] for v in sa.inspect(c).get_columns('mail_campaigns',schema=schema)}:
        op.add_column('mail_campaigns',sa.Column('attachment_ids',sa.JSON(),nullable=False,server_default=sa.text("'[]'")))

def downgrade():
    c=op.get_bind()
    rows=c.execute(sa.text('SELECT attachment_ids FROM mail_campaigns')).all()
    import json
    if any((json.loads(v) if isinstance(v,str) else v) for (v,) in rows):raise RuntimeError('Mail attachments exist; preserve history before downgrade.')
    op.drop_column('mail_campaigns','attachment_ids')
