"""Gmail send-only OAuth. Credentials stay encrypted on the server."""
import base64,hashlib,json,secrets,re
from datetime import timedelta
from urllib.parse import urlencode,urlsplit
from email.message import EmailMessage
from email.utils import formatdate
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select,update,func
from . import models as m
from .db import get_db
from .auth import current_user,utc
from .permissions import require,permissions
from .config import settings
from .schemas import StrictModel
from .audit import audit

router=APIRouter(prefix='/api/mail')
SEND_SCOPE='https://www.googleapis.com/auth/gmail.send'
SCOPES=['openid','email',SEND_SCOPE]
TOKEN_URL='https://oauth2.googleapis.com/token'
INFO_URL='https://openidconnect.googleapis.com/v1/userinfo'

def cipher():
    try:return Fernet(settings.mail_encryption_key.get_secret_value().encode())
    except (ValueError,TypeError):raise HTTPException(503,'MAIL_ENCRYPTION_KEY chưa được cấu hình hợp lệ ở backend.')

def encrypt(value):return cipher().encrypt(json.dumps(value).encode()).decode()
def decrypt(value):
    try:return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken,ValueError):raise HTTPException(503,'Không đọc được thông tin kết nối. Kiểm tra khóa mã hóa hoặc kết nối lại Gmail.')

def redirect_uri():
    value=settings.gmail_redirect_uri or settings.frontend_origin.rstrip('/')+'/mail/callback'
    parsed=urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname or not (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
        raise HTTPException(503,'Redirect URI cần HTTPS hoặc HTTP localhost để phát triển.')
    return value

def setup(user=None):
    fields={'GMAIL_SENDER':settings.gmail_sender,'GMAIL_CLIENT_ID':settings.gmail_client_id,
            'GMAIL_CLIENT_SECRET':settings.gmail_client_secret.get_secret_value(),'MAIL_ENCRYPTION_KEY':settings.mail_encryption_key.get_secret_value()}
    personal=bool(user and user.role=='Employee')
    if personal:fields.pop('GMAIL_SENDER')
    missing=[k for k,v in fields.items() if not v]
    valid=not missing
    if valid:
        try:cipher();redirect_uri()
        except HTTPException:valid=False
    return {'configured':valid,'missing':missing,'sender':user.email if personal else settings.gmail_sender,'redirect_uri':redirect_uri(),
            'scopes':SCOPES,'auth_method':'Google OAuth 2.0','can_read_mail':False}

def require_setup(user=None):
    if not setup(user)['configured']:raise HTTPException(503,'Cần cấu hình OAuth Client Google và khóa mã hóa ở backend trước khi kết nối.')
    if not (user and user.role=='Employee') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',settings.gmail_sender):raise HTTPException(503,'Địa chỉ Gmail gửi chưa hợp lệ.')

def require_connection(db,user):
    # Older sender roles keep access while mail.connect is deployed separately.
    if 'mail.send' not in permissions(db,user):require(db,user,'mail.connect')

def google(method,url,**kwargs):
    try:
        with httpx.Client(timeout=15,follow_redirects=False) as client:response=client.request(method,url,**kwargs)
    except httpx.HTTPError:raise HTTPException(502,'Không thể kết nối Google. Vui lòng thử lại.') from None
    if response.status_code>=300:
        if response.status_code in (400,401,403):raise HTTPException(401,'Google từ chối xác thực hoặc quyền truy cập. Hãy kết nối lại Gmail.')
        raise HTTPException(502,'Google chưa xử lý được yêu cầu. Vui lòng thử lại.')
    try:return response.json()
    except ValueError:raise HTTPException(502,'Phản hồi Google không hợp lệ.') from None

def expiry(tokens):
    try:seconds=int(tokens.get('expires_in',3600))
    except (ValueError,TypeError):raise HTTPException(502,'Thời hạn phiên Google không hợp lệ.') from None
    return m.now()+timedelta(seconds=max(1,min(seconds,86400)))

def connection(db,user,locked=False):
    query=select(m.GmailConnection).where(m.GmailConnection.user_id==user.id,m.GmailConnection.workspace_id==user.workspace_id)
    if locked:query=query.with_for_update()
    row=db.scalar(query)
    if not row:raise HTTPException(409,'Bạn chưa kết nối Gmail trong workspace này.')
    return row

@router.get('/status')
def status(user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user)
    row=db.get(m.GmailConnection,user.id)
    connected=bool(row and row.workspace_id==user.workspace_id)
    return {**setup(user),'connected':connected,'email':row.email if connected else None,
            'connected_at':row.connected_at.isoformat() if connected else None,
            'can_send_campaigns':'mail.send' in permissions(db,user),
            'self_test_limit_per_hour':1 if user.role=='Employee' else 5}

@router.post('/connect')
def connect(user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user);require_setup(user)
    raw=secrets.token_urlsafe(40);verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    db.execute(update(m.GmailOAuthState).where(m.GmailOAuthState.user_id==user.id,m.GmailOAuthState.used.is_(False)).values(used=True))
    db.add(m.GmailOAuthState(digest=hashlib.sha256(raw.encode()).hexdigest(),user_id=user.id,workspace_id=user.workspace_id,
         verifier_ciphertext=encrypt({'verifier':verifier}),expires_at=m.now()+timedelta(minutes=10)))
    audit(db,user,'gmail.oauth_started',user.id);db.commit()
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':settings.gmail_client_id,
            'redirect_uri':redirect_uri(),'response_type':'code','scope':' '.join(SCOPES),'state':raw,'access_type':'offline',
            'prompt':'consent','login_hint':user.email if user.role=='Employee' else settings.gmail_sender,'code_challenge':challenge,'code_challenge_method':'S256'})}

