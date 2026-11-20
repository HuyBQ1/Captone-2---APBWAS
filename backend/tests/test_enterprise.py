import hashlib,json,uuid
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
from sqlalchemy import select,func
from app import models as m
from app.auth import hasher
from app.retrieval import index_document
from conftest import login,create,execute

def test_employee_can_change_only_own_delivery_email_without_send_permission(env):
    client,factory,users,_=env;login(client,'Employee')
    before=client.get('/api/auth/me').json()
    result=client.patch('/api/auth/profile',json={'name':before['name'],'delivery_email':'My.Staff@Gmail.com'})
    assert result.status_code==200 and result.json()['delivery_email']=='my.staff@gmail.com'
    assert result.json()['email']==before['email'] and result.json()['role']=='Employee'
    assert 'mail.send' not in result.json()['permissions']
    assert client.patch('/api/auth/profile',json={'name':before['name'],'delivery_email':'bad@example.com'}).status_code==422
    assert client.patch('/api/auth/profile',json={'name':before['name'],'role':'Admin'}).status_code==422
    assert client.put('/api/mail/employees/'+users['Manager'],json={'delivery_email':'other@gmail.com'}).status_code==403
    with factory() as db:assert not db.get(m.User,users['Manager']).delivery_email

def invite(client,email='staff@company.test'):
    r=client.post('/api/admin/invitations',json={'email':email,'name':'New employee','role':'Employee'})
    assert r.status_code==200,r.text
    body=r.json();token=parse_qs(urlsplit(body['url']).fragment)['token'][0]
    return body,token

def test_invitation_is_hashed_one_use_and_never_in_audit(env):
    client,factory,_,_=env;login(client,'Admin');body,token=invite(client)
    with factory() as db:
        ticket=db.scalar(select(m.AccountToken));assert ticket.token_hash==hashlib.sha256(token.encode()).hexdigest()
        assert token not in str([a.payload for a in db.scalars(select(m.AuditLog))])
    assert client.post('/api/auth/redeem',json={'token':token,'password':'PersonalPassword@123'}).status_code==200
    assert client.post('/api/auth/redeem',json={'token':token,'password':'AnotherPassword@123'}).status_code==400
    assert client.post('/api/auth/login',json={'email':'staff@company.test','password':'PersonalPassword@123'}).status_code==200
    assert client.get('/api/auth/me').json()['must_change_password'] is False
    assert client.get('/api/data/products').status_code==200

def test_expired_and_disabled_account_links_are_rejected(env):
    client,factory,users,_=env;login(client,'Admin');body,token=invite(client)
    with factory() as db:
        db.scalar(select(m.AccountToken)).expires_at=m.now()-timedelta(seconds=1);db.commit()
    assert client.post('/api/auth/redeem',json={'token':token,'password':'PersonalPassword@123'}).status_code==400
    r=client.post('/api/admin/users/'+body['user']['id']+'/recovery');token=parse_qs(urlsplit(r.json()['url']).fragment)['token'][0]
    assert client.patch('/api/admin/users/'+body['user']['id'],json={'name':'New employee','role':'Employee','active':False}).status_code==200
    assert client.post('/api/auth/redeem',json={'token':token,'password':'PersonalPassword@123'}).status_code==400

def test_initial_password_is_enforced_and_profile_survives_login(env):
    client,factory,_,_=env;login(client,'Admin')
    assert client.post('/api/admin/users',json={'email':'staff@company.test','name':'Staff member','role':'Employee','password':'TemporaryPassword@123'}).status_code==200
    assert client.post('/api/auth/login',json={'email':'staff@company.test','password':'TemporaryPassword@123'}).status_code==200
    assert client.get('/api/data/products').status_code==403
    profile={'name':'Employee Name','phone':'0901234567','department':'Operations','job_title':'Specialist'}
    assert client.patch('/api/auth/profile',json=profile).status_code==200
    assert client.post('/api/auth/password',json={'current_password':'TemporaryPassword@123','new_password':'PersonalPassword@123'}).status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'email':'staff@company.test','password':'PersonalPassword@123'}).status_code==200
    assert all(client.get('/api/auth/me').json()[k]==v for k,v in profile.items())
    assert client.get('/api/data/products').status_code==200

def test_preferences_sessions_and_ownership(env):
    client,factory,users,_=env;login(client,'Employee')
    prefs={'theme':'dark','sidebar_collapsed':True}
    assert client.put('/api/auth/preferences',json=prefs).status_code==200
    login(client,'Employee')
    assert client.get('/api/auth/me').json()['preferences']==prefs
    sessions=client.get('/api/auth/sessions').json()['items'];assert len(sessions)==2
    assert all('token_hash' not in s for s in sessions)
    other=next(s for s in sessions if not s['current'])
    login(client,'Manager');assert client.delete('/api/auth/sessions/'+other['id']).status_code==404
    login(client,'Employee');assert client.delete('/api/auth/sessions/'+other['id']).status_code==200
    with factory() as db:assert db.get(m.AuthSession,other['id']) is None

