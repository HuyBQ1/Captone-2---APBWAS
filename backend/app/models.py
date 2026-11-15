import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text, Numeric, UniqueConstraint, CheckConstraint, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base, UTCDateTime

def now():
    return datetime.now(timezone.utc)

class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, index=True)

class Role(Base):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String(20), primary_key=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)

class Permission(Base):
    __tablename__ = 'permissions'
    name: Mapped[str] = mapped_column(String(80), primary_key=True)

class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    name: Mapped[str] = mapped_column(String(120))

class User(Identity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(180), unique=True)
    delivery_email: Mapped[str | None] = mapped_column(String(180),nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(ForeignKey('roles.name'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registration_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    phone: Mapped[str] = mapped_column(String(30), default='')
    department: Mapped[str] = mapped_column(String(100), default='')
    job_title: Mapped[str] = mapped_column(String(100), default='')
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),default='primary',server_default='primary',index=True)

class Agent(Identity, Base):
    __tablename__ = 'agents'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000),default='')
    avatar: Mapped[str] = mapped_column(String(30),default='sparkles')
    visibility: Mapped[str] = mapped_column(String(20),default='private')
    status: Mapped[str] = mapped_column(String(20),default='draft',index=True)
    published_version: Mapped[int | None] = mapped_column(Integer,nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=now)

class AgentConfig(Base):
    __tablename__ = 'agent_configs'
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'),primary_key=True)
    revision: Mapped[int] = mapped_column(Integer,default=1)
    config: Mapped[dict] = mapped_column(JSON().with_variant(JSONB,'postgresql'))

class AgentTool(Base):
    __tablename__ = 'agent_tools'
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'),primary_key=True)
    tool: Mapped[str] = mapped_column(String(80),primary_key=True)

class AgentKnowledge(Base):
    __tablename__ = 'agent_knowledge'
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'),primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'),primary_key=True)

class AgentVersion(Identity, Base):
    __tablename__ = 'agent_versions'
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'),index=True)
    number: Mapped[int] = mapped_column(Integer)
    draft_revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB,'postgresql'))
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (UniqueConstraint('agent_id','number'),)

class AgentDraftRevision(Base):
    __tablename__ = 'agent_draft_revisions'
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'),primary_key=True)
    revision: Mapped[int] = mapped_column(Integer,primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB,'postgresql'))
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=now)

class AuthSession(Identity, Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    device: Mapped[str] = mapped_column(String(250), default='')
    ip_address: Mapped[str] = mapped_column(String(64), default='')

class AccountToken(Identity, Base):
    __tablename__ = 'account_tokens'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

class AuthRequestAttempt(Identity, Base):
    __tablename__ = 'auth_request_attempts'
    kind: Mapped[str] = mapped_column(String(20),index=True)
    email_hash: Mapped[str] = mapped_column(String(64),index=True)
    ip_hash: Mapped[str] = mapped_column(String(64),index=True)

class AccountEmail(Identity, Base):
    __tablename__ = 'account_emails'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    token_id: Mapped[str] = mapped_column(ForeignKey('account_tokens.id'),unique=True)
    sender_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    recipient: Mapped[str] = mapped_column(String(180))
    payload_ciphertext: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20),default='queued',index=True)
    remote_id: Mapped[str | None] = mapped_column(String(255),nullable=True)
    error: Mapped[str | None] = mapped_column(String(300),nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)

class Conversation(Identity, Base):
    __tablename__ = 'conversations'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(120))
    context: Mapped[dict] = mapped_column(JSON, default=dict)

class Message(Identity, Base):
    __tablename__ = 'messages'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)

class Workflow(Identity, Base):
    __tablename__ = 'workflows'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey('conversations.id'), nullable=True)
    request: Mapped[str] = mapped_column(Text)
    model_ref: Mapped[str | None] = mapped_column(String(256),nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey('agents.id'),nullable=True,index=True)
    agent_version_id: Mapped[str | None] = mapped_column(ForeignKey('agent_versions.id'),nullable=True)
    agent_draft_revision: Mapped[int | None] = mapped_column(Integer,nullable=True)
    agent_snapshot: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB,'postgresql'),nullable=True)

class WorkflowStep(Identity, Base):
    __tablename__ = 'workflow_steps'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('workflow_id', 'position'),)

class ToolExecution(Identity, Base):
    __tablename__ = 'tool_executions'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    duration_ms: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint('workflow_id', 'position'),)

class WorkflowEvent(Identity, Base):
    __tablename__ = 'workflow_events'
    sequence: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), index=True)
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)

class Notification(Identity, Base):
    __tablename__ = 'notifications'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'))
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (UniqueConstraint('user_id','workflow_id','kind'),)

class Product(Identity, Base):
    __tablename__ = 'products'
    sku: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    price: Mapped[float] = mapped_column(Numeric(15, 0))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default='')

class ProductImage(Base):
    __tablename__ = 'product_images'
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    mime_type: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)

class Inventory(Base):
    __tablename__ = 'inventory'
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer, default=20)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint('quantity >= 0'),)

class Sale(Identity, Base):
    __tablename__ = 'sales'
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    date: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[float] = mapped_column(Numeric(15, 0))
    reference: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(15,0), nullable=True)
    order_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

class Expense(Identity, Base):
    __tablename__ = 'expenses'
    reference: Mapped[str] = mapped_column(String(100),unique=True)
    date: Mapped[datetime] = mapped_column(UTCDateTime(),index=True)
    category: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Numeric(15,0))
    note: Mapped[str] = mapped_column(String(500),default='')
    __table_args__ = (CheckConstraint('amount >= 0'),)

