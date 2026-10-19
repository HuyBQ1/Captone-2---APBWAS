from datetime import timedelta
from sqlalchemy import select, func
import redis
from fastapi import HTTPException
from .models import SystemSetting, Workflow, UsageRecord, now
from .config import settings

DEFAULT_CONFIG = {'token_budget':100000,'request_limit':20,'max_steps':8,'timeout':60,'approval_hours':24,'approver_roles':['Admin','Manager']}
cache = redis.Redis.from_url(settings.redis_url,decode_responses=True,socket_connect_timeout=1,socket_timeout=1)

def configuration(db):
    row = db.get(SystemSetting,'limits')
    return {**DEFAULT_CONFIG,**(row.value if row else {})}

def quota(db,user):
    config = configuration(db)
    # Serialize reservations per user; persistent fallback when Redis is down.
    if db.bind.dialect.name == 'postgresql':
        db.execute(select(Workflow.id).where(Workflow.user_id == user.id).with_for_update())
        from sqlalchemy import text
        import hashlib
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(hashlib.sha256(user.id.encode()).hexdigest()[:8],16)})
    count = db.scalar(select(func.count()).select_from(Workflow).where(Workflow.user_id==user.id,Workflow.created_at>=now()-timedelta(minutes=1))) or 0
    used = db.scalar(select(func.coalesce(func.sum(UsageRecord.tokens),0)).where(UsageRecord.user_id==user.id,UsageRecord.created_at>=now()-timedelta(days=30))) or 0
    inflight = db.scalar(select(func.count()).select_from(Workflow).where(Workflow.user_id==user.id,Workflow.status.in_(['queued','planning','running']))) or 0
    if count >= config['request_limit']:
        raise HTTPException(429,'Đã đạt giới hạn yêu cầu mỗi phút. Vui lòng thử lại sau.')
    # Reserve a conservative maximum for the bounded planner call.
    if used + (inflight+1)*6000 > config['token_budget']:
        raise HTTPException(429,'Không còn đủ token budget cho yêu cầu mới.')
    try:
        key='rate:'+user.id
        hits=cache.incr(key)
        if hits==1:
            cache.expire(key,60)
        if hits>config['request_limit']:
            raise HTTPException(429,'Đã đạt giới hạn Redis rate limit.')
    except redis.RedisError:
        pass

def context_get(db,conversation):
    if not conversation:
        return {}
    try:
        import json
        value=cache.get('memory:'+conversation.id)
        if value:
            return json.loads(value)
    except redis.RedisError:
        pass
    return conversation.context or {}

def context_set(conversation,data):
    if conversation:
        conversation.context={**(conversation.context or {}),**data}
        try:
            import json
            cache.setex('memory:'+conversation.id,1800,json.dumps(conversation.context))
        except redis.RedisError:
            pass
