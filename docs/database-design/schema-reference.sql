-- APBWAS schema reference from SQLAlchemy metadata on 2026-10-31.

-- Review only. Deploy with Alembic; ORM defaults are not server defaults.

CREATE EXTENSION IF NOT EXISTS vector;


CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor VARCHAR(80) NOT NULL, 
	event VARCHAR(80) NOT NULL, 
	resource VARCHAR(80) NOT NULL, 
	correlation_id VARCHAR(80) NOT NULL, 
	payload JSON NOT NULL, 
	previous_hash VARCHAR(64) NOT NULL, 
	hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_audit_logs_correlation_id ON audit_logs (correlation_id);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_event ON audit_logs (event);


CREATE TABLE jobs (
	resource VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	lease_until TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (resource)
)

;

CREATE INDEX ix_jobs_created_at ON jobs (created_at);

CREATE INDEX ix_jobs_status ON jobs (status);


CREATE TABLE permissions (
	name VARCHAR(80) NOT NULL, 
	PRIMARY KEY (name)
)

;


CREATE TABLE products (
	sku VARCHAR(30) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	category VARCHAR(80) NOT NULL, 
	price NUMERIC(15, 0) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (sku)
)

;

CREATE INDEX ix_products_created_at ON products (created_at);


CREATE TABLE roles (
	name VARCHAR(20) NOT NULL, 
	permissions JSON NOT NULL, 
	PRIMARY KEY (name)
)

;


CREATE TABLE system_settings (
	key VARCHAR(80) NOT NULL, 
	value JSON NOT NULL, 
	PRIMARY KEY (key)
)

;


CREATE TABLE inventory (
	product_id VARCHAR(36) NOT NULL, 
	quantity INTEGER NOT NULL, 
	threshold INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (product_id), 
	CHECK (quantity >= 0), 
	FOREIGN KEY(product_id) REFERENCES products (id)
)

;


CREATE TABLE sales (
	product_id VARCHAR(36) NOT NULL, 
	date TIMESTAMP WITH TIME ZONE NOT NULL, 
	quantity INTEGER NOT NULL, 
	revenue NUMERIC(15, 0) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES products (id)
)

;

CREATE INDEX ix_sales_created_at ON sales (created_at);

CREATE INDEX ix_sales_date ON sales (date);

CREATE INDEX ix_sales_product_id ON sales (product_id);


CREATE TABLE users (
	email VARCHAR(180) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	active BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(role) REFERENCES roles (name)
)

;

CREATE INDEX ix_users_created_at ON users (created_at);


CREATE TABLE auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_auth_sessions_created_at ON auth_sessions (created_at);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);


CREATE TABLE conversations (
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	context JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_conversations_created_at ON conversations (created_at);

CREATE INDEX ix_conversations_user_id ON conversations (user_id);


CREATE TABLE documents (
	user_id VARCHAR(36) NOT NULL, 
	name VARCHAR(250) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	scope VARCHAR(30) NOT NULL, 
	path TEXT, 
	content TEXT NOT NULL, 
	chunks INTEGER NOT NULL, 
	error TEXT, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_documents_created_at ON documents (created_at);

CREATE INDEX ix_documents_status ON documents (status);


CREATE TABLE document_chunks (
	document_id VARCHAR(36) NOT NULL, 
	content TEXT NOT NULL, 
	page INTEGER, 
	position INTEGER NOT NULL, 
	embedding VECTOR(384) NOT NULL, 
	model VARCHAR(120) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_document_chunks_created_at ON document_chunks (created_at);

CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id);

CREATE INDEX ix_document_chunks_model ON document_chunks (model);


CREATE TABLE messages (
	conversation_id VARCHAR(36) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);

CREATE INDEX ix_messages_created_at ON messages (created_at);


CREATE TABLE workflows (
	user_id VARCHAR(36) NOT NULL, 
	conversation_id VARCHAR(36), 
	request TEXT NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	plan JSON NOT NULL, 
	result JSON NOT NULL, 
	error TEXT, 
	checkpoint INTEGER NOT NULL, 
	tokens INTEGER NOT NULL, 
	duration_ms INTEGER NOT NULL, 
	cancel_requested BOOLEAN NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	deadline TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id), 
	UNIQUE (idempotency_key)
)

;

CREATE INDEX ix_workflows_created_at ON workflows (created_at);

CREATE INDEX ix_workflows_status ON workflows (status);

CREATE INDEX ix_workflows_user_id ON workflows (user_id);


CREATE TABLE approval_requests (
	workflow_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	tool VARCHAR(80) NOT NULL, 
	arguments JSON NOT NULL, 
	revision INTEGER NOT NULL, 
	approved_revision INTEGER, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reason TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workflow_id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_approval_requests_created_at ON approval_requests (created_at);

CREATE INDEX ix_approval_requests_status ON approval_requests (status);


CREATE TABLE reports (
	workflow_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	data JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workflow_id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_reports_created_at ON reports (created_at);

CREATE INDEX ix_reports_user_id ON reports (user_id);


CREATE TABLE tool_executions (
	workflow_id VARCHAR(36) NOT NULL, 
	position INTEGER NOT NULL, 
	tool VARCHAR(80) NOT NULL, 
	arguments JSON NOT NULL, 
	output JSON NOT NULL, 
	duration_ms INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workflow_id, position), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
)

;

CREATE INDEX ix_tool_executions_created_at ON tool_executions (created_at);

CREATE INDEX ix_tool_executions_workflow_id ON tool_executions (workflow_id);


CREATE TABLE usage_records (
	user_id VARCHAR(36) NOT NULL, 
	workflow_id VARCHAR(36) NOT NULL, 
	tokens INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (workflow_id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
)

;

CREATE INDEX ix_usage_records_created_at ON usage_records (created_at);

CREATE INDEX ix_usage_records_user_id ON usage_records (user_id);


CREATE TABLE workflow_events (
	sequence INTEGER NOT NULL, 
	workflow_id VARCHAR(36) NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	payload JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
)

;

CREATE INDEX ix_workflow_events_created_at ON workflow_events (created_at);

CREATE UNIQUE INDEX ix_workflow_events_sequence ON workflow_events (sequence);

CREATE INDEX ix_workflow_events_workflow_id ON workflow_events (workflow_id);


CREATE TABLE workflow_steps (
	workflow_id VARCHAR(36) NOT NULL, 
	position INTEGER NOT NULL, 
	tool VARCHAR(80) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	output JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workflow_id, position), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
)

;

CREATE INDEX ix_workflow_steps_created_at ON workflow_steps (created_at);

CREATE INDEX ix_workflow_steps_workflow_id ON workflow_steps (workflow_id);


CREATE TABLE approval_decisions (
	approval_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	revision INTEGER NOT NULL, 
	decision VARCHAR(20) NOT NULL, 
	reason TEXT NOT NULL, 
	arguments JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(approval_id) REFERENCES approval_requests (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_approval_decisions_approval_id ON approval_decisions (approval_id);

CREATE INDEX ix_approval_decisions_created_at ON approval_decisions (created_at);

CREATE INDEX document_chunks_vector_idx ON document_chunks USING hnsw (embedding vector_cosine_ops);

CREATE FUNCTION protect_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END $$;

CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION protect_audit();