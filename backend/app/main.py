import asyncio, csv, hashlib, io, json, uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, func, delete, update, text, or_
from sqlalchemy.exc import IntegrityError
from .db import Session, get_db, read_only_db
from . import models as m, schemas as s
from .config import settings
from .auth import current_user, hasher, create_session, utc
from .permissions import require, permissions, visible, DEFAULT_PERMISSIONS
from .audit import audit, verify
from .usage import quota, configuration, cache
from .tools import REGISTRY, revenue, period
from .retrieval import search, allowed_scopes
from .approvals import decide
from .workflows import emit
from .provider import public_configuration, key_configured, ProviderError

app=FastAPI(title='APBWAS API',version='1.0.0',docs_url='/api/docs',openapi_url='/api/openapi.json')
from .product_media import router as media_router, image_metadata
app.include_router(media_router)
from .finance import router as finance_router
app.include_router(finance_router)
from .agent_management import router as agent_router
app.include_router(agent_router)
from .gmail import router as gmail_router
app.include_router(gmail_router)
from .llm_models import router as llm_router
app.include_router(llm_router)
from .office_files import router as office_router
app.include_router(office_router)
from .mail_campaigns import router as mail_campaign_router
app.include_router(mail_campaign_router)
from .public_accounts import router as public_accounts_router
app.include_router(public_accounts_router)
from .shop_connection import PREFIX as NOVA_REFERENCE_PREFIX, router as shop_router, setting as shop_setting
app.include_router(shop_router)

@app.get('/api/health')
def health():
    return {'status':'ok'}

@app.get('/api/health/ready')
def ready(db=Depends(get_db)):
    database_ok=False
    try:
        db.execute(text('SELECT 1'));database_ok=True
    except Exception:db.rollback()
    try:redis_ok=bool(cache.ping())
    except Exception:redis_ok=False
    ok=database_ok and (redis_ok or settings.demo_mode)
    return JSONResponse({'status':'ready' if ok else 'unavailable','database':database_ok,'redis':redis_ok},status_code=200 if ok else 503)

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

@app.exception_handler(ProviderError)
async def provider_error(request,exc):
    return JSONResponse({'error':{'code':503,'message':str(exc)}},status_code=503)

def data(row):
    return {column.name: (float(value) if isinstance(value,Decimal) else value.isoformat() if hasattr(value,'isoformat') else value)
            for column in row.__table__.columns if column.name not in ('password_hash','token_hash','embedding','path','agent_snapshot','credentials_ciphertext','verifier_ciphertext','digest','api_key_ciphertext','payload_ciphertext')
            for value in [getattr(row,column.name)]}

def workflow_metadata(row):
    value=data(row)
    # List APIs don't distribute tool outputs or document excerpts.
    value['result']={}
    value['plan']=[]
    return value

def user_data(db,user):
    return {**data(user),'permissions':permissions(db,user),**public_configuration()}

def get_owned(db,model,id,user):
    item=db.get(model,id)
    if not item:
        raise HTTPException(404,'Không tìm thấy tài nguyên.')
    if not visible(user,item.user_id):
        raise HTTPException(403,'Bạn không có quyền xem tài nguyên này.')
    if model in (m.Report,m.Approval):
        from .agent_runtime import can_view_run
        parent=db.get(m.Workflow,item.workflow_id)
        if parent and not can_view_run(db,user,parent):raise HTTPException(404,'Không tìm thấy tài nguyên trong workspace của bạn.')
    if model==m.Workflow:
        from .agent_runtime import can_view_run
        if not can_view_run(db,user,item):raise HTTPException(404,'Không tìm thấy lần chạy Agent trong workspace của bạn.')
        for step in item.plan:
            if step['tool'] in REGISTRY:
                require(db,user,REGISTRY[step['tool']]['permission'])
        for source in item.result.get('sources',[]):
            document=db.get(m.Document,source['document_id'])
            if not document or document.scope not in allowed_scopes(user) or (item.agent_id and document.workspace_id!=user.workspace_id):
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
    if valid and user and user.registration_pending:
        audit(db,user,'auth.registration_pending');db.commit()
        raise HTTPException(403,'Tài khoản đang chờ quản trị viên duyệt.')
    if not valid or not user or not user.active:
        audit(db,'anonymous','auth.failed',payload={'email':body.email[:180]})
        db.commit()
        raise HTTPException(401,'Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.')
    token=create_session(db,user,request)
    if hasher.check_needs_rehash(user.password_hash):user.password_hash=hasher.hash(body.password)
    response.set_cookie('apbwas_session',token,httponly=True,samesite='lax',secure=settings.cookie_secure,max_age=settings.session_hours*3600,path='/')
    audit(db,user,'auth.login')
    db.commit()
    return user_data(db,user)

