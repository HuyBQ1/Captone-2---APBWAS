import base64,json,uuid
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import httpx,pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from conftest import login
from app import gmail,models as m
from app.config import settings
HTTP_CLIENT=httpx.Client

@pytest.fixture
def google_config(monkeypatch):
    for key,value in {'gmail_sender':'sender@gmail.com','gmail_client_id':'test.apps.googleusercontent.com',
        'gmail_client_secret':SecretStr('test-only-client-secret'),'gmail_redirect_uri':'http://localhost:4181/mail/callback',
        'mail_encryption_key':SecretStr(Fernet.generate_key().decode())}.items():monkeypatch.setattr(settings,key,value)

def transport(monkeypatch,handler):
    monkeypatch.setattr(gmail.httpx,'Client',lambda **kwargs:HTTP_CLIENT(transport=httpx.MockTransport(handler),**kwargs))

def oauth(client,monkeypatch,email='sender@gmail.com'):
    start=client.post('/api/mail/connect');assert start.status_code==200,start.text
    params=parse_qs(urlsplit(start.json()['url']).query)
    assert params['scope']==[' '.join(gmail.SCOPES)] and params['code_challenge_method']==['S256']
    def handler(request):
        if str(request.url)==gmail.TOKEN_URL:
            fields=parse_qs(request.content.decode());assert fields['client_secret']==['test-only-client-secret'];assert fields.get('code_verifier')
            return httpx.Response(200,json={'access_token':'private-access-token','refresh_token':'private-refresh-token','expires_in':3600,'scope':' '.join(gmail.SCOPES)})
        if str(request.url)==gmail.INFO_URL:return httpx.Response(200,json={'sub':'google-user-1','email':email,'email_verified':True})
        raise AssertionError('Unexpected Google request')
    transport(monkeypatch,handler)
    result=client.post('/api/mail/callback',json={'state':params['state'][0],'code':'google-auth-code'})
    assert result.status_code==200,result.text
    return params['state'][0]

def test_oauth_scopes_encryption_one_use_and_rbac(env,google_config,monkeypatch):
    client,factory,users,*_=env
    login(client,'Employee');personal=client.get('/api/mail/status');assert personal.status_code==200 and not personal.json()['can_send_campaigns']
    login(client);state=oauth(client,monkeypatch)
    status=client.get('/api/mail/status').json();assert status['connected'] and not status['can_read_mail']
    assert 'private-' not in json.dumps(status) and 'test-only-client-secret' not in json.dumps(status)
    with factory() as db:
        row=db.get(m.GmailConnection,users['Manager']);assert 'private-' not in row.credentials_ciphertext
        assert gmail.decrypt(row.credentials_ciphertext)['refresh_token']=='private-refresh-token'
    assert client.post('/api/mail/callback',json={'state':state,'code':'google-auth-code'}).status_code==400
    login(client,'Admin');assert not client.get('/api/mail/status').json()['connected']

def test_oauth_state_wrong_user_expiry_and_wrong_account(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client)
    url=client.post('/api/mail/connect').json()['url'];state=parse_qs(urlsplit(url).query)['state'][0]
    login(client,'Admin');assert client.post('/api/mail/callback',json={'state':state,'code':'code'}).status_code==400
    login(client)
    with factory() as db:
        ticket=db.scalar(select(m.GmailOAuthState));ticket.expires_at=m.now()-timedelta(minutes=1);db.commit()
    assert client.post('/api/mail/callback',json={'state':state,'code':'code'}).status_code==400
    state=parse_qs(urlsplit(client.post('/api/mail/connect').json()['url']).query)['state'][0]
    transport(monkeypatch,lambda r:httpx.Response(200,json={'access_token':'access','refresh_token':'refresh','scope':gmail.SEND_SCOPE}) if str(r.url)==gmail.TOKEN_URL else httpx.Response(200,json={'sub':'other','email':'other@gmail.com','email_verified':True}))
    assert client.post('/api/mail/callback',json={'state':state,'code':'code'}).status_code==403

def test_gmail_refresh_and_test_send_only_self_confirmed_idempotent(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch)
    with factory() as db:db.get(m.GmailConnection,users['Manager']).expires_at=m.now()-timedelta(seconds=1);db.commit()
    sent=[]
    def handler(request):
        if str(request.url)==gmail.TOKEN_URL:return httpx.Response(200,json={'access_token':'renewed','expires_in':3600})
        assert str(request.url)=='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        assert request.headers['authorization']=='Bearer renewed'
        raw=base64.urlsafe_b64decode(json.loads(request.content)['raw']).decode()
        assert 'To: sender@gmail.com' in raw and 'From: sender@gmail.com' in raw
        sent.append(raw);return httpx.Response(200,json={'id':'gmail-message-1'})
    transport(monkeypatch,handler)
    key=str(uuid.uuid4())
    assert client.post('/api/mail/test',json={'confirmed':False,'idempotency_key':key}).status_code==422
    one=client.post('/api/mail/test',json={'confirmed':True,'idempotency_key':key});assert one.json()['status']=='sent',one.text
    two=client.post('/api/mail/test',json={'confirmed':True,'idempotency_key':key});assert two.json()['id']==one.json()['id'] and len(sent)==1

