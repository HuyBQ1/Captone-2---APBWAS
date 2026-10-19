import hashlib, secrets
from datetime import timedelta, timezone
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db
from .models import AuthSession, User, now
from .config import settings

hasher = PasswordHasher()

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('apbwas_session', '')
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if not session or utc(session.expires_at) <= now():
        raise HTTPException(401, 'Phiên đăng nhập đã hết hạn.')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, 'Tài khoản đã bị khóa.')
    # SameSite plus origin validation for mutating browser requests.
    origin = request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin:
        from urllib.parse import urlparse
        if urlparse(origin).netloc != request.headers.get('host') and origin != settings.frontend_origin:
            raise HTTPException(403, 'Origin không hợp lệ.')
    return user

def create_session(db, user):
    token = secrets.token_urlsafe(40)
    db.add(AuthSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now()+timedelta(hours=settings.session_hours)))
    return token