@app.get('/api/auth/config')
def login_configuration(db=Depends(get_db)):
    company=db.get(m.SystemSetting,'company')
    enabled=company.value.get('demo_accounts_enabled',True) if company else True
    return {'demo_accounts':enabled and (settings.demo_mode or settings.sample_data)}

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
    values=body.model_dump(exclude_unset=True)
    if 'delivery_email' in values:
        from .mail_campaigns import address
        value=address(values['delivery_email'])
        if values['delivery_email'].strip() and not value:raise HTTPException(422,'Nhập địa chỉ email nhận thư hợp lệ.')
        values['delivery_email']=value or ''
    for key,value in values.items():setattr(user,key,value)
    audit(db,user,'profile.updated'); db.commit()
    return user_data(db,user)

@app.post('/api/auth/password')
def password(body:s.ChangePassword,response:Response,user=Depends(current_user),db=Depends(get_db)):
    try: hasher.verify(user.password_hash,body.current_password)
    except Exception: raise HTTPException(400,'Mật khẩu hiện tại không đúng.')
    user.password_hash=hasher.hash(body.new_password)
    user.must_change_password=False
    db.execute(update(m.AccountToken).where(m.AccountToken.user_id==user.id,m.AccountToken.used_at.is_(None)).values(used_at=m.now()))
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
    histories=list(db.scalars(select(m.Workflow).where(m.Workflow.conversation_id==id).order_by(m.Workflow.created_at)))
    # Assistant messages can contain the same protected data as tool outputs.
    # Message rows do not map to individual workflows, so fail closed for this conversation.
    for wf in histories:get_owned(db,m.Workflow,wf.id,user)
    return {**data(item),'messages':[data(row) for row in db.scalars(select(m.Message).where(m.Message.conversation_id==id).order_by(m.Message.created_at))],
            'workflows':[{**workflow_metadata(wf),'mail_campaign_id':wf.result.get('campaign_id') if wf.result else None} for wf in histories]}

@app.delete('/api/conversations/{id}')
def delete_conversation(id:str,user=Depends(current_user),db=Depends(get_db)):
    from .conversations import remove
    return remove(db,user,id)

