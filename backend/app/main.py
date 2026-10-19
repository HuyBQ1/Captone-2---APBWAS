import asyncio, csv, hashlib, io, json, uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, func, delete, text
from sqlalchemy.exc import IntegrityError
from .db import Session, get_db
from . import models as m, schemas as s
from .config import settings
from .auth import current_user, hasher, create_session, utc
from .permissions import require, permissions, visible, DEFAULT_PERMISSIONS
from .audit import audit, verify
from .usage import quota, configuration, cache
from .tools import REGISTRY, revenue
from .retrieval import search, allowed_scopes
from .approvals import decide
from .workflows import emit

app=FastAPI(title='APBWAS API',version='1.0.0',docs_url='/api/docs',openapi_url='/api/openapi.json')

@app.middleware('http')
async def origin_guard(request,call_next):
    origin=request.headers.get('origin')
    if origin and request.method not in ('GET','HEAD','OPTIONS'):
        from urllib.parse import urlparse
        if urlparse(origin).netloc!=request.headers.get('host') and origin!=settings.frontend_origin:
            return JSONResponse({'error':{'code':403,'message':'Origin không hợp lệ.'}},status_code=403)
    return await call_next(request)

@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse({'error':{'code':exc.status_code,'message':exc.detail}},status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse({'error':{'code':422,'message':'Thông tin không hợp lệ. Kiểm tra lại các trường nhập.'}},status_code=422)

@app.exception_handler(IntegrityError)
async def conflict(request,exc):
    return JSONResponse({'error':{'code':409,'message':'Dữ liệu trùng hoặc đã thay đổi. Vui lòng tải lại.'}},status_code=409)

def data(row):
    return {column.name: (float(value) if isinstance(value,Decimal) else value.isoformat() if hasattr(value,'isoformat') else value)
            for column in row.__table__.columns if column.name not in ('password_hash','token_hash','embedding','path')
            for value in [getattr(row,column.name)]}

def workflow_metadata(row):
    value=data(row)
    # List APIs don't distribute tool outputs or document excerpts.
    value['result']={}
    value['plan']=[]
    return value

def user_data(db,user):
    return {**data(user),'permissions':permissions(db,user),'demo_mode':settings.demo_mode,'provider':settings.provider}

def get_owned(db,model,id,user):
    item=db.get(model,id)
    if not item:
        raise HTTPException(404,'Không tìm thấy tài nguyên.')
    if not visible(user,item.user_id):
        raise HTTPException(403,'Bạn không có quyền xem tài nguyên này.')
    if model==m.Workflow:
        for step in item.plan:
            if step['tool'] in REGISTRY:
                require(db,user,REGISTRY[step['tool']]['permission'])
        for source in item.result.get('sources',[]):
            document=db.get(m.Document,source['document_id'])
            if document and document.scope not in allowed_scopes(user):
                raise HTTPException(403,'Workflow chứa tài liệu ngoài phạm vi được phép.')
    return item

def page(db,query,page=1,size=10):
    page=max(1,page); size=max(1,min(100,size))
    total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return {'items':[data(row) for row in db.scalars(query.offset((page-1)*size).limit(size))], 'total':total,'page':page,'size':size}

@app.post('/api/auth/login')
def login(body:s.Login,request:Request,response:Response,db=Depends(get_db)):
    try:
        key='login:'+hashlib.sha256((request.client.host+body.email.lower()).encode()).hexdigest()
        hits=cache.incr(key)
        if hits==1: cache.expire(key,60)
        if hits>10: raise HTTPException(429,'Đăng nhập quá nhiều lần. Thử lại sau 1 phút.')
    except __import__('redis').RedisError:
        # Safe failure in Connected Mode; Demo Mode can run locally without Redis.
        if not settings.demo_mode: raise HTTPException(503,'Session service tạm thời không khả dụng.')
    user=db.scalar(select(m.User).where(m.User.email==body.email.lower()))
    valid=False
    try:
        valid=hasher.verify(user.password_hash if user else hasher.hash('constant-dummy-password'),body.password)
    except Exception:
        pass
    if not valid or not user or not user.active:
        audit(db,'anonymous','auth.failed',payload={'email':body.email[:180]})
        db.commit()
        raise HTTPException(401,'Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.')
    token=create_session(db,user)
    response.set_cookie('apbwas_session',token,httponly=True,samesite='lax',secure=settings.cookie_secure,max_age=settings.session_hours*3600,path='/')
    audit(db,user,'auth.login')
    db.commit()
    return user_data(db,user)

@app.get('/api/auth/me')
def me(user=Depends(current_user),db=Depends(get_db)):
    return user_data(db,user)

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    token=request.cookies.get('apbwas_session','')
    db.execute(delete(m.AuthSession).where(m.AuthSession.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    response.delete_cookie('apbwas_session',path='/')
    audit(db,user,'auth.logout'); db.commit()
    return {'ok':True}

@app.patch('/api/auth/profile')
def profile(body:s.Profile,user=Depends(current_user),db=Depends(get_db)):
    user.name=body.name
    audit(db,user,'profile.updated'); db.commit()
    return user_data(db,user)

@app.post('/api/auth/password')
def password(body:s.ChangePassword,response:Response,user=Depends(current_user),db=Depends(get_db)):
    try: hasher.verify(user.password_hash,body.current_password)
    except Exception: raise HTTPException(400,'Mật khẩu hiện tại không đúng.')
    user.password_hash=hasher.hash(body.new_password)
    db.execute(delete(m.AuthSession).where(m.AuthSession.user_id==user.id))
    response.delete_cookie('apbwas_session',path='/')
    audit(db,user,'password.changed'); db.commit()
    return {'ok':True}

@app.get('/api/conversations')
def conversations(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1):
    return page(db,select(m.Conversation).where(m.Conversation.user_id==user.id,m.Conversation.title.ilike('%'+q+'%')).order_by(m.Conversation.created_at.desc()),page_number,30)

@app.get('/api/conversations/{id}')
def conversation(id:str,user=Depends(current_user),db=Depends(get_db)):
    item=get_owned(db,m.Conversation,id,user)
    # Conversations are private even to managers.
    if item.user_id!=user.id: raise HTTPException(403,'Hội thoại riêng tư.')
    return {**data(item),'messages':[data(row) for row in db.scalars(select(m.Message).where(m.Message.conversation_id==id).order_by(m.Message.created_at))],
            'workflows':[workflow_metadata(wf) for wf in db.scalars(select(m.Workflow).where(m.Workflow.conversation_id==id).order_by(m.Workflow.created_at))]}

@app.post('/api/workflows',status_code=202)
def create_workflow(body:s.RequestWorkflow,user=Depends(current_user),db=Depends(get_db)):
    existing=db.scalar(select(m.Workflow).where(m.Workflow.idempotency_key==body.idempotency_key))
    if existing:
        if existing.user_id!=user.id: raise HTTPException(409,'Idempotency key bị trùng.')
        if existing.request!=body.request: raise HTTPException(409,'Idempotency key không khớp nội dung.')
        return data(existing)
    quota(db,user)
    conv=db.get(m.Conversation,body.conversation_id) if body.conversation_id else None
    if body.conversation_id and (not conv or conv.user_id!=user.id): raise HTTPException(403,'Hội thoại không hợp lệ.')
    if not conv:
        conv=m.Conversation(user_id=user.id,title=body.request[:90]); db.add(conv); db.flush()
    wf=m.Workflow(user_id=user.id,conversation_id=conv.id,request=body.request,idempotency_key=body.idempotency_key)
    db.add(wf); db.flush()
    db.add(m.Message(conversation_id=conv.id,role='user',content=body.request))
    db.add(m.Job(resource=wf.id,kind='workflow'))
    emit(db,wf,'queued',{'message':'Yêu cầu đã vào hàng đợi worker.'})
    audit(db,user,'workflow.requested',wf.id,{'request':body.request})
    db.commit()
    return data(wf)

@app.get('/api/workflows')
def workflows(user=Depends(current_user),db=Depends(get_db),q:str='',status:str='',page_number:int=1,size:int=10,days:int=90,creator:str=''):
    query=select(m.Workflow).where(m.Workflow.request.ilike('%'+q+'%'),m.Workflow.created_at>=m.now()-timedelta(days=max(1,min(days,3650))))
    if user.role=='Employee': query=query.where(m.Workflow.user_id==user.id)
    if status: query=query.where(m.Workflow.status==status)
    if creator: query=query.where(m.Workflow.user_id==creator)
    result=page(db,query.order_by(m.Workflow.created_at.desc()),page_number,size)
    for item in result['items']:
        item['result']={};item['plan']=[]
    return result

@app.get('/api/workflows/{id}')
def workflow(id:str,user=Depends(current_user),db=Depends(get_db)):
    wf=get_owned(db,m.Workflow,id,user)
    return {**data(wf),'steps':[data(row) for row in db.scalars(select(m.WorkflowStep).where(m.WorkflowStep.workflow_id==id).order_by(m.WorkflowStep.position))],
            'tools':[data(row) for row in db.scalars(select(m.ToolExecution).where(m.ToolExecution.workflow_id==id).order_by(m.ToolExecution.position))],
            'events':[data(row) for row in db.scalars(select(m.WorkflowEvent).where(m.WorkflowEvent.workflow_id==id).order_by(m.WorkflowEvent.sequence))]}

@app.get('/api/workflows/{id}/events')
async def events(id:str,request:Request,after:int=0,user=Depends(current_user),db=Depends(get_db)):
    get_owned(db,m.Workflow,id,user)
    try: cursor=max(after,int(request.headers.get('last-event-id','0')))
    except ValueError: raise HTTPException(422,'Event cursor không hợp lệ.')
    async def stream():
        nonlocal cursor
        token_hash=hashlib.sha256(request.cookies.get('apbwas_session','').encode()).hexdigest()
        yield ': connected\n\n'
        while not await request.is_disconnected():
            with Session() as session:
                auth_session=session.scalar(select(m.AuthSession).where(m.AuthSession.token_hash==token_hash))
                if not auth_session or utc(auth_session.expires_at)<=m.now():
                    yield 'data: '+json.dumps({'id':cursor+1,'type':'access_revoked','workflow_id':id,'timestamp':m.now().isoformat(),'payload':{'message':'Phiên đăng nhập đã kết thúc.'}})+'\n\n'
                    return
                active=session.get(m.User,user.id)
                if not active or not active.active: return
                try:
                    wf=get_owned(session,m.Workflow,id,active)
                except HTTPException:
                    yield 'data: '+json.dumps({'id':cursor+1,'type':'access_revoked','workflow_id':id,'timestamp':m.now().isoformat(),'payload':{'message':'Quyền truy cập đã thay đổi.'}})+'\n\n'
                    return
                rows=list(session.scalars(select(m.WorkflowEvent).where(m.WorkflowEvent.workflow_id==id,m.WorkflowEvent.sequence>cursor).order_by(m.WorkflowEvent.sequence)))
                for row in rows:
                    cursor=row.sequence
                    yield f'id: {row.sequence}\ndata: '+json.dumps({'id':row.sequence,'workflow_id':id,'type':row.type,'timestamp':row.created_at.isoformat(),'payload':row.payload},ensure_ascii=False)+'\n\n'
                if wf.status in ('completed','failed','cancelled'): return
            yield ': heartbeat\n\n'
            await asyncio.sleep(.5)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/workflows/{id}/cancel')
def cancel(id:str,user=Depends(current_user),db=Depends(get_db)):
    wf=get_owned(db,m.Workflow,id,user)
    # Same lock order as decision: approval first, workflow second.
    approval=db.scalar(select(m.Approval).where(m.Approval.workflow_id==id).with_for_update())
    wf=db.scalar(select(m.Workflow).where(m.Workflow.id==id).with_for_update())
    if wf.status not in ('queued','planning','running','waiting_approval'): raise HTTPException(409,'Workflow không thể hủy ở trạng thái hiện tại.')
    wf.cancel_requested=True
    if wf.status in ('queued','waiting_approval'):
        wf.status='cancelled'
        if approval: approval.status='rejected'
        emit(db,wf,'cancelled',{'message':'Workflow đã được hủy.'})
    audit(db,user,'workflow.cancel_requested',id); db.commit()
    return data(wf)

@app.post('/api/workflows/{id}/retry')
def retry(id:str,user=Depends(current_user),db=Depends(get_db)):
    wf=get_owned(db,m.Workflow,id,user)
    if wf.status!='failed' or any(step['tool']=='propose_inventory_adjustment' for step in wf.plan):
        raise HTTPException(409,'Chỉ retry workflow lỗi gồm các bước chỉ đọc/tạo báo cáo idempotent.')
    wf.status='queued'; wf.error=None; wf.deadline=None
    job=db.scalar(select(m.Job).where(m.Job.resource==id)); job.status='queued'
    emit(db,wf,'queued',{'message':'Retry từ checkpoint đã lưu.'})
    audit(db,user,'workflow.retried',id); db.commit()
    return data(wf)

@app.get('/api/approvals')
def approvals(user=Depends(current_user),db=Depends(get_db),status:str='',page_number:int=1):
    query=select(m.Approval)
    if user.role=='Employee': query=query.where(m.Approval.user_id==user.id)
    if status: query=query.where(m.Approval.status==status)
    return page(db,query.order_by(m.Approval.created_at.desc()),page_number)

@app.get('/api/approvals/{id}')
def approval(id:str,user=Depends(current_user),db=Depends(get_db)):
    item=get_owned(db,m.Approval,id,user)
    return {**data(item),'decisions':[data(row) for row in db.scalars(select(m.ApprovalDecision).where(m.ApprovalDecision.approval_id==id).order_by(m.ApprovalDecision.created_at))]}

@app.post('/api/approvals/{id}/decision')
def decision(id:str,body:s.Decision,user=Depends(current_user),db=Depends(get_db)):
    return data(decide(db,user,id,body))

@app.get('/api/reports')
def reports(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1,days:int=90,creator:str=''):
    require(db,user,'sales.read')
    query=select(m.Report).where(m.Report.title.ilike('%'+q+'%'),m.Report.created_at>=m.now()-timedelta(days=max(1,days)))
    if creator: query=query.where(m.Report.user_id==creator)
    return page(db,query.order_by(m.Report.created_at.desc()),page_number)

@app.get('/api/reports/{id}')
def report(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read')
    return data(get_owned(db,m.Report,id,user))

@app.get('/api/reports/{id}/export')
def export(id:str,format:str='csv',user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read')
    item=get_owned(db,m.Report,id,user)
    if format=='csv':
        output=io.StringIO(); writer=csv.writer(output); writer.writerow(['Danh mục','Doanh thu VND'])
        for row in item.data['rows']: writer.writerow([row['category'],row['revenue']])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="report-{id}.csv"'})
    if format!='pdf': raise HTTPException(422,'Chỉ hỗ trợ CSV hoặc PDF.')
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import simpleSplit
    font=next((p for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf'] if Path(p).exists()),None)
    if not font: raise HTTPException(503,'Thiếu font hỗ trợ tiếng Việt cho PDF.')
    pdfmetrics.registerFont(TTFont('Vietnamese',font))
    output=io.BytesIO(); c=canvas.Canvas(output); c.setFont('Vietnamese',16); c.drawString(48,790,item.title)
    c.setFont('Vietnamese',10); c.drawString(48,760,'APBWAS • '+('Dữ liệu mô phỏng' if settings.demo_mode else 'Connected Mode'))
    y=725
    lines=[f"Kỳ: {item.data['month']}",f"Tổng doanh thu: {item.data['total']:,.0f} VND",item.data['source'],item.data['summary']]
    lines += [f"{r['category']}: {r['revenue']:,.0f} VND" for r in item.data['rows']]
    for line in lines:
        for part in simpleSplit(line,'Vietnamese',10,490): c.drawString(48,y,part); y-=22
    c.showPage(); c.save()
    return Response(output.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="report-{id}.pdf"'})

@app.get('/api/documents')
def documents(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1):
    require(db,user,'documents.read')
    query=select(m.Document).where(m.Document.scope.in_(allowed_scopes(user)),m.Document.name.ilike('%'+q+'%')).order_by(m.Document.created_at.desc())
    result=page(db,query,page_number)
    for item in result['items']: item.pop('content',None)
    return result

@app.post('/api/documents',status_code=202)
async def upload(file:UploadFile=File(...),scope:str='all',user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.write')
    if scope not in ('all',user.role): raise HTTPException(403,'Phạm vi tài liệu không hợp lệ.')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ('.pdf','.docx','.txt'): raise HTTPException(422,'Chỉ hỗ trợ PDF, DOCX và TXT.')
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024 or not content: raise HTTPException(422,'File phải từ 1 byte đến 10 MB.')
    if suffix=='.pdf' and not content.startswith(b'%PDF'): raise HTTPException(422,'PDF không hợp lệ.')
    if suffix=='.docx' and not content.startswith(b'PK'): raise HTTPException(422,'DOCX không hợp lệ.')
    if suffix=='.docx':
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(info.file_size for info in archive.infolist())>30*1024*1024:
                    raise HTTPException(422,'DOCX có kích thước giải nén vượt 30 MB.')
        except zipfile.BadZipFile:
            raise HTTPException(422,'DOCX không hợp lệ.')
    folder=Path(settings.upload_dir); folder.mkdir(parents=True,exist_ok=True)
    path=folder/(str(uuid.uuid4())+suffix); path.write_bytes(content)
    item=m.Document(user_id=user.id,name=Path(file.filename).name[:250],scope=scope,path=str(path))
    db.add(item); db.flush(); db.add(m.Job(resource=item.id,kind='document'))
    audit(db,user,'document.uploaded',item.id,{'name':item.name,'bytes':len(content)}); db.commit()
    return data(item)

@app.get('/api/documents/search')
def search_documents(q:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.read')
    if len(q)<2 or len(q)>1000: raise HTTPException(422,'Truy vấn cần 2–1000 ký tự.')
    return {'items':search(db,user,q)}

@app.get('/api/documents/{id}')
def document(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.read')
    item=db.get(m.Document,id)
    if not item: raise HTTPException(404,'Không tìm thấy tài liệu.')
    if item.scope not in allowed_scopes(user): raise HTTPException(403,'Tài liệu ngoài phạm vi được phép.')
    return {**data(item),'chunk_items':[data(row) for row in db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id==id).order_by(m.DocumentChunk.position))]}

@app.post('/api/documents/{id}/reindex')
def reindex(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.write'); document(id,user,db)
    item=db.get(m.Document,id)
    if item.status in ('uploaded','processing'): raise HTTPException(409,'Tài liệu đang xử lý.')
    item.status='uploaded'; item.error=None
    job=db.scalar(select(m.Job).where(m.Job.resource==id)); job.status='queued'
    audit(db,user,'document.reindex',id); db.commit()
    return data(item)

@app.delete('/api/documents/{id}')
def remove_document(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.write'); document(id,user,db)
    item=db.scalar(select(m.Document).where(m.Document.id==id).with_for_update())
    if item.status in ('uploaded','processing'): raise HTTPException(409,'Đợi indexing kết thúc trước khi xóa.')
    file=item.path
    db.execute(delete(m.DocumentChunk).where(m.DocumentChunk.document_id==id))
    db.execute(delete(m.Job).where(m.Job.resource==id)); db.delete(item)
    audit(db,user,'document.deleted',id); db.commit()
    if file: Path(file).unlink(missing_ok=True)
    # Retrieval is uncached, so no stale vector/cache remains.
    return {'ok':True}

@app.get('/api/data/{kind}')
def business(kind:str,user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1,low:bool=False):
    if kind in ('products','inventory'):
        require(db,user,'inventory.read')
        query=select(m.Product,m.Inventory).join(m.Inventory,m.Inventory.product_id==m.Product.id).where(m.Product.name.ilike('%'+q+'%'))
        if low: query=query.where(m.Inventory.quantity<=m.Inventory.threshold)
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.execute(query.order_by(m.Product.sku).offset((max(1,page_number)-1)*10).limit(10)).all()
        return {'items':[{**data(p),**data(i),'id':p.id} for p,i in rows],'total':total,'page':page_number,'size':10}
    if kind=='sales':
        require(db,user,'sales.read')
        query=select(m.Sale).order_by(m.Sale.date.desc())
        return page(db,query,page_number)
    raise HTTPException(404,'Nguồn dữ liệu không tồn tại.')

@app.get('/api/audit')
def logs(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1,days:int=90,actor:str='',workflow_id:str=''):
    require(db,user,'audit.read')
    query=select(m.AuditLog).where(m.AuditLog.event.ilike('%'+q+'%'),m.AuditLog.created_at>=m.now()-timedelta(days=max(1,days)))
    if user.role!='Admin':
        # Managers see their own actions and worker events correlated to their workflows.
        own_workflows=select(m.Workflow.id).where(m.Workflow.user_id==user.id)
        query=query.where((m.AuditLog.actor==user.id)|m.AuditLog.correlation_id.in_(own_workflows))
    if actor: query=query.where(m.AuditLog.actor==actor)
    if workflow_id: query=query.where(m.AuditLog.correlation_id==workflow_id)
    result=page(db,query.order_by(m.AuditLog.id.desc()),page_number)
    workflow_ids=set(db.scalars(select(m.Workflow.id).where(m.Workflow.id.in_([item['correlation_id'] for item in result['items']]))))
    for item in result['items']:item['workflow_id']=item['correlation_id'] if item['correlation_id'] in workflow_ids else None
    return {**result,'integrity':verify(db)}

@app.get('/api/overview')
def overview(user=Depends(current_user),db=Depends(get_db),days:int=30):
    query=select(m.Workflow).where(m.Workflow.created_at>=m.now()-timedelta(days=max(1,min(days,365))))
    if user.role=='Employee': query=query.where(m.Workflow.user_id==user.id)
    workflows=list(db.scalars(query.order_by(m.Workflow.created_at.desc())))
    counts={status:sum(w.status==status for w in workflows) for status in ['queued','planning','running','waiting_approval','completed','failed','cancelled']}
    report_query=select(func.count()).select_from(m.Report).where(m.Report.created_at>=m.now()-timedelta(days=days))
    if user.role=='Employee': report_query=report_query.where(m.Report.user_id==user.id)
    activity={}
    from zoneinfo import ZoneInfo
    for wf in workflows:
        day=utc(wf.created_at).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m')
        activity.setdefault(day,{'date':day,'completed':0,'failed':0,'total':0})
        activity[day]['total']+=1
        if wf.status in ('completed','failed'): activity[day][wf.status]+=1
    docs=db.scalar(select(func.count()).select_from(m.Document).where(m.Document.status=='indexed',m.Document.scope.in_(allowed_scopes(user))))
    return {'total':len(workflows),'counts':counts,'reports':db.scalar(report_query),'tokens':sum(w.tokens for w in workflows),'limits':configuration(db),
            'recent':[workflow_metadata(w) for w in workflows[:5]],'activity':list(reversed(list(activity.values()))),'indexed_documents':docs,'demo_mode':settings.demo_mode}

@app.get('/api/admin/users')
def users(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1):
    require(db,user,'users.manage')
    return page(db,select(m.User).where(m.User.name.ilike('%'+q+'%')).order_by(m.User.created_at),page_number)

@app.post('/api/admin/users')
def add_user(body:s.UserInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    item=m.User(email=body.email.lower(),name=body.name,role=body.role,password_hash=hasher.hash(body.password))
    db.add(item); db.flush(); audit(db,user,'user.created',item.id,{'role':item.role}); db.commit()
    return data(item)

@app.patch('/api/admin/users/{id}')
def edit_user(id:str,body:s.UserEdit,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    item=db.get(m.User,id)
    if not item: raise HTTPException(404,'Không tìm thấy người dùng.')
    if item.id==user.id and (not body.active or body.role!='Admin'): raise HTTPException(409,'Không thể khóa hoặc hạ quyền tài khoản quản trị đang sử dụng.')
    revoke=item.role!=body.role or item.active!=body.active
    item.name=body.name; item.role=body.role; item.active=body.active
    if revoke:db.execute(delete(m.AuthSession).where(m.AuthSession.user_id==id))
    audit(db,user,'user.updated',id,{'role':item.role,'active':item.active}); db.commit()
    return data(item)

@app.get('/api/admin/roles')
def roles(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    return {'items':[data(r) for r in db.scalars(select(m.Role))],'permissions':sorted(set(p for value in DEFAULT_PERMISSIONS.values() for p in value))}

@app.patch('/api/admin/roles/{name}')
def edit_role(name:str,body:s.RoleEdit,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    role=db.get(m.Role,name)
    if not role or any(p not in set(p for v in DEFAULT_PERMISSIONS.values() for p in v) for p in body.permissions): raise HTTPException(422,'Vai trò hoặc quyền không hợp lệ.')
    if name=='Admin' and not {'users.manage','settings.manage'}.issubset(body.permissions): raise HTTPException(409,'Admin cần giữ quyền quản trị để tránh khóa hệ thống.')
    role.permissions=sorted(set(body.permissions)); audit(db,user,'role.updated',name,{'permissions':body.permissions}); db.commit()
    return data(role)

@app.get('/api/admin/tools')
def registry(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    toggles=db.get(m.SystemSetting,'tools')
    return {'items':[{'name':name,**tool,'enabled':toggles.value.get(name,True) if toggles else True,'schema':s.ToolArgs.model_json_schema(),
                      'approval_required':tool['risk']=='high'} for name,tool in REGISTRY.items()]}

@app.patch('/api/admin/tools/{name}')
def toggle_tool(name:str,body:s.ToolToggle,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    if name not in REGISTRY: raise HTTPException(404,'Không tìm thấy công cụ.')
    row=db.get(m.SystemSetting,'tools')
    if not row: row=m.SystemSetting(key='tools',value={}); db.add(row)
    row.value={**row.value,name:body.enabled}; audit(db,user,'tool.configured',name,{'enabled':body.enabled}); db.commit()
    return {'ok':True}

@app.get('/api/admin/settings')
def config(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    return {**configuration(db),'provider':settings.provider,'model':settings.ai_model,'embedding_model':settings.embedding_model,'demo_mode':settings.demo_mode,
            'key_configured':bool(settings.openai_api_key if settings.provider=='openai' else settings.gemini_api_key)}

@app.put('/api/admin/settings')
def update_config(body:s.SettingsInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    row=db.get(m.SystemSetting,'limits')
    if not row: row=m.SystemSetting(key='limits',value={}); db.add(row)
    row.value=body.model_dump(); audit(db,user,'settings.updated',payload=body.model_dump()); db.commit()
    return configuration(db)

@app.get('/api/admin/monitoring')
def monitoring(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    db.execute(text('SELECT 1'))
    try: redis_ok=cache.ping()
    except Exception: redis_ok=False
    jobs=list(db.scalars(select(m.Job).where(m.Job.status.in_(['queued','running']))))
    tools=list(db.scalars(select(m.ToolExecution)))
    workflows=list(db.scalars(select(m.Workflow)))
    heartbeat=db.get(m.SystemSetting,'worker_heartbeat')
    alive=bool(heartbeat and (m.now()-__import__('datetime').datetime.fromisoformat(heartbeat.value['at'])).total_seconds()<20)
    return {'database':True,'redis':redis_ok,'worker':alive,'provider':'demo' if settings.demo_mode else 'configured-unverified' if settings.openai_api_key or settings.gemini_api_key else 'missing-key',
            'queued_jobs':len(jobs),'tool_calls':len(tools),'average_tool_ms':round(sum(t.duration_ms for t in tools)/len(tools)) if tools else 0,
            'failed_workflows':sum(w.status=='failed' for w in workflows),'audit_integrity':verify(db)}