class Callback(StrictModel):
    code:str=Field(min_length=1,max_length=4096)
    state:str=Field(min_length=30,max_length=200)

@router.post('/callback')
def callback(body:Callback,user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user);require_setup(user)
    digest=hashlib.sha256(body.state.encode()).hexdigest()
    ticket=db.get(m.GmailOAuthState,digest)
    if not ticket or ticket.user_id!=user.id or ticket.workspace_id!=user.workspace_id:raise HTTPException(400,'Phiên kết nối Google không hợp lệ.')
    consumed=db.execute(update(m.GmailOAuthState).where(m.GmailOAuthState.digest==digest,m.GmailOAuthState.used.is_(False),m.GmailOAuthState.expires_at>m.now()).values(used=True))
    if consumed.rowcount!=1:raise HTTPException(400,'Phiên kết nối Google đã dùng hoặc hết hạn. Bấm kết nối lại.')
    verifier=decrypt(ticket.verifier_ciphertext)['verifier'];db.commit()
    tokens=google('POST',TOKEN_URL,data={'client_id':settings.gmail_client_id,'client_secret':settings.gmail_client_secret.get_secret_value(),
                  'redirect_uri':redirect_uri(),'code':body.code,'code_verifier':verifier,'grant_type':'authorization_code'})
    if not tokens.get('access_token') or SEND_SCOPE not in tokens.get('scope','').split():raise HTTPException(403,'Bạn chưa cấp quyền gửi Gmail cho APBWAS.')
    info=google('GET',INFO_URL,headers={'Authorization':'Bearer '+tokens['access_token']})
    email=info.get('email','')
    if info.get('email_verified') is not True or not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not info.get('sub'):
        raise HTTPException(403,'Google chưa xác minh được địa chỉ email của tài khoản này.')
    if user.role!='Employee' and email.lower()!=settings.gmail_sender.lower():
        raise HTTPException(403,'Hãy chọn đúng tài khoản Gmail gửi đã cấu hình: '+settings.gmail_sender)
    row=db.get(m.GmailConnection,user.id)
    refresh=tokens.get('refresh_token')
    if not refresh and row and row.workspace_id==user.workspace_id and row.google_sub==info['sub']:
        refresh=decrypt(row.credentials_ciphertext).get('refresh_token')
    if not refresh:raise HTTPException(400,'Google chưa cấp quyền ngoại tuyến. Hãy kết nối lại và chấp thuận quyền gửi.')
    if not row:row=m.GmailConnection(user_id=user.id);db.add(row)
    row.workspace_id=user.workspace_id;row.email=info['email'].lower();row.google_sub=info['sub']
    row.credentials_ciphertext=encrypt({'access_token':tokens['access_token'],'refresh_token':refresh})
    row.expires_at=expiry(tokens)
    row.scopes=tokens['scope'].split();row.connected_at=m.now()
    audit(db,user,'gmail.connected',user.id,{'email':row.email});db.commit()
    return {'connected':True,'email':row.email}

def access(db,row):
    tokens=decrypt(row.credentials_ciphertext)
    if utc(row.expires_at)<=m.now()+timedelta(minutes=1):
        refreshed=google('POST',TOKEN_URL,data={'client_id':settings.gmail_client_id,'client_secret':settings.gmail_client_secret.get_secret_value(),
                    'refresh_token':tokens['refresh_token'],'grant_type':'refresh_token'})
        if not refreshed.get('access_token'):raise HTTPException(401,'Phiên Gmail hết hạn. Hãy kết nối lại.')
        tokens['access_token']=refreshed['access_token']
        if refreshed.get('refresh_token'):tokens['refresh_token']=refreshed['refresh_token']
        row.credentials_ciphertext=encrypt(tokens);row.expires_at=expiry(refreshed);db.commit()
    return tokens['access_token']

