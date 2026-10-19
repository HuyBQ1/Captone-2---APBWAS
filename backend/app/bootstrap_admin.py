import getpass
from sqlalchemy import select
from .db import Session
from .models import User
from .auth import hasher
from .audit import audit

if __name__=='__main__':
    email=input('Admin email: ').strip().lower()
    name=input('Full name: ').strip()
    password=getpass.getpass('Password (10+ characters): ')
    if len(password)<10 or '@' not in email or len(name)<2: raise SystemExit('Invalid input.')
    with Session() as db:
        if db.scalar(select(User).where(User.role=='Admin',User.active==True)): raise SystemExit('Active admin already exists.')
        user=User(email=email,name=name,role='Admin',password_hash=hasher.hash(password)); db.add(user); db.flush()
        audit(db,user,'admin.bootstrap'); db.commit()
