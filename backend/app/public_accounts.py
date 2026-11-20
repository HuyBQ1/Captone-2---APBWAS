"""Public account requests; no public role assignment or recovery-token disclosure."""
import base64,hashlib,hmac,json,re
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate
from urllib.parse import urlsplit,parse_qs
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import Field,field_validator
from sqlalchemy import select,func,text
from . import models as m,gmail
from .auth import hasher,current_user,utc
from .config import settings
from .db import get_db
from .schemas import StrictModel
from .permissions import require,permissions
from .audit import audit

router=APIRouter(prefix='/api')
EMAIL=r'^[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$'

class EmailInput(StrictModel):
    email:str=Field(min_length=5,max_length=180)
    @field_validator('email')
    @classmethod
    def normalize(cls,value):
        value=value.strip().lower()
        if not re.fullmatch(EMAIL,value):raise ValueError('Địa chỉ email không hợp lệ.')
        return value

class Register(EmailInput):
    name:str=Field(min_length=2,max_length=120)
    password:str=Field(min_length=10,max_length=128)
    @field_validator('name')
    @classmethod
    def name_value(cls,value):
        if len(value.strip())<2:raise ValueError('Nhập họ và tên hợp lệ.')
        return value.strip()

def fingerprint(value):return hmac.new(settings.audit_key.encode(),value.encode(),hashlib.sha256).hexdigest()

def throttle(db,request,email,kind):
    ip=request.client.host if request.client else 'unknown'
    email_hash=fingerprint(email);ip_hash=fingerprint(ip)
    if db.bind.dialect.name=='postgresql':
        for value in sorted([fingerprint(kind+':email:'+email),fingerprint(kind+':ip:'+ip)]):
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(value[:15],16)})
    recent=m.now()-timedelta(hours=1)
    base=select(func.count()).select_from(m.AuthRequestAttempt).where(m.AuthRequestAttempt.kind==kind,m.AuthRequestAttempt.created_at>=recent)
    by_ip=db.scalar(base.where(m.AuthRequestAttempt.ip_hash==ip_hash)) or 0
    by_email=db.scalar(base.where(m.AuthRequestAttempt.email_hash==email_hash)) or 0
    if by_ip>=(5 if kind=='register' else 20) or by_email>=3:
        raise HTTPException(429,'Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.')
    db.add(m.AuthRequestAttempt(kind=kind,email_hash=email_hash,ip_hash=ip_hash));db.flush()

def sender_connection(db):
    if not gmail.setup()['configured']:return None
    rows=db.scalars(select(m.GmailConnection).join(m.User,m.User.id==m.GmailConnection.user_id).where(
        m.GmailConnection.workspace_id=='primary',m.GmailConnection.email==settings.gmail_sender.lower(),m.User.active.is_(True)).order_by(m.GmailConnection.connected_at.desc()))
    for row in rows:
        owner=db.get(m.User,row.user_id)
        if owner.workspace_id=='primary' and 'mail.send' in permissions(db,owner) and gmail.SEND_SCOPE in row.scopes:return row
    return None

@router.post('/auth/register',status_code=202)
def register(body:Register,request:Request,db=Depends(get_db)):
    throttle(db,request,body.email,'register')
    password_hash=hasher.hash(body.password)
    existing=db.scalar(select(m.User).where(func.lower(m.User.email)==body.email))
    if not existing:
        if not db.get(m.Workspace,'primary') or not db.get(m.Role,'Employee'):raise HTTPException(503,'Doanh nghiệp chưa hoàn tất cấu hình tài khoản.')
        target=m.User(name=body.name,email=body.email,password_hash=password_hash,role='Employee',workspace_id='primary',active=False,registration_pending=True,must_change_password=False)
        db.add(target);db.flush();audit(db,'anonymous','account.registration_requested',target.id)
    db.commit()
    return {'ok':True,'message':'Yêu cầu đã được ghi nhận. Tài khoản mới cần quản trị viên duyệt trước khi đăng nhập. Nếu đã có tài khoản, hãy đăng nhập hoặc dùng Quên mật khẩu.'}

@router.post('/auth/forgot-password',status_code=202)
def forgot(body:EmailInput,request:Request,db=Depends(get_db)):
    throttle(db,request,body.email,'password_reset')
    sender=sender_connection(db)
    if sender:
        target=db.scalar(select(m.User).where(func.lower(m.User.email)==body.email,m.User.active.is_(True),m.User.registration_pending.is_(False),m.User.workspace_id=='primary').with_for_update())
        if target:
            from .enterprise import token_link
            link=token_link(db,target,'password_reset');db.flush()
            raw=parse_qs(urlsplit(link['url']).fragment)['token'][0]
            ticket=db.scalar(select(m.AccountToken).where(m.AccountToken.token_hash==hashlib.sha256(raw.encode()).hexdigest()))
            outbox=m.AccountEmail(user_id=target.id,token_id=ticket.id,sender_user_id=sender.user_id,recipient=target.email,payload_ciphertext=gmail.encrypt({'url':link['url']}))
            db.add(outbox);db.flush();db.add(m.Job(kind='account_email',resource=outbox.id))
            audit(db,'anonymous','account.recovery_requested',target.id)
    db.commit()
    return {'ok':True,'message':('Nếu email thuộc tài khoản đang hoạt động, liên kết đặt lại mật khẩu sẽ được gửi tới email đăng nhập. Liên kết có hiệu lực 1 giờ. Kiểm tra cả thư rác.' if sender else 'Yêu cầu đã được ghi nhận. Kết nối gửi thư khôi phục chưa sẵn sàng; vui lòng liên hệ quản trị viên để nhận liên kết riêng.')}

