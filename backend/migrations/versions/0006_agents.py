"""Additive Agent builder, ownership and immutable versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from app.db import Base
from app import models
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    c=op.get_bind();pg=c.dialect.name=='postgresql'
    schema=c.execute(sa.text('SELECT current_schema()')).scalar() if pg else None
    def tables():return sa.inspect(c).get_table_names(schema=schema)
    if 'workspaces' not in tables():Base.metadata.tables['workspaces'].create(c,checkfirst=False)
    workspace=Base.metadata.tables['workspaces']
    if not c.execute(sa.select(workspace.c.id).where(workspace.c.id=='primary')).first():c.execute(workspace.insert().values(id='primary',name='Primary company workspace'))
    for name in ['users','documents']:
        if 'workspace_id' not in {i['name'] for i in sa.inspect(c).get_columns(name,schema=schema)}:
            op.add_column(name,sa.Column('workspace_id',sa.String(36),nullable=False,server_default='primary'))
            if pg:op.create_foreign_key(name+'_workspace_fk',name,'workspaces',['workspace_id'],['id'])
        if 'ix_'+name+'_workspace_id' not in {i['name'] for i in sa.inspect(c).get_indexes(name,schema=schema)}:
            op.create_index('ix_'+name+'_workspace_id',name,['workspace_id'])
    for name in ['agents','agent_configs','agent_tools','agent_knowledge','agent_versions','agent_draft_revisions']:
        if name not in tables():Base.metadata.tables[name].create(c,checkfirst=False)
    agents=Base.metadata.tables['agents'];configs=Base.metadata.tables['agent_configs'];drafts=Base.metadata.tables['agent_draft_revisions']
    for row in c.execute(sa.select(agents.c.id,agents.c.name,agents.c.description,agents.c.avatar,agents.c.visibility,agents.c.owner_id,configs.c.config,configs.c.revision).join(configs,configs.c.agent_id==agents.c.id)).mappings():
        if not c.execute(sa.select(drafts.c.agent_id).where(drafts.c.agent_id==row['id'],drafts.c.revision==row['revision'])).first():
            c.execute(drafts.insert().values(agent_id=row['id'],revision=row['revision'],created_by=row['owner_id'],snapshot={**row['config'],**{k:row[k] for k in ['name','description','avatar','visibility']}}))
    additions=[sa.Column('agent_id',sa.String(36),nullable=True),sa.Column('agent_version_id',sa.String(36),nullable=True),
               sa.Column('agent_draft_revision',sa.Integer(),nullable=True),sa.Column('agent_snapshot',sa.JSON().with_variant(JSONB,'postgresql'),nullable=True)]
    cols={i['name'] for i in sa.inspect(c).get_columns('workflows',schema=schema)}
    for column in additions:
        if column.name not in cols:
            op.add_column('workflows',column)
            if pg and column.name in ('agent_id','agent_version_id'):
                op.create_foreign_key('workflows_'+column.name+'_fk','workflows','agents' if column.name=='agent_id' else 'agent_versions',[column.name],['id'])
    if 'ix_workflows_agent_id' not in {i['name'] for i in sa.inspect(c).get_indexes('workflows',schema=schema)}:
        op.create_index('ix_workflows_agent_id','workflows',['agent_id'])
    roles=sa.table('roles',sa.column('name',sa.String),sa.column('permissions',sa.JSON))
    catalog=sa.table('permissions',sa.column('name',sa.String))
    for permission in ['agents.manage','agents.run']:
        if not c.execute(sa.select(catalog).where(catalog.c.name==permission)).first():c.execute(catalog.insert().values(name=permission))
    for name,existing in c.execute(sa.select(roles.c.name,roles.c.permissions)).all():
        additions=['agents.run']+(['agents.manage'] if name in ('Admin','Manager') else [])
        c.execute(roles.update().where(roles.c.name==name).values(permissions=list(dict.fromkeys(existing+additions))))
    if pg:
        op.execute("CREATE OR REPLACE FUNCTION protect_agent_version() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'agent_versions are immutable'; END $$")
        op.execute('DROP TRIGGER IF EXISTS agent_version_immutable ON agent_versions')
        op.execute('CREATE TRIGGER agent_version_immutable BEFORE UPDATE OR DELETE ON agent_versions FOR EACH ROW EXECUTE FUNCTION protect_agent_version()')
        op.execute('DROP TRIGGER IF EXISTS agent_draft_immutable ON agent_draft_revisions')
        op.execute('CREATE TRIGGER agent_draft_immutable BEFORE UPDATE OR DELETE ON agent_draft_revisions FOR EACH ROW EXECUTE FUNCTION protect_agent_version()')

def downgrade():
    c=op.get_bind()
    if c.execute(sa.text('SELECT count(*) FROM agents')).scalar() or c.execute(sa.text('SELECT count(*) FROM agent_versions')).scalar():
        raise RuntimeError('Agent records exist. Export/restore a verified backup rather than dropping execution history.')
    if c.dialect.name=='postgresql':
        op.execute('DROP TRIGGER IF EXISTS agent_version_immutable ON agent_versions');op.execute('DROP TRIGGER IF EXISTS agent_draft_immutable ON agent_draft_revisions');op.execute('DROP FUNCTION IF EXISTS protect_agent_version()')
        schema=c.execute(sa.text('SELECT current_schema()')).scalar()
        for fk in sa.inspect(c).get_foreign_keys('workflows',schema=schema):
            if fk['constrained_columns'] in (['agent_id'],['agent_version_id']):op.drop_constraint(fk['name'],'workflows',type_='foreignkey')
    op.drop_index('ix_workflows_agent_id',table_name='workflows')
    for key in ['agent_snapshot','agent_draft_revision','agent_version_id','agent_id']:op.drop_column('workflows',key)
    for name in ['agent_knowledge','agent_tools','agent_configs','agent_draft_revisions','agent_versions','agents']:op.drop_table(name)
    # Retain additive workspace ownership and permission catalog on downgrade:
    # other modules/users may already reference them. No company data is dropped.
