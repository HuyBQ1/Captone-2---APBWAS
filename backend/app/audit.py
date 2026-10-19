import hashlib, hmac, json
from sqlalchemy import select, text
from .models import AuditLog, now
from .auth import utc
from .config import settings

def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if any(s in k.lower() for s in ('password','secret','token','api_key','authorization')) else redact(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

def digest(previous, actor, event, resource, correlation, payload, created_at):
    raw = json.dumps([previous, actor, event, resource, correlation, payload, utc(created_at).isoformat()], sort_keys=True, ensure_ascii=False).encode()
    return hmac.new(settings.audit_key.encode(), raw, hashlib.sha256).hexdigest()

def audit(db, user, event, resource='', payload=None, correlation=''):
    # Serialize the chain across API and worker processes, transaction scoped.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(730019)'))
    last = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    previous = last.hash if last else '0'*64
    actor = user.id if hasattr(user, 'id') else str(user)
    payload = redact(payload or {})
    created_at=now()
    row = AuditLog(actor=actor,event=event,resource=resource,correlation_id=correlation or resource,
                   payload=payload,previous_hash=previous,created_at=created_at,hash=digest(previous,actor,event,resource,correlation or resource,payload,created_at))
    db.add(row)
    db.flush()
    return row

def verify(db):
    previous = '0'*64
    for row in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        if row.previous_hash != previous or row.hash != digest(previous,row.actor,row.event,row.resource,row.correlation_id,row.payload,row.created_at):
            return False
        previous = row.hash
    return True