@router.get('/admin/registrations')
def registrations(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    return {'items':[{'id':u.id,'name':u.name,'email':u.email,'created_at':u.created_at.isoformat()} for u in db.scalars(select(m.User).where(m.User.workspace_id==user.workspace_id,m.User.registration_pending.is_(True)).order_by(m.User.created_at))]}

@router.post('/admin/registrations/{id}/approve')
def approve(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    target=db.scalar(select(m.User).where(m.User.id==id,m.User.workspace_id==user.workspace_id).with_for_update())
    if not target or not target.registration_pending:raise HTTPException(409,'Yêu cầu đã được xử lý hoặc không tồn tại.')
    target.registration_pending=False;target.active=True;target.role='Employee'
    audit(db,user,'account.registration_approved',target.id);db.commit();return {'ok':True}

@router.post('/admin/registrations/{id}/reject')
def reject(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    target=db.scalar(select(m.User).where(m.User.id==id,m.User.workspace_id==user.workspace_id).with_for_update())
    if not target or not target.registration_pending:raise HTTPException(409,'Yêu cầu đã được xử lý hoặc không tồn tại.')
    target.registration_pending=False;target.active=False
    audit(db,user,'account.registration_rejected',target.id);db.commit();return {'ok':True}

def process_email(db,job):
    row=db.scalar(select(m.AccountEmail).where(m.AccountEmail.id==job.resource).with_for_update())
    if not row:return
    if row.status in ('preparing','sending'):
        row.status='unknown';row.payload_ciphertext='';row.error='Worker bị gián đoạn; không tự gửi lại.';db.commit();return
    if row.status!='queued':return
    target=db.get(m.User,row.user_id);ticket=db.get(m.AccountToken,row.token_id)
    if not target or not target.active or target.registration_pending or target.email!=row.recipient or not ticket or ticket.used_at or utc(ticket.expires_at)<=m.now():
        row.status='cancelled';row.payload_ciphertext='';db.commit();return
    owner=db.get(m.User,row.sender_user_id);connection=db.get(m.GmailConnection,row.sender_user_id)
    if not owner or not owner.active or owner.workspace_id!=target.workspace_id or 'mail.send' not in permissions(db,owner) or not connection or connection.workspace_id!=target.workspace_id or connection.email!=settings.gmail_sender.lower() or gmail.SEND_SCOPE not in connection.scopes:
        row.status='failed';row.payload_ciphertext='';row.error='Kết nối gửi thư khôi phục không còn khả dụng.';db.commit();return
    try:
        url=gmail.decrypt(row.payload_ciphertext)['url']
        raw_token=parse_qs(urlsplit(url).fragment)['token'][0]
        if hashlib.sha256(raw_token.encode()).hexdigest()!=ticket.token_hash:raise ValueError('Token mismatch')
        row.status='preparing';db.commit()
        token=gmail.access(db,connection)
        # Refresh token state after a Google refresh may commit the transaction.
        db.refresh(ticket);db.refresh(target);db.refresh(owner);db.refresh(connection)
        if ticket.used_at or utc(ticket.expires_at)<=m.now() or not target.active or target.registration_pending or target.email!=row.recipient:
            row.status='cancelled';row.payload_ciphertext='';db.commit();return
        if not owner.active or 'mail.send' not in permissions(db,owner) or connection.email!=settings.gmail_sender.lower() or gmail.SEND_SCOPE not in connection.scopes:
            row.status='failed';row.payload_ciphertext='';row.error='Quyền gửi thư khôi phục đã thay đổi.';db.commit();return
        msg=EmailMessage();msg['From']=connection.email;msg['To']=row.recipient;msg['Subject']='APBWAS — đặt lại mật khẩu'
        msg['Date']=formatdate(localtime=False);msg['Message-ID']=f'<apbwas-account-{row.id}@gmail.com>'
        msg.set_content('Bạn đã yêu cầu đặt lại mật khẩu APBWAS. Mở liên kết sau để chọn mật khẩu mới:\n\n'+url+'\n\nLiên kết chỉ dùng một lần và hết hạn sau 1 giờ. Nếu bạn không yêu cầu, hãy bỏ qua thư này. Không gửi liên kết cho người khác.')
        row.status='sending';db.commit()
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            response=client.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':'Bearer '+token},json={'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()})
        if 200<=response.status_code<300:
            remote=response.json().get('id');row.status='sent' if remote else 'unknown'
            if remote:row.remote_id=str(remote)[:255];row.sent_at=m.now()
        elif response.status_code in (400,401,403,404,429):row.status='failed'
        else:row.status='unknown'
    except (HTTPException,ValueError,KeyError,TypeError,IndexError):row.status='unknown' if row.status=='sending' else 'failed'
    except httpx.HTTPError:row.status='unknown' if row.status=='sending' else 'failed'
    row.payload_ciphertext=''
    if row.status!='sent':row.error='Không xác nhận được việc gửi thư. Có thể yêu cầu liên kết mới hoặc liên hệ quản trị viên.'
    audit(db,'system','account.recovery_email_'+row.status,row.id);db.commit()