def test_send_timeout_is_uncertain_and_is_not_automatically_repeated(env,google_config,monkeypatch):
    client,*_=env;login(client);oauth(client,monkeypatch)
    calls=[]
    def handler(request):calls.append(1);raise httpx.ReadTimeout('never disclose token')
    transport(monkeypatch,handler);key=str(uuid.uuid4())
    result=client.post('/api/mail/test',json={'confirmed':True,'idempotency_key':key})
    assert result.json()['status']=='unknown'
    assert client.post('/api/mail/test',json={'confirmed':True,'idempotency_key':key}).json()['status']=='unknown'
    assert len(calls)==1

def test_unconfigured_status_does_not_claim_connected(env,monkeypatch):
    client,*_=env;login(client);monkeypatch.setattr(settings,'gmail_client_secret',SecretStr(''))
    status=client.get('/api/mail/status').json();assert not status['configured'] and not status['connected']
    assert client.post('/api/mail/connect').status_code==503

def test_employee_personal_oauth_is_private_and_campaign_sending_is_denied(env,google_config,monkeypatch):
    client,factory,users,*_=env
    login(client);oauth(client,monkeypatch)
    login(client,'Employee');oauth(client,monkeypatch,email='personal.staff@gmail.com')
    status=client.get('/api/mail/status').json()
    assert status['email']=='personal.staff@gmail.com' and not status['can_send_campaigns']
    assert status['self_test_limit_per_hour']==1
    calls=[]
    def handler(request):
        if str(request.url)==gmail.INFO_URL:return httpx.Response(200,json={'sub':'google-user-1','email':'personal.staff@gmail.com','email_verified':True})
        raw=base64.urlsafe_b64decode(json.loads(request.content)['raw']).decode()
        assert 'To: personal.staff@gmail.com' in raw and 'From: personal.staff@gmail.com' in raw
        assert 'sender@gmail.com' not in raw
        calls.append(request.url);return httpx.Response(200,json={'id':'self-test-1'})
    transport(monkeypatch,handler)
    assert client.post('/api/mail/check').status_code==200
    assert client.get('/api/mail/employees').status_code==403
    assert client.get('/api/mail/campaigns').status_code==403
    assert client.post('/api/mail/campaigns',json={'subject':'Hi','body_text':'Content','idempotency_key':str(uuid.uuid4())}).status_code==403
    assert client.post('/api/mail/campaigns/nonexistent/send',json={'revision':1,'confirmed':True}).status_code==403
    body={'confirmed':True,'idempotency_key':str(uuid.uuid4())}
    assert client.post('/api/mail/test',json={**body,'recipient':'other@gmail.com'}).status_code==422
    assert client.post('/api/mail/test',json=body).json()['status']=='sent'
    assert client.post('/api/mail/test',json=body).json()['status']=='sent'  # No replay.
    assert client.post('/api/mail/test',json={**body,'idempotency_key':str(uuid.uuid4())}).status_code==429
    assert len(calls)==1
    with factory() as db:
        assert db.get(m.GmailConnection,users['Manager']).email=='sender@gmail.com'
        assert db.get(m.GmailConnection,users['Employee']).email=='personal.staff@gmail.com'
    login(client,'Admin');assert not client.get('/api/mail/status').json()['connected']

def test_employee_connect_does_not_need_company_sender_and_rejects_unverified_identity(env,google_config,monkeypatch):
    client,*_=env;login(client,'Employee');monkeypatch.setattr(settings,'gmail_sender','')
    assert client.get('/api/mail/status').json()['configured']
    url=client.post('/api/mail/connect').json()['url'];params=parse_qs(urlsplit(url).query)
    assert params['login_hint']==['employee@apbwas.demo']
    transport(monkeypatch,lambda request:httpx.Response(200,json={'access_token':'access','refresh_token':'refresh','scope':gmail.SEND_SCOPE}) if str(request.url)==gmail.TOKEN_URL else httpx.Response(200,json={'email_verified':False,'email':'someone@gmail.com','sub':'other'}))
    assert client.post('/api/mail/callback',json={'code':'code','state':params['state'][0]}).status_code==403