@app.post('/api/workflows',status_code=202)
def create_workflow(body:s.RequestWorkflow,user=Depends(current_user),db=Depends(get_db)):
    existing=db.scalar(select(m.Workflow).where(m.Workflow.idempotency_key==body.idempotency_key))
    if existing:
        if existing.user_id!=user.id: raise HTTPException(409,'Idempotency key bị trùng.')
        if existing.request!=body.request or existing.model_ref!=body.model: raise HTTPException(409,'Idempotency key không khớp nội dung hoặc model.')
        get_owned(db,m.Workflow,existing.id,user)
        return data(existing)
    if body.model:
        from .llm_models import authorize_model
        require(db,user,'agents.run');authorize_model(db,user,body.model)
    quota(db,user)
    conv=db.scalar(select(m.Conversation).where(m.Conversation.id==body.conversation_id).with_for_update()) if body.conversation_id else None
    if body.conversation_id and (not conv or conv.user_id!=user.id): raise HTTPException(403,'Hội thoại không hợp lệ.')
    if not conv:
        conv=m.Conversation(user_id=user.id,title=body.request[:90]); db.add(conv); db.flush()
    wf=m.Workflow(user_id=user.id,conversation_id=conv.id,request=body.request,idempotency_key=body.idempotency_key,model_ref=body.model)
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
    agent_scope=select(m.Agent.id).where(m.Agent.workspace_id==user.workspace_id)
    query=query.where(or_(m.Workflow.agent_id.is_(None),(m.Workflow.agent_id.in_(agent_scope)) & (m.Workflow.user_id==user.id if user.role!='Admin' else True)))
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
    steps=list(db.scalars(select(m.WorkflowStep).where(m.WorkflowStep.workflow_id==id).order_by(m.WorkflowStep.position)))
    from .workflow_graph import execution_graph
    return {**data(wf),'steps':[data(row) for row in steps],'execution_graph':execution_graph(db,user,wf,steps),
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
    wf=db.scalar(select(m.Workflow).where(m.Workflow.id==wf.id).with_for_update().execution_options(populate_existing=True))
    if wf.result.get('conversation_deleted') or wf.result.get('mock_data_removed'):raise HTTPException(409,'Dữ liệu nguồn của lượt chạy đã bị xóa; hãy gửi yêu cầu mới.')
    if wf.status!='failed' or any(step['tool']=='propose_inventory_adjustment' for step in wf.plan):
        raise HTTPException(409,'Chỉ retry workflow lỗi gồm các bước chỉ đọc/tạo báo cáo idempotent.')
    wf.status='queued'; wf.error=None; wf.deadline=None
    job=db.scalar(select(m.Job).where(m.Job.resource==id)); job.status='queued'
    emit(db,wf,'queued',{'message':'Retry từ checkpoint đã lưu.'})
    audit(db,user,'workflow.retried',id); db.commit()
    return data(wf)

@app.get('/api/approvals')
def approvals(user=Depends(current_user),db=Depends(get_db),status:str='',page_number:int=1):
    require(db,user,'inventory.read')
    query=select(m.Approval)
    visible_runs=select(m.Workflow.id).where(or_(m.Workflow.agent_id.is_(None),(m.Workflow.agent_id.in_(select(m.Agent.id).where(m.Agent.workspace_id==user.workspace_id))) & (m.Workflow.user_id==user.id if user.role!='Admin' else True)))
    query=query.where(m.Approval.workflow_id.in_(visible_runs))
    if user.role=='Employee': query=query.where(m.Approval.user_id==user.id)
    if status: query=query.where(m.Approval.status==status)
    return page(db,query.order_by(m.Approval.created_at.desc()),page_number)

@app.get('/api/approvals/{id}')
def approval(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'inventory.read')
    item=get_owned(db,m.Approval,id,user)
    return {**data(item),'decisions':[data(row) for row in db.scalars(select(m.ApprovalDecision).where(m.ApprovalDecision.approval_id==id).order_by(m.ApprovalDecision.created_at))]}

@app.post('/api/approvals/{id}/decision')
def decision(id:str,body:s.Decision,user=Depends(current_user),db=Depends(get_db)):
    return data(decide(db,user,id,body))

@app.get('/api/reports')
def reports(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1,days:int=90,creator:str=''):
    require(db,user,'sales.read')
    query=select(m.Report).where(m.Report.title.ilike('%'+q+'%'),m.Report.created_at>=m.now()-timedelta(days=max(1,days)))
    visible_runs=select(m.Workflow.id).where(or_(m.Workflow.agent_id.is_(None),(m.Workflow.agent_id.in_(select(m.Agent.id).where(m.Agent.workspace_id==user.workspace_id))) & (m.Workflow.user_id==user.id if user.role!='Admin' else True)))
    query=query.where(m.Report.workflow_id.in_(visible_runs))
    if creator: query=query.where(m.Report.user_id==creator)
    return page(db,query.order_by(m.Report.created_at.desc()),page_number)

@app.get('/api/reports/nova-sales')
def nova_sales_report(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read')
    connection=shop_setting(db) if user.workspace_id=='primary' else None
    source=connection.value if connection else {}
    if not source.get('enabled') or not source.get('last_sync'):
        return {'synced_at':None,'sync_failed':False,'periods':[]}
    return {
        'synced_at':source['last_sync'],
        'sync_failed':bool(source.get('last_error')),
        'periods':[
            {'month':month,'revenue':totals['revenue'],'orders_created':totals['orders_created']}
            for month,totals in sorted(source.get('periods',{}).items(),reverse=True)
        ],
    }

@app.get('/api/reports/nova-sales/{month}')
def nova_sales_detail(month:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read')
    if user.workspace_id!='primary':
        raise HTTPException(404,'Không tìm thấy kỳ doanh số Nova Commerce.')
    with read_only_db(db,consistent_snapshot=True) as reader:
        connection=shop_setting(reader)
        source=connection.value if connection else {}
        totals=source.get('periods',{}).get(month)
        if not source.get('enabled') or not source.get('last_sync') or totals is None:
            raise HTTPException(404,'Không tìm thấy kỳ doanh số Nova Commerce.')

        _,start,end,_=period(month)
        product,sale=m.Product,m.Sale
        rows=reader.execute(
            select(
                product.sku,product.name,product.category,
                func.coalesce(func.sum(sale.quantity).filter(sale.quantity>0),0),
                func.coalesce(-func.sum(sale.quantity).filter(sale.quantity<0),0),
                func.coalesce(func.sum(sale.revenue).filter(sale.quantity>0),0),
                func.coalesce(-func.sum(sale.revenue).filter(sale.quantity<0),0),
            )
            .join(sale,sale.product_id==product.id)
            .where(sale.reference.startswith(NOVA_REFERENCE_PREFIX),sale.date>=start,sale.date<end)
            .group_by(product.sku,product.name,product.category)
            .order_by(func.sum(sale.revenue).desc(),product.sku)
        ).all()
        products=[]
        category_totals={}
        for sku,name,category,sold,returned,sales_amount,refund_amount in rows:
            net=int(sales_amount-refund_amount)
            products.append({'sku':sku,'name':name,'category':category,'sold':sold,'returned':returned,
                             'sales_amount':int(sales_amount),'refund_amount':int(refund_amount),'revenue':net})
            category_totals[category]=category_totals.get(category,0)+net
        categories=[{'category':category,'revenue':total} for category,total in
                    sorted(category_totals.items(),key=lambda item:(-item[1],item[0]))]
        return {
            'month':month,'synced_at':source['last_sync'],'sync_failed':bool(source.get('last_error')),
            'revenue':totals['revenue'],'orders_created':totals['orders_created'],
            'sales_amount':sum(p['sales_amount'] for p in products),
            'refund_amount':sum(p['refund_amount'] for p in products),
            'cost_of_goods':totals.get('cost_of_goods'),'expenses':totals.get('expenses'),
            'operating_profit':totals.get('operating_profit'),'products':products,'categories':categories,
        }

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
        for row in item.data['rows']:
            # Spreadsheet applications must not execute user-controlled categories.
            category=str(row['category'])
            if category.lstrip().startswith(('=','+','-','@','\t','\r')):category="'"+category
            writer.writerow([category,row['revenue']])
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
    c.setFont('Vietnamese',10); c.drawString(48,760,'APBWAS • '+('Dữ liệu mô phỏng' if settings.demo_mode or settings.sample_data else 'Connected Mode'))
    y=725
    lines=[f"Kỳ: {item.data['month']}",f"Tổng doanh thu: {item.data['total']:,.0f} VND",item.data['source'],item.data['summary']]
    lines += [f"{r['category']}: {r['revenue']:,.0f} VND" for r in item.data['rows']]
    for line in lines:
        for part in simpleSplit(line,'Vietnamese',10,490):
            if y<55:
                c.showPage();c.setFont('Vietnamese',10);y=790
            c.drawString(48,y,part);y-=22
    c.showPage(); c.save()
    return Response(output.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="report-{id}.pdf"'})

@app.get('/api/documents')
def documents(user=Depends(current_user),db=Depends(get_db),q:str='',page_number:int=1,include_archived:bool=False):
    require(db,user,'documents.read')
    query=select(m.Document).where(m.Document.scope.in_(allowed_scopes(user)),m.Document.name.ilike('%'+q+'%')).order_by(m.Document.created_at.desc())
    if not include_archived:query=query.where(m.Document.status!='archived')
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
                if not {'[Content_Types].xml','word/document.xml'}.issubset(archive.namelist()):
                    raise HTTPException(422,'Tệp ZIP không phải tài liệu DOCX hợp lệ.')
                if sum(info.file_size for info in archive.infolist())>30*1024*1024:
                    raise HTTPException(422,'DOCX có kích thước giải nén vượt 30 MB.')
        except zipfile.BadZipFile:
            raise HTTPException(422,'DOCX không hợp lệ.')
    if suffix=='.txt':
        try:content.decode('utf-8')
        except UnicodeDecodeError:raise HTTPException(422,'TXT phải được lưu bằng UTF-8.')
    item=m.Document(user_id=user.id,workspace_id=user.workspace_id,name=Path(file.filename).name[:250],scope=scope)
    db.add(item); db.flush(); db.add(m.DocumentFile(document_id=item.id,content=content));db.add(m.Job(resource=item.id,kind='document'))
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
    return {**data(item),'has_original':bool(db.scalar(select(m.DocumentFile.document_id).where(m.DocumentFile.document_id==id))),
            'chunk_items':[data(row) for row in db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id==id).order_by(m.DocumentChunk.position))]}

@app.post('/api/documents/{id}/reindex')
def reindex(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.write'); document(id,user,db)
    item=db.get(m.Document,id)
    if item.status=='archived':raise HTTPException(409,'Tài liệu đã lưu trữ; hãy sử dụng phiên bản mới trong Kho tri thức.')
    if item.status in ('uploaded','processing'): raise HTTPException(409,'Tài liệu đang xử lý.')
    item.status='uploaded'; item.error=None
    job=db.scalar(select(m.Job).where(m.Job.resource==id)); job.status='queued'
    audit(db,user,'document.reindex',id); db.commit()
    return data(item)

@app.delete('/api/documents/{id}')
def remove_document(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'documents.write'); document(id,user,db)
    item=db.scalar(select(m.Document).where(m.Document.id==id).with_for_update())
    if item.status=='archived':raise HTTPException(409,'Tài liệu lưu trữ được giữ để đối chiếu lịch sử.')
    if item.status in ('uploaded','processing'): raise HTTPException(409,'Đợi indexing kết thúc trước khi xóa.')
    file=item.path
    db.execute(delete(m.DocumentChunk).where(m.DocumentChunk.document_id==id))
    db.execute(delete(m.DocumentFile).where(m.DocumentFile.document_id==id))
    db.execute(delete(m.Job).where(m.Job.resource==id)); db.delete(item)
    audit(db,user,'document.deleted',id); db.commit()
    if file: Path(file).unlink(missing_ok=True)
    # Retrieval is uncached, so no stale vector/cache remains.
    return {'ok':True}

@app.get('/api/data/{kind}')
def business(kind:str,user=Depends(current_user),db=Depends(get_db),q:str=Query(default='',max_length=200),page_number:int=1,low:bool=False,
             month:str=Query(default='',pattern=r'^(?:\d{4}-(?:0[1-9]|1[0-2]))?$')):
    pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    if kind in ('products','inventory'):
        require(db,user,'inventory.read')
        query=select(m.Product,m.Inventory).join(m.Inventory,m.Inventory.product_id==m.Product.id).where(
            or_(m.Product.name.ilike(pattern,escape='\\'),m.Product.sku.ilike(pattern,escape='\\'),m.Product.category.ilike(pattern,escape='\\')))
        if low: query=query.where(m.Inventory.quantity<=m.Inventory.threshold)
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.execute(query.order_by(m.Product.sku).offset((max(1,page_number)-1)*10).limit(10)).all()
        images=image_metadata(db,[p.id for p,i in rows])
        return {'items':[{**data(p),**data(i),'id':p.id,'product_version':p.version,'inventory_version':i.version,**images.get(p.id,{'image_url':None,'image_source':None})} for p,i in rows],'total':total,'page':page_number,'size':10}
    if kind=='sales':
        require(db,user,'sales.read')
        query=select(m.Sale,m.Product).join(m.Product,m.Product.id==m.Sale.product_id).where(
            or_(m.Product.name.ilike(pattern,escape='\\'),m.Product.sku.ilike(pattern,escape='\\'),m.Product.category.ilike(pattern,escape='\\'),m.Sale.reference.ilike(pattern,escape='\\')))
        if month:
            try:_,start,end,_=period(month)
            except ValueError:raise HTTPException(422,'Kỳ doanh thu không hợp lệ.')
            query=query.where(m.Sale.date>=start,m.Sale.date<end)
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.execute(query.order_by(m.Sale.date.desc(),m.Sale.id).offset((max(1,page_number)-1)*10).limit(10)).all()
        return {'items':[{**data(sale),'product_name':product.name,'sku':product.sku,'category':product.category} for sale,product in rows],
                'total':total,'page':max(1,page_number),'size':10}
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
    for item in result['items']:
        item['workflow_id']=item['correlation_id'] if item['correlation_id'] in workflow_ids else None
        if item['workflow_id']:
            try:get_owned(db,m.Workflow,item['workflow_id'],user)
            except HTTPException:
                item['payload']={'redacted':True,'reason':'Quyền truy cập dữ liệu workflow đã thay đổi.'}
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
    return page(db,select(m.User).where(or_(m.User.name.ilike('%'+q+'%'),m.User.email.ilike('%'+q+'%'),m.User.department.ilike('%'+q+'%'))).order_by(m.User.created_at),page_number)

@app.post('/api/admin/users')
def add_user(body:s.UserInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    item=m.User(email=body.email.strip().lower(),name=body.name.strip(),role=body.role,workspace_id=user.workspace_id,password_hash=hasher.hash(body.password),must_change_password=True)
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
    if body.active:item.registration_pending=False
    if revoke:db.execute(delete(m.AuthSession).where(m.AuthSession.user_id==id))
    if not body.active:db.execute(update(m.AccountToken).where(m.AccountToken.user_id==id,m.AccountToken.used_at.is_(None)).values(used_at=m.now()))
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
    return {**configuration(db),**public_configuration(),'key_configured':key_configured()}

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
    return {'database':True,'redis':redis_ok,'worker':alive,'provider':'demo' if settings.demo_mode else 'configured-unverified' if key_configured() else 'missing-key',
            'queued_jobs':len(jobs),'tool_calls':len(tools),'average_tool_ms':round(sum(t.duration_ms for t in tools)/len(tools)) if tools else 0,
            'failed_workflows':sum(w.status=='failed' for w in workflows),'audit_integrity':verify(db)}

from .enterprise import router as enterprise_router
app.include_router(enterprise_router)
