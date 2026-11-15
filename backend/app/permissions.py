from fastapi import HTTPException
from .models import Role

DEFAULT_PERMISSIONS = {
    'Admin': ['business.manage','sales.read','inventory.read','inventory.propose','documents.read','documents.write','approvals.decide','audit.read','users.manage','settings.manage'],
    'Manager': ['sales.read','inventory.read','inventory.propose','documents.read','documents.write','approvals.decide','audit.read'],
    'Employee': ['inventory.read','documents.read'],
}
for _role,_permissions in DEFAULT_PERMISSIONS.items():
    _permissions.extend(['agents.run','mail.connect'])
    if _role in ('Admin','Manager'):_permissions.extend(['agents.manage','mail.send'])

def permissions(db, user):
    # Long-lived workers must not authorize from an old identity-map snapshot.
    role = db.get(Role, user.role, populate_existing=True)
    return role.permissions if role else []

def require(db, user, permission):
    if not user.active or permission not in permissions(db, user):
        raise HTTPException(403, 'Bạn không có quyền thực hiện thao tác này.')

def visible(user, owner):
    return user.role in ('Admin', 'Manager') or user.id == owner