def test_company_is_persistent_and_only_administrators_edit(env):
    client,factory,_,_=env;login(client,'Admin')
    body={'name':'Company Example','email':'hello@company.test','phone':'01234','tax_code':'TEST01','address':'Office address'}
    assert client.put('/api/company',json=body).status_code==200
    login(client,'Employee');assert client.get('/api/company').json()==body
    assert client.put('/api/company',json=body).status_code==403

def test_product_version_archive_and_business_permissions(env):
    client,factory,_,_=env;login(client,'Admin')
    body={'sku':'NEW-001','name':'New product','category':'Business','price':125000,'threshold':5,'active':True,'version':1}
    r=client.post('/api/business/products',json=body);assert r.status_code==200,r.text
    pid=r.json()['id'];assert client.post('/api/business/products',json=body).status_code==409
    with factory() as db:assert db.get(m.Inventory,pid).quantity==0
    assert client.put('/api/business/products/'+pid,json={**body,'active':False}).status_code==200
    assert client.put('/api/business/products/'+pid,json=body).status_code==409
    login(client,'Manager');assert client.post('/api/business/products',json={**body,'sku':'NEW-002'}).status_code==403

def test_sale_stock_ledger_idempotency_and_rollback(env):
    client,factory,users,pid=env;login(client,'Admin')
    body={'product_id':pid,'quantity':4,'reference':str(uuid.uuid4()),'product_version':1}
    first=client.post('/api/business/sales',json=body);assert first.status_code==200,first.text
    listed=client.get('/api/data/products?q=T01').json()['items'][0]
    assert listed['product_version']==1 and listed['inventory_version']==2
    second=client.post('/api/business/sales',json=body);assert second.json()['id']==first.json()['id']
    assert first.json()['revenue']==400000
    assert client.post('/api/business/sales',json={**body,'quantity':2}).status_code==409
    assert client.post('/api/business/sales',json={**body,'reference':str(uuid.uuid4()),'quantity':7}).status_code==409
    with factory() as db:
        assert db.get(m.Inventory,pid).quantity==6
        assert db.scalar(select(func.count()).select_from(m.InventoryMovement))==1
        movement=db.scalar(select(m.InventoryMovement));assert (movement.before,movement.after)==(10,6)
    login(client,'Employee');assert client.post('/api/business/sales',json={**body,'reference':str(uuid.uuid4())}).status_code==403

def test_original_file_stays_in_database_and_download_checks_scope(env):
    client,factory,_,_=env;login(client,'Manager');content='Nội dung doanh nghiệp được lưu bền vững.'.encode()
    r=client.post('/api/documents?scope=Manager',files={'file':('company.txt',content,'text/plain')});assert r.status_code==202
    did=r.json()['id']
    with factory() as db:
        doc=db.get(m.Document,did);assert doc.path is None
        assert db.get(m.DocumentFile,did).content==content
        index_document(db,doc)
    assert client.get('/api/documents/'+did+'/download').content==content
    assert client.get('/api/documents/'+did).json()['has_original'] is True
    login(client,'Employee');assert client.get('/api/documents/'+did+'/download').status_code==403
    login(client,'Manager');assert client.delete('/api/documents/'+did).status_code==200
    with factory() as db:assert db.get(m.DocumentFile,did) is None

def test_notifications_persist_and_are_private(env):
    client,factory,_,_=env;login(client,'Manager');wf=create(client,'Kiểm tra sản phẩm sắp hết hàng');execute(factory,wf['id'])
    result=client.get('/api/notifications').json();assert result['unread']==1
    nid=result['items'][0]['id']
    login(client,'Employee');assert client.get('/api/notifications').json()['total']==0
    assert client.post('/api/notifications/'+nid+'/read').status_code==404
    login(client,'Manager');assert client.post('/api/notifications/'+nid+'/read').status_code==200
    assert client.get('/api/notifications').json()['unread']==0

def test_provision_company_delivers_unique_credentials_without_storing_plaintext(env,monkeypatch):
    from app import provision_company
    client,factory,users,_=env;monkeypatch.setattr(provision_company,'Session',factory)
    delivered=provision_company.provision(disable_demo=True)
    assert len({a['temporary_password'] for a in delivered['accounts']})==3
    assert client.get('/api/auth/config').json()['demo_accounts'] is False
    for account in delivered['accounts']:
        r=client.post('/api/auth/login',json={'email':account['email'],'password':account['temporary_password']})
        assert r.status_code==200 and r.json()['must_change_password'] is True
    with factory() as db:
        assert all(not db.get(m.User,id).active for id in users.values())
        payloads=str([a.payload for a in db.scalars(select(m.AuditLog))])
        assert all(a['temporary_password'] not in payloads for a in delivered['accounts'])
    import pytest
    with pytest.raises(RuntimeError,match='already exists'):provision_company.provision(disable_demo=True)
    with factory() as db:assert db.scalar(select(func.count()).select_from(m.User))==6