class FinancePeriod(Base):
    __tablename__ = 'finance_periods'
    month: Mapped[str] = mapped_column(String(7),primary_key=True)
    expenses_confirmed: Mapped[bool] = mapped_column(Boolean,default=False)
    version: Mapped[int] = mapped_column(Integer,default=1)

class FinanceImport(Identity, Base):
    __tablename__ = 'finance_imports'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    month: Mapped[str] = mapped_column(String(7))
    preview: Mapped[dict] = mapped_column(JSON)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20),default='preview')

class InventoryMovement(Identity, Base):
    __tablename__ = 'inventory_movements'
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    before: Mapped[int] = mapped_column(Integer)
    after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(250))

class Document(Identity, Base):
    __tablename__ = 'documents'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(30), default='uploaded', index=True)
    scope: Mapped[str] = mapped_column(String(30), default='all')
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, default='')
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),default='primary',server_default='primary',index=True)

class DocumentChunk(Identity, Base):
    __tablename__ = 'document_chunks'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list] = mapped_column(Vector(384).with_variant(JSON, 'sqlite'))
    model: Mapped[str] = mapped_column(String(120), index=True)

class DocumentFile(Base):
    __tablename__ = 'document_files'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)

class Approval(Identity, Base):
    __tablename__ = 'approval_requests'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    tool: Mapped[str] = mapped_column(String(80), default='apply_approved_inventory_adjustment')
    arguments: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    reason: Mapped[str] = mapped_column(Text, default='Hành động ghi thay đổi tồn kho cần phê duyệt.')

class ApprovalDecision(Identity, Base):
    __tablename__ = 'approval_decisions'
    approval_id: Mapped[str] = mapped_column(ForeignKey('approval_requests.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    revision: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default='')
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)

class Report(Identity, Base):
    __tablename__ = 'reports'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30), default='revenue')
    data: Mapped[dict] = mapped_column(JSON)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    event: Mapped[str] = mapped_column(String(80), index=True)
    resource: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    previous_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

class UsageRecord(Identity, Base):
    __tablename__ = 'usage_records'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), unique=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)

class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

class Job(Identity, Base):
    __tablename__ = 'jobs'
    resource: Mapped[str] = mapped_column(String(36), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

class GmailConnection(Base):
    __tablename__ = 'gmail_connections'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),index=True)
    email: Mapped[str] = mapped_column(String(180))
    google_sub: Mapped[str] = mapped_column(String(255))
    credentials_ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    scopes: Mapped[list] = mapped_column(JSON)
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=now)

class GmailOAuthState(Base):
    __tablename__ = 'gmail_oauth_states'
    digest: Mapped[str] = mapped_column(String(64),primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used: Mapped[bool] = mapped_column(Boolean,default=False)

class GmailSendAttempt(Identity, Base):
    __tablename__ = 'gmail_send_attempts'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    idempotency_key: Mapped[str] = mapped_column(String(100),unique=True)
    recipient: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20),default='sending')
    remote_id: Mapped[str | None] = mapped_column(String(255),nullable=True)

class MailCampaign(Identity, Base):
    __tablename__ = 'mail_campaigns'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey('workflows.id'),nullable=True,unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100),unique=True)
    subject: Mapped[str] = mapped_column(String(180))
    body_text: Mapped[str] = mapped_column(Text)
    attachment_ids: Mapped[list] = mapped_column(JSON,default=list)
    requested_ids: Mapped[list | None] = mapped_column(JSON,nullable=True)
    skipped: Mapped[list] = mapped_column(JSON,default=list)
    revision: Mapped[int] = mapped_column(Integer,default=1)
    status: Mapped[str] = mapped_column(String(20),default='draft',index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean,default=False)
    sender_email: Mapped[str | None] = mapped_column(String(180),nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    error: Mapped[str | None] = mapped_column(String(500),nullable=True)

class MailDelivery(Identity, Base):
    __tablename__ = 'mail_deliveries'
    campaign_id: Mapped[str] = mapped_column(ForeignKey('mail_campaigns.id'),index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    recipient: Mapped[str] = mapped_column(String(180))
    recipient_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20),default='pending',index=True)
    attempted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    remote_id: Mapped[str | None] = mapped_column(String(255),nullable=True)
    error: Mapped[str | None] = mapped_column(String(500),nullable=True)
    __table_args__ = (UniqueConstraint('campaign_id','recipient'),)

class LLMProvider(Identity, Base):
    __tablename__ = 'llm_providers'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),index=True)
    name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_ciphertext: Mapped[str] = mapped_column(Text)
    model_ids: Mapped[list] = mapped_column(JSON,default=list)
    allowed_roles: Mapped[list] = mapped_column(JSON,default=lambda:['Admin','Manager'])
    enabled: Mapped[bool] = mapped_column(Boolean,default=True)
    json_mode: Mapped[bool] = mapped_column(Boolean,default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer,default=45)
    revision: Mapped[int] = mapped_column(Integer,default=1)
    last_test_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20),nullable=True)

class GeneratedFile(Identity, Base):
    __tablename__ = 'generated_files'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'),index=True)
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(180))
    filename: Mapped[str] = mapped_column(String(180))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[dict] = mapped_column(JSON,default=dict)
    __table_args__=(UniqueConstraint('workflow_id','kind'),)
