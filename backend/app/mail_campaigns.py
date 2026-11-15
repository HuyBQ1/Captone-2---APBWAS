"""Reviewed employee mail drafts and durable individual deliveries."""
import base64,re
from collections import Counter
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate
import httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select,func
from . import models as m,gmail
from .db import get_db
from .auth import current_user
from .permissions import require,permissions
from .schemas import StrictModel
from .audit import audit
from .config import settings

router=APIRouter(prefix='/api/mail')

def address(value):
    value=(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',value) or len(value)>180:return None
    domain=value.split('@')[1]
    if domain in ('example.com','example.org','example.net') or domain.endswith(('.example','.demo','.test','.invalid','.localhost')):return None
    return value

def contact(u):
    email=address(u.delivery_email or u.email)
    return {'id':u.id,'name':u.name,'role':u.role,'department':u.department,'login_email':u.email,
            'delivery_email':u.delivery_email,'recipient':email,'ready':bool(email)}

@router.get('/employees')
def employees(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send')
    return {'can_manage': 'users.manage' in permissions(db,user),'current_user_id':user.id,
            'items':[contact(u) for u in db.scalars(select(m.User).where(m.User.workspace_id==user.workspace_id,m.User.active.is_(True)).order_by(m.User.name))]}

class ContactInput(StrictModel):
    delivery_email:str=Field(max_length=180)

@router.put('/employees/{id}')
def update_contact(id:str,body:ContactInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send')
    if id!=user.id:require(db,user,'users.manage')
    u=db.get(m.User,id)
    if not u or u.workspace_id!=user.workspace_id or not u.active:raise HTTPException(404,'Không tìm thấy nhân viên.')
    value=address(body.delivery_email)
    if body.delivery_email.strip() and not value:raise HTTPException(422,'Nhập địa chỉ nhận thư thật; email mẫu không thể nhận thư.')
    u.delivery_email=value
    audit(db,user,'mail.contact_updated',u.id,{'delivery_email':value});db.commit()
    return contact(u)

class Draft(StrictModel):
    subject:str=Field(min_length=1,max_length=180)
    body_text:str=Field(min_length=1,max_length=20000)
    recipient_ids:list[str]|None=Field(default=None,max_length=100)
    attachment_ids:list[str]=Field(default_factory=list,max_length=5)
    idempotency_key:str=Field(min_length=10,max_length=100)

def attachments(db,user,ids,lock=False):
    from .office_files import check_access
    rows=[]
    for id in dict.fromkeys(ids or []):
        query=select(m.GeneratedFile).where(m.GeneratedFile.id==id,m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id)
        if lock:query=query.with_for_update()
        f=db.scalar(query)
        if not f:raise HTTPException(404,'Không tìm thấy tệp đính kèm của bạn.')
        check_access(db,user,f);rows.append(f)
    if len(rows)>5 or sum(f.size for f in rows)>12*1024*1024:raise HTTPException(422,'Tối đa 5 tệp và tổng dung lượng 12 MB cho mỗi email.')
    return rows

def create_draft(db,user,body,workflow=None):
    if not body.subject.strip() or not body.body_text.strip() or '\r' in body.subject or '\n' in body.subject:raise HTTPException(422,'Cần tiêu đề một dòng và nội dung thư.')
    if body.recipient_ids==[]:raise HTTPException(422,'Chọn ít nhất một nhân viên.')
    existing=db.scalar(select(m.MailCampaign).where(m.MailCampaign.idempotency_key==body.idempotency_key))
    if existing:
        if existing.user_id!=user.id or existing.workspace_id!=user.workspace_id:raise HTTPException(409,'Mã bản nháp đã được sử dụng.')
        return existing
    query=select(m.User).where(m.User.workspace_id==user.workspace_id,m.User.active.is_(True)).order_by(m.User.name)
    if body.recipient_ids is not None:query=query.where(m.User.id.in_(body.recipient_ids))
    people=list(db.scalars(query.limit(101)))
    if len(people)>100:raise HTTPException(422,'Mỗi đợt tối đa 100 nhân viên; hãy chọn một nhóm nhỏ hơn.')
    selected={p.id for p in people}
    if body.recipient_ids is not None and set(body.recipient_ids)-selected:raise HTTPException(422,'Có nhân viên không còn hoạt động hoặc không thuộc workspace.')
    files=attachments(db,user,body.attachment_ids,lock=True)
    c=m.MailCampaign(user_id=user.id,workspace_id=user.workspace_id,workflow_id=workflow.id if workflow else None,attachment_ids=[f.id for f in files],
                     idempotency_key=body.idempotency_key,subject=body.subject.strip(),body_text=body.body_text.strip(),requested_ids=body.recipient_ids,skipped=[])
    db.add(c);db.flush();seen=set();skipped=[]
    for u in people:
        email=address(u.delivery_email or u.email)
        if not email or email in seen:
            skipped.append({'id':u.id,'name':u.name,'reason':'Email không hợp lệ / email mẫu' if not email else 'Trùng địa chỉ nhận thư'});continue
        seen.add(email)
        db.add(m.MailDelivery(campaign_id=c.id,employee_id=u.id,recipient=email,recipient_name=u.name))
    c.skipped=skipped
    audit(db,user,'mail.draft_created',c.id,{'recipients':len(seen),'skipped':len(skipped)});db.flush()
    return c

def owned(db,user,id,lock=False):
    q=select(m.MailCampaign).where(m.MailCampaign.id==id,m.MailCampaign.user_id==user.id,m.MailCampaign.workspace_id==user.workspace_id)
    if lock:q=q.with_for_update()
    c=db.scalar(q.execution_options(populate_existing=True))
    if not c:raise HTTPException(404,'Không tìm thấy đợt gửi thư.')
    return c

def view(db,c):
    from .office_files import metadata
    owner=db.get(m.User,c.user_id)
    try:files=[metadata(f) for f in attachments(db,owner,c.attachment_ids)];file_error=None
    except HTTPException:files=[];file_error='Quyền truy cập tệp đính kèm đã thay đổi; chưa thể gửi bản nháp này.'
    deliveries=list(db.scalars(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id).order_by(m.MailDelivery.recipient_name)))
    return {'id':c.id,'subject':c.subject,'body_text':c.body_text,'status':c.status,'revision':c.revision,'sender_email':c.sender_email,'attachments':files,'attachment_error':file_error,
            'cancel_requested':c.cancel_requested,'created_at':c.created_at.isoformat(),'skipped':c.skipped,'error':c.error,
            'counts':dict(Counter(d.status for d in deliveries)),
            'recipients':[{'id':d.id,'name':d.recipient_name,'email':d.recipient,'status':d.status,'error':d.error} for d in deliveries]}

@router.post('/campaigns',status_code=201)
def draft(body:Draft,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send');c=create_draft(db,user,body);db.commit();return view(db,c)

@router.get('/campaigns')
def campaigns(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send')
    return [view(db,c) for c in db.scalars(select(m.MailCampaign).where(m.MailCampaign.user_id==user.id,m.MailCampaign.workspace_id==user.workspace_id).order_by(m.MailCampaign.created_at.desc()).limit(50))]

@router.get('/campaigns/{id}')
def detail(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send');return view(db,owned(db,user,id))

class EditDraft(StrictModel):
    subject:str=Field(min_length=1,max_length=180)
    body_text:str=Field(min_length=1,max_length=20000)
    revision:int=Field(ge=1)

@router.put('/campaigns/{id}')
def edit_draft(id:str,body:EditDraft,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send');c=owned(db,user,id,True)
    if c.status!='draft' or c.revision!=body.revision:raise HTTPException(409,'Bản nháp đã thay đổi hoặc đã được duyệt gửi.')
    if not body.subject.strip() or not body.body_text.strip() or '\r' in body.subject or '\n' in body.subject:raise HTTPException(422,'Cần tiêu đề một dòng và nội dung thư.')
    c.subject=body.subject.strip();c.body_text=body.body_text.strip();c.revision+=1
    audit(db,user,'mail.draft_edited',c.id,{'revision':c.revision});db.commit();return view(db,c)

class Send(StrictModel):
    confirmed:bool
    revision:int=Field(ge=1)

@router.post('/campaigns/{id}/send')
def send(id:str,body:Send,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send')
    if not body.confirmed:raise HTTPException(422,'Cần xem trước và xác nhận gửi thư.')
    # Serialize quota reservations for one Gmail owner.
    c=owned(db,user,id,True)
    row=gmail.connection(db,user,True)
    if c.revision!=body.revision:raise HTTPException(409,'Bản nháp đã thay đổi. Hãy xem lại.')
    if c.status!='draft':return view(db,c)
    attachments(db,user,c.attachment_ids)
    deliveries=list(db.scalars(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id)))
    if not deliveries:raise HTTPException(422,'Chưa có email nhân viên hợp lệ. Cập nhật địa chỉ và tạo bản nháp mới.')
    for d in deliveries:
        u=db.get(m.User,d.employee_id,populate_existing=True)
        if not u or not u.active or u.workspace_id!=user.workspace_id or address(u.delivery_email or u.email)!=d.recipient:
            raise HTTPException(409,'Danh sách nhân viên đã thay đổi. Tạo bản nháp mới để xác nhận đúng người nhận.')
    reserved=db.scalar(select(func.count()).select_from(m.MailDelivery).join(m.MailCampaign,m.MailDelivery.campaign_id==m.MailCampaign.id).where(
        m.MailCampaign.user_id==user.id,m.MailCampaign.approved_at>=m.now()-timedelta(hours=24),m.MailCampaign.status!='draft'))
    if reserved+len(deliveries)>settings.mail_bulk_daily_limit:raise HTTPException(429,'Đạt giới hạn gửi của ứng dụng trong 24 giờ. Hãy thử lại sau.')
    c.status='queued';c.approved_at=m.now();c.sender_email=row.email
    db.add(m.Job(kind='mail',resource=c.id));audit(db,user,'mail.send_confirmed',c.id,{'recipients':len(deliveries),'sender':row.email});db.commit()
    return view(db,c)

@router.post('/campaigns/{id}/cancel')
def cancel(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'mail.send');c=owned(db,user,id,True)
    if c.status in ('draft','queued','sending'):
        c.cancel_requested=True
        if c.status=='draft':c.status='cancelled'
        audit(db,user,'mail.cancel_requested',c.id);db.commit()
    return view(db,c)

def deliver(sender,recipient,subject,body,delivery_id,token,files=()):
    msg=EmailMessage();msg['From']=sender;msg['To']=recipient;msg['Subject']=subject
    msg['Date']=formatdate(localtime=False);msg['Message-ID']=f'<apbwas-{delivery_id}@gmail.com>';msg.set_content(body)
    from .office_files import MIMES
    for f in files:
        major,minor=MIMES[f.kind].split('/',1);msg.add_attachment(f.content,maintype=major,subtype=minor,filename=f.filename)
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            response=client.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':'Bearer '+token},json={'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()})
        if response.status_code in (400,401,403,404,429):return 'failed',None,'Google từ chối yêu cầu gửi. Kiểm tra quyền hoặc giới hạn tài khoản.'
        if 200<=response.status_code<300:
            remote=response.json().get('id')
            if remote:return 'sent',str(remote)[:255],None
    except (httpx.HTTPError,ValueError,AttributeError):pass
    return 'unknown',None,'Chưa xác định Google đã nhận thư hay chưa. Kiểm tra Thư đã gửi trước khi gửi lại.'

def process_mail(db,job):
    c=db.get(m.MailCampaign,job.resource)
    if not c or c.status not in ('queued','sending'):return
    ids=list(db.scalars(select(m.MailDelivery.id).where(m.MailDelivery.campaign_id==c.id).order_by(m.MailDelivery.created_at,m.MailDelivery.id)))
    for id in ids:
        # Claim the delivery under a DB lock, then commit before any network call.
        # A crashed attempt is UNKNOWN and is never automatically retried.
        c=db.scalar(select(m.MailCampaign).where(m.MailCampaign.id==c.id).with_for_update().execution_options(populate_existing=True))
        d=db.scalar(select(m.MailDelivery).where(m.MailDelivery.id==id).with_for_update().execution_options(populate_existing=True))
        if d.status=='sending':d.status='unknown';d.error='Worker bị ngắt trong khi gửi. Kiểm tra Gmail trước khi gửi lại.';db.commit();continue
        if d.status!='pending':db.commit();continue
        user=db.get(m.User,c.user_id,populate_existing=True)
        employee=db.get(m.User,d.employee_id,populate_existing=True)
        try:
            if c.cancel_requested:raise HTTPException(409,'Đã dừng các thư chưa gửi.')
            if not user or user.workspace_id!=c.workspace_id:raise HTTPException(403,'Người gửi không còn trong workspace.')
            require(db,user,'mail.send')
            if not employee or not employee.active or employee.workspace_id!=c.workspace_id or address(employee.delivery_email or employee.email)!=d.recipient:raise HTTPException(409,'Nhân viên hoặc địa chỉ nhận thư đã thay đổi.')
            row=gmail.connection(db,user)
            if row.email!=c.sender_email:raise HTTPException(409,'Tài khoản Gmail gửi đã thay đổi.')
            files=attachments(db,user,c.attachment_ids)
            token=gmail.access(db,row)
        except HTTPException as exc:
            d.status='skipped';d.error=str(exc.detail)[:500];db.commit();continue
        # access() may commit a token refresh; reacquire and recheck the claim.
        c=db.scalar(select(m.MailCampaign).where(m.MailCampaign.id==c.id).with_for_update().execution_options(populate_existing=True))
        d=db.scalar(select(m.MailDelivery).where(m.MailDelivery.id==id).with_for_update().execution_options(populate_existing=True))
        if d.status!='pending':db.commit();continue
        if c.cancel_requested:d.status='skipped';d.error='Đã dừng trước khi gửi.';db.commit();continue
        d.status='sending';d.attempted_at=m.now();c.status='sending';job.lease_until=m.now()+timedelta(minutes=10)
        audit(db,user,'mail.delivery_started',d.id,{'campaign':c.id});db.commit()
        d.status,d.remote_id,d.error=deliver(c.sender_email,d.recipient,c.subject,c.body_text,d.id,token,files)
        audit(db,user,'mail.delivery_finished',d.id,{'campaign':c.id,'status':d.status});db.commit()
    db.refresh(c)
    statuses=list(db.scalars(select(m.MailDelivery.status).where(m.MailDelivery.campaign_id==c.id)))
    c.status='completed' if statuses and all(s=='sent' for s in statuses) else 'partial' if 'sent' in statuses else 'cancelled' if c.cancel_requested else 'unknown' if 'unknown' in statuses else 'failed'
    db.commit()

def draft_from_tool(db,user,workflow,args):
    require(db,user,'mail.send')
    body=Draft(subject=args.get('subject') or '',body_text=args.get('body_text') or '',recipient_ids=args.get('recipient_ids'),idempotency_key='workflow-mail-'+workflow.id)
    c=create_draft(db,user,body,workflow)
    return {'campaign_id':c.id,'summary':f'Đã tạo bản nháp email “{c.subject}”. [Xem người nhận và xác nhận gửi](/mail/campaigns/{c.id}). Chưa gửi thư nào. Email mẫu hoặc trùng địa chỉ được bỏ qua.'}

def report_draft(db,user,workflow,args):
    from .office_files import check_access
    from sqlalchemy.orm import defer
    require(db,user,'mail.send')
    query=select(m.GeneratedFile).options(defer(m.GeneratedFile.content)).join(m.Workflow,m.Workflow.id==m.GeneratedFile.workflow_id).where(m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id,m.Workflow.conversation_id==workflow.conversation_id)
    candidates=list(db.scalars(query.order_by(m.GeneratedFile.created_at.desc(),m.GeneratedFile.id.desc()).limit(100))) if workflow.conversation_id else []
    month=args.get('month')
    if month:candidates=[f for f in candidates if f.source.get('month')==month]
    elif candidates:month=candidates[0].source.get('month')
    chosen={}
    for f in candidates:
        if f.source.get('month')!=month or f.kind in chosen:continue
        check_access(db,user,f);chosen[f.kind]=f
    if not chosen:
        return {'month':month,'summary':'Chưa có tệp báo cáo phù hợp'+(' tháng '+month if month else '')+' trong hội thoại này. Hãy tạo Word hoặc Excel cho kỳ đó trước, rồi yêu cầu gửi file báo cáo cho toàn bộ nhân viên. Chưa tạo hay gửi email.'}
    label='Báo cáo'+(' tháng '+month if month else '')
    text='Kính gửi toàn thể nhân viên,\n\nXin gửi các tệp báo cáo đính kèm'+(' cho tháng '+month if month else '')+'. Vui lòng xem nội dung và số liệu trong tệp.\n\nTrân trọng.'
    body=Draft(subject=label,body_text=text,attachment_ids=[f.id for f in chosen.values()],idempotency_key='workflow-mail-'+workflow.id)
    c=create_draft(db,user,body,workflow)
    return {'campaign_id':c.id,'month':month,'summary':f'Đã tạo bản nháp email “{c.subject}” với {len(chosen)} tệp Word/Excel đính kèm. [Mở email để xem người nhận, tệp và xác nhận gửi](/mail/campaigns/{c.id}). Chưa gửi thư nào.'}

def open_from_conversation(db,user,workflow):
    require(db,user,'mail.send')
    c=None
    if workflow.conversation_id:
        c=db.scalar(select(m.MailCampaign).join(m.Workflow,m.Workflow.id==m.MailCampaign.workflow_id).where(
            m.Workflow.conversation_id==workflow.conversation_id,m.MailCampaign.user_id==user.id,
            m.MailCampaign.workspace_id==user.workspace_id).order_by(m.MailCampaign.created_at.desc(),m.MailCampaign.id.desc()).limit(1))
    if not c:return {'summary':'Chưa có email nào được tạo trong hội thoại này. Hãy yêu cầu soạn email trước, hoặc mở Gmail → Soạn email cho nhân viên để xem lịch sử của bạn.'}
    return {'campaign_id':c.id,'mail_status':c.status,'summary':f'Email gần nhất trong hội thoại: “{c.subject}”. [Mở email để xem người nhận và nội dung](/mail/campaigns/{c.id}). Bấm nút mở email bên dưới; chỉ khi bạn xác nhận trên trang email thì hệ thống mới xếp hàng gửi. Lệnh chat này không gửi thư.'}

def revenue_draft(db,user,workflow,args):
    from .db import read_only_db
    from .tools import revenue
    from zoneinfo import ZoneInfo
    require(db,user,'mail.send');require(db,user,'sales.read')
    if user.workspace_id!='primary':raise HTTPException(403,'Workspace chưa cấu hình nguồn doanh thu.')
    with read_only_db(db) as reader:data=revenue(reader,args.get('month'),cutoff=m.now())
    amount=lambda value:f'{value:,}'.replace(',','.')+' ₫'
    stamp=m.now().astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')
    lines=['Kính gửi toàn thể nhân viên,','',f"Báo cáo doanh thu tháng {data['month']}:",f"Tổng doanh thu ghi nhận: {amount(data['total'])}.",f'Cập nhật lúc {stamp} (giờ Việt Nam).']
    if settings.sample_data or settings.demo_mode:lines.extend(['','Lưu ý: hệ thống đang sử dụng dữ liệu mẫu/mô phỏng Nova Commerce.'])
    if not data['rows']:lines.extend(['','Chưa có giao dịch bán được ghi nhận trong database cho kỳ này. Tổng 0 ₫ không đủ để kết luận doanh nghiệp không phát sinh doanh thu.'])
    else:
        lines.extend(['','Doanh thu theo danh mục:'])
        lines.extend(f"- {r['category']}: {amount(r['revenue'])}." for r in data['rows'])
    lines.extend(['','Nguồn: giao dịch bán hàng và danh mục sản phẩm được lưu trong APBWAS. Đây là doanh thu ghi nhận, chưa phải lợi nhuận.','','Trân trọng,','Ban quản lý'])
    output=draft_from_tool(db,user,workflow,{'subject':f"Báo cáo doanh thu tháng {data['month']}",'body_text':'\n'.join(lines)})
    return {**output,'month':data['month'],'revenue':data['total'],'source':data['source'],
            'summary':f"Doanh thu ghi nhận tháng {data['month']}: **{amount(data['total'])}**. "+('Chưa có giao dịch trong database cho kỳ này. ' if not data['rows'] else '')+output['summary']}
