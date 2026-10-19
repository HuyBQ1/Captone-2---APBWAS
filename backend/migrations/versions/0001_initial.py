"""Initial schema, vector index, append-only audit."""
from alembic import op
from app.db import Base
from app import models

revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    connection=op.get_bind()
    if connection.dialect.name=='postgresql': op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    Base.metadata.create_all(connection)
    if connection.dialect.name=='postgresql':
        op.execute('CREATE INDEX document_chunks_vector_idx ON document_chunks USING hnsw (embedding vector_cosine_ops)')
        op.execute("CREATE FUNCTION protect_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END $$")
        op.execute('CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION protect_audit()')

def downgrade():
    connection=op.get_bind()
    if connection.dialect.name=='postgresql':
        op.execute('DROP TRIGGER IF EXISTS audit_append_only ON audit_logs')
        op.execute('DROP FUNCTION IF EXISTS protect_audit()')
    Base.metadata.drop_all(connection)
