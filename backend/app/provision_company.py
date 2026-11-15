"""Provision internal accounts once; capture stdout in a private, ignored file."""
import argparse,json,secrets
from sqlalchemy import select,delete,update
from .db import Session
from .models import User,Role,AuthSession,AccountToken,SystemSetting,now
from .auth import hasher
from .audit import audit

def provision(disable_demo=False):
    accounts=[]
    with Session() as db:
        if not db.get(SystemSetting,'company'):
            db.add(SystemSetting(key='company',value={'name':'Nova Commerce','email':'','phone':'','address':'','tax_code':''}));db.flush()
        definitions=[('Admin','admin','Quản trị Nova Commerce','Quản trị'),('Manager','manager','Quản lý Nova Commerce','Kinh doanh'),('Employee','employee','Nhân viên Nova Commerce','Vận hành')]
        for role,handle,name,department in definitions:
            email=handle+'@novacommerce.example'
            if not db.get(Role,role):raise RuntimeError('Run migrations and seed roles before provisioning.')
            if db.scalar(select(User.id).where(User.email==email)):raise RuntimeError('Internal account already exists; use recovery instead of overwriting credentials.')
            password=secrets.token_urlsafe(20)+'Aa1!'
            user=User(email=email,name=name,department=department,role=role,password_hash=hasher.hash(password),must_change_password=True)
            db.add(user);db.flush();audit(db,'operator','company.account_provisioned',user.id,{'role':role,'email':email})
            accounts.append({'role':role,'email':email,'temporary_password':password,'must_change_password':True})
        if disable_demo:
            for user in db.scalars(select(User).where(User.email.in_(['admin@apbwas.demo','manager@apbwas.demo','employee@apbwas.demo'])).with_for_update()):
                user.active=False
                db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
                db.execute(update(AccountToken).where(AccountToken.user_id==user.id,AccountToken.used_at.is_(None)).values(used_at=now()))
                audit(db,'operator','company.demo_account_disabled',user.id)
            company=db.get(SystemSetting,'company');company.value={**company.value,'demo_accounts_enabled':False}
        db.commit()
    return {'company':'Nova Commerce','login_url':'http://localhost:4180','delivery':'Reserved .example domain for internal usernames; no email is sent.',
            'instructions':'Change the temporary password on first login. Share each credential only with its owner. This private file must not be committed.', 'accounts':accounts}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--disable-demo',action='store_true');args=parser.parse_args()
    print(json.dumps(provision(args.disable_demo),ensure_ascii=True,indent=2))
