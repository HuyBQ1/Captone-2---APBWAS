import base64,hashlib,json,uuid
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit,parse_qs
import httpx,pytest
from sqlalchemy import select,func
from app import models as m,public_accounts as accounts,gmail
from app.auth import hasher
from conftest import login
from test_gmail import google_config

HTTP_CLIENT=httpx.Client
PASSWORD='PersonalPassword@123'

def add_sender(factory,users):
    with factory() as db:
        db.add(m.GmailConnection(user_id=users['Manager'],workspace_id='primary',email='sender@gmail.com',google_sub='sender-sub',credentials_ciphertext=gmail.encrypt({'access_token':'private-access','refresh_token':'private-refresh'}),expires_at=m.now()+timedelta(hours=1),scopes=gmail.SCOPES));db.commit()

def signup(client,email='new.staff@gmail.com'):
    return client.post('/api/auth/register',json={'name':'New Staff','email':email,'password':PASSWORD})

def test_registration_persists_hashed_password_and_requires_admin_approval(env):
    client,factory,users,_=env
    result=signup(client);assert result.status_code==202
    assert PASSWORD not in result.text
    assert client.post('/api/auth/register',json={'name':'Other','email':'root@gmail.com','password':PASSWORD,'role':'Admin'}).status_code==422
    with factory() as db:
        user=db.scalar(select(m.User).where(m.User.email=='new.staff@gmail.com'));id=user.id
        assert user.role=='Employee' and not user.active and user.registration_pending
        assert user.password_hash!=PASSWORD and hasher.verify(user.password_hash,PASSWORD)
        assert PASSWORD not in str([x.payload for x in db.scalars(select(m.AuditLog))])
    assert client.post('/api/auth/login',json={'email':'new.staff@gmail.com','password':PASSWORD}).status_code==403
    assert signup(client).json()==result.json()
    login(client);assert client.post('/api/admin/registrations/'+id+'/approve').status_code==403
    login(client,'Admin')
    assert any(u['id']==id for u in client.get('/api/admin/registrations').json()['items'])
    assert client.post('/api/admin/registrations/'+id+'/approve').status_code==200
    assert client.post('/api/admin/registrations/'+id+'/approve').status_code==409
    assert client.post('/api/auth/login',json={'email':'new.staff@gmail.com','password':PASSWORD}).status_code==200
    assert client.get('/api/auth/me').json()['role']=='Employee'
    assert 'mail.send' not in client.get('/api/auth/me').json()['permissions']

def test_duplicate_signup_does_not_change_existing_account_and_requests_are_db_limited(env):
    client,factory,users,_=env
    with factory() as db:old=db.get(m.User,users['Manager']).password_hash
    for _ in range(3):assert signup(client,'manager@apbwas.demo').status_code==202
    assert signup(client,'manager@apbwas.demo').status_code==429
    with factory() as db:
        assert db.get(m.User,users['Manager']).password_hash==old
        assert db.scalar(select(func.count()).select_from(m.AuthRequestAttempt))==3
        assert 'manager@apbwas.demo' not in str(db.scalar(select(m.AuthRequestAttempt)).email_hash)

def test_rejected_registration_cannot_log_in(env):
    client,factory,_,_=env;signup(client)
    with factory() as db:id=db.scalar(select(m.User.id).where(m.User.email=='new.staff@gmail.com'))
    login(client,'Admin');assert client.post('/api/admin/registrations/'+id+'/reject').status_code==200
    with factory() as db:
        u=db.get(m.User,id);assert not u.active and not u.registration_pending
    assert client.post('/api/auth/login',json={'email':'new.staff@gmail.com','password':PASSWORD}).status_code==401