@router.post('/check')
def check(user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user);require_setup(user);row=connection(db,user,True)
    info=google('GET',INFO_URL,headers={'Authorization':'Bearer '+access(db,row)})
    if info.get('sub')!=row.google_sub or info.get('email','').lower()!=row.email:raise HTTPException(401,'Tài khoản Google không khớp. Hãy kết nối lại.')
    audit(db,user,'gmail.connection_checked',user.id);db.commit()
    return {'ok':True,'email':row.email,'message':'Đã xác thực với Google. Chưa gửi thư nào.'}

@router.delete('/connection')
def disconnect(user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user);row=connection(db,user,True)
    token=decrypt(row.credentials_ciphertext)['refresh_token']
    try:
        with httpx.Client(timeout=15,follow_redirects=False) as client:
            response=client.post('https://oauth2.googleapis.com/revoke',data={'token':token})
            revoked=response.status_code in (200,400)
    except httpx.HTTPError:revoked=False
    db.delete(row);audit(db,user,'gmail.disconnected',user.id,{'google_revocation_confirmed':revoked});db.commit()
    return {'ok':True,'google_revocation_confirmed':revoked}

class TestMail(StrictModel):
    confirmed:bool
    idempotency_key:str=Field(min_length=10,max_length=100)

@router.post('/test')
def test_mail(body:TestMail,user=Depends(current_user),db=Depends(get_db)):
    require_connection(db,user);require_setup(user)
    if not body.confirmed:raise HTTPException(422,'Cần xác nhận gửi thư thử tới chính tài khoản Gmail đã kết nối.')
    row=connection(db,user,True)
    existing=db.scalar(select(m.GmailSendAttempt).where(m.GmailSendAttempt.idempotency_key==body.idempotency_key))
    if existing:
        if existing.user_id!=user.id or existing.workspace_id!=user.workspace_id:raise HTTPException(409,'Mã gửi đã được sử dụng.')
        return {'id':existing.id,'status':existing.status,'recipient':existing.recipient}
    recent=db.scalar(select(func.count()).select_from(m.GmailSendAttempt).where(m.GmailSendAttempt.user_id==user.id,m.GmailSendAttempt.created_at>=m.now()-timedelta(hours=1)))
    limit=1 if user.role=='Employee' else 5
    if recent>=limit:raise HTTPException(429,f'Tối đa {limit} thư kiểm tra mỗi giờ.')
    token=access(db,row)
    attempt=m.GmailSendAttempt(user_id=user.id,workspace_id=user.workspace_id,idempotency_key=body.idempotency_key,recipient=row.email)
    db.add(attempt);db.flush();audit(db,user,'gmail.test_send_started',attempt.id,{'recipient':row.email});db.commit()
    msg=EmailMessage();msg['From']=row.email;msg['To']=row.email;msg['Subject']='APBWAS — kiểm tra kết nối Gmail'
    msg['Date']=formatdate(localtime=False);msg['Message-ID']=f'<apbwas-{attempt.id}@gmail.com>'
    msg.set_content('Đây là thư kiểm tra do bạn xác nhận gửi từ APBWAS. Kết nối Gmail OAuth đã hoạt động.\nAPBWAS không yêu cầu mật khẩu Gmail và không đọc hộp thư của bạn.')
    raw=base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            response=client.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':'Bearer '+token},json={'raw':raw})
        if response.status_code>=500 or response.status_code<200 or response.status_code>=300 and response.status_code not in (400,401,403,404,429):attempt.status='unknown'
        elif response.status_code>=400:attempt.status='failed'
        else:
            result=response.json()
            if not result.get('id'):attempt.status='unknown'
            else:attempt.status='sent';attempt.remote_id=str(result['id'])[:255]
    except (httpx.HTTPError,ValueError):attempt.status='unknown'
    audit(db,user,'gmail.test_send_finished',attempt.id,{'status':attempt.status});db.commit()
    return {'id':attempt.id,'status':attempt.status,'recipient':attempt.recipient,
            'message':'Google đã chấp nhận gửi thư.' if attempt.status=='sent' else 'Google từ chối yêu cầu. Kiểm tra quyền/kết nối.' if attempt.status=='failed' else 'Chưa xác định kết quả. Kiểm tra Gmail trước khi gửi lại để tránh trùng thư.'}
