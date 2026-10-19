from fastapi import HTTPException
from .models import Role

DEFAULT_PERMISSIONS = {
    'Admin': ['sales.read','inventory.read','inventory.propose','documents.read','documents.write','approvals.decide','audit.read','users.manage','settings.manage'],
    'Manager': ['sales.read','inventory.read','inventory.propose','documents.read','documents.write','approvals.decide','audit.read'],
    'Employee': ['inventory.read','documents.read'],
}

def permissions(db, user):
    role = db.get(Role, user.role)
    return role.permissions if role else []

def require(db, user, permission):
    if not user.active or permission not in permissions(db, user):
        raise HTTPException(403, 'Bạn không có quyền thực hiện thao tác này.')

def visible(user, owner):
    return user.role in ('Admin', 'Manager') or user.id == owner