def test_recovery_delivers_private_one_use_link_and_revokes_old_sessions(env,google_config,monkeypatch):
    client,factory,users,_=env;add_sender(factory,users);login(client,'Employee')
    with factory() as db:db.get(m.User,users['Employee']).delivery_email='someone.else@gmail.com';db.commit()
    known=client.post('/api/auth/forgot-password',json={'email':'EMPLOYEE@APBWAS.DEMO'})
    unknown=client.post('/api/auth/forgot-password',json={'email':'unknown@gmail.com'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    with factory() as db:
        row=db.scalar(select(m.AccountEmail));job=db.scalar(select(m.Job).where(m.Job.resource==row.id))
        raw=gmail.decrypt(row.payload_ciphertext)['url'];token=parse_qs(urlsplit(raw).fragment)['token'][0]
        ticket=db.get(m.AccountToken,row.token_id)
        assert ticket.token_hash==hashlib.sha256(token.encode()).hexdigest()
        assert token not in row.payload_ciphertext and token not in known.text
        assert token not in str([x.payload for x in db.scalars(select(m.AuditLog))])
        assert row.recipient=='employee@apbwas.demo'
        job_id=job.id;outbox_id=row.id
    sent=[]
    def handler(request):
        assert str(request.url)=='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        msg=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(json.loads(request.content)['raw']))
        assert msg['To']=='employee@apbwas.demo' and msg['From']=='sender@gmail.com'
        assert raw in msg.get_content() and 'someone.else@gmail.com' not in msg.get_content()
        sent.append(1);return httpx.Response(200,json={'id':'recovery-message-1'})
    monkeypatch.setattr(accounts.httpx,'Client',lambda **kwargs:HTTP_CLIENT(transport=httpx.MockTransport(handler),**kwargs))
    with factory() as db:
        accounts.process_email(db,db.get(m.Job,job_id));row=db.get(m.AccountEmail,outbox_id)
        assert row.status=='sent' and not row.payload_ciphertext and row.remote_id=='recovery-message-1'
        accounts.process_email(db,db.get(m.Job,job_id))
    assert len(sent)==1
    assert client.post('/api/auth/redeem',json={'token':token,'password':PASSWORD}).status_code==200
    with factory() as db:assert not db.scalar(select(m.AuthSession.id).where(m.AuthSession.user_id==users['Employee']))
    assert client.post('/api/auth/redeem',json={'token':token,'password':PASSWORD}).status_code==400
    assert client.post('/api/auth/login',json={'email':'employee@apbwas.demo','password':'Demo@123456'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'employee@apbwas.demo','password':PASSWORD}).status_code==200

def test_recovery_unknown_or_disabled_accounts_create_no_tokens(env,google_config):
    client,factory,users,_=env;add_sender(factory,users)
    with factory() as db:db.get(m.User,users['Employee']).active=False;db.commit()
    assert client.post('/api/auth/forgot-password',json={'email':'employee@apbwas.demo'}).status_code==202
    assert client.post('/api/auth/forgot-password',json={'email':'missing@gmail.com'}).status_code==202
    with factory() as db:
        assert not db.scalar(select(m.AccountToken)) and not db.scalar(select(m.AccountEmail))

def test_new_reset_invalidates_previous_links_and_rate_limit_is_persistent(env,google_config):
    client,factory,users,_=env;add_sender(factory,users)
    for _ in range(3):assert client.post('/api/auth/forgot-password',json={'email':'employee@apbwas.demo'}).status_code==202
    assert client.post('/api/auth/forgot-password',json={'email':'employee@apbwas.demo'}).status_code==429
    with factory() as db:
        tickets=list(db.scalars(select(m.AccountToken).order_by(m.AccountToken.created_at)))
        assert len(tickets)==3 and sum(x.used_at is None for x in tickets)==1
        old=db.scalar(select(m.AccountEmail).where(m.AccountEmail.token_id==tickets[0].id));job=db.scalar(select(m.Job).where(m.Job.resource==old.id))
        accounts.process_email(db,job);assert old.status=='cancelled' and not old.payload_ciphertext

def test_recovery_send_timeout_is_not_replayed(env,google_config,monkeypatch):
    client,factory,users,_=env;add_sender(factory,users)
    client.post('/api/auth/forgot-password',json={'email':'employee@apbwas.demo'})
    calls=[]
    def handler(request):calls.append(1);raise httpx.ReadTimeout('never display request context')
    monkeypatch.setattr(accounts.httpx,'Client',lambda **kwargs:HTTP_CLIENT(transport=httpx.MockTransport(handler),**kwargs))
    with factory() as db:
        job=db.scalar(select(m.Job).where(m.Job.kind=='account_email'))
        accounts.process_email(db,job);row=db.get(m.AccountEmail,job.resource)
        assert row.status=='unknown' and not row.payload_ciphertext
        accounts.process_email(db,job)
    assert len(calls)==1

def test_no_sender_is_reported_without_exposing_account_existence(env,google_config):
    client,factory,users,_=env
    one=client.post('/api/auth/forgot-password',json={'email':'employee@apbwas.demo'})
    two=client.post('/api/auth/forgot-password',json={'email':'missing@gmail.com'})
    assert one.json()==two.json() and 'chưa sẵn sàng' in one.json()['message']
    with factory() as db:assert not db.scalar(select(m.AccountToken))
