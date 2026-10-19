import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text, Numeric, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
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

class User(Identity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(ForeignKey('roles.name'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class AuthSession(Identity, Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())

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

class Product(Identity, Base):
    __tablename__ = 'products'
    sku: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    price: Mapped[float] = mapped_column(Numeric(15, 0))

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

class DocumentChunk(Identity, Base):
    __tablename__ = 'document_chunks'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list] = mapped_column(Vector(384).with_variant(JSON, 'sqlite'))
    model: Mapped[str] = mapped_column(String(120), index=True)

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
