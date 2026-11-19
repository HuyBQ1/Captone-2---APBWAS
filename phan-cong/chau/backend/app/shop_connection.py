"""Read-only Nova API mirror. No customer PII, remote writes or LLM calls."""
import copy,json,os,re,uuid
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,SecretStr
from sqlalchemy import select,delete,func,text
from . import models as m
from .db import get_db
from .auth import current_user
from .permissions import require,permissions
from .schemas import StrictModel
from .llm_models import protect,reveal
from .audit import audit

router=APIRouter(prefix='/api/connections/shop')
KEY='nova-shop-connection-v1'
BASE='https://nova-commerce-neon.vercel.app'
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
PREFIX='nova-api:'

def setting(db):return db.get(m.SystemSetting,KEY,populate_existing=True)
def enabled(db):
    row=setting(db)
    return bool(row and row.value.get('enabled') and row.value.get('api_key_ciphertext'))
def stamp(value):
    v=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if v.tzinfo is None:raise ValueError('Thời gian API thiếu múi giờ.')
    return v.astimezone(timezone.utc)
def integer(value,minimum=None):
    if isinstance(value,bool) or not isinstance(value,int) or (minimum is not None and value<minimum):raise ValueError('Số liệu API không hợp lệ.')
    return value
def identity(kind,value):return str(uuid.uuid5(uuid.NAMESPACE_URL,BASE+'/'+kind+'/'+str(value)))
def public(db):
    row=setting(db);v=row.value if row else {}
    return {k:v[k] for k in ('enabled','last_sync','last_attempt','last_error','counts','periods','revision','backup','source_as_of') if k in v} | {'configured':bool(v.get('api_key_ciphertext')),'base_url':BASE,'interval_seconds':300,'source':'Nova Commerce API','read_only':True}

class NovaClient:
    def __init__(self,key):self.client=httpx.Client(base_url=BASE,headers={'Authorization':'Bearer '+key},timeout=httpx.Timeout(15,connect=8),follow_redirects=False,trust_env=False)
    def __enter__(self):return self
    def __exit__(self,*args):self.client.close()
    def get(self,path,**params):
        try:
            with self.client.stream('GET',path,params=params) as r:
                if r.status_code!=200:
                    msg={401:'API key Nova không hợp lệ hoặc đã bị thu hồi.',403:'API key thiếu quyền đọc dữ liệu.',429:'Nova đang giới hạn lượt gọi; dữ liệu cũ chưa bị thay đổi.'}.get(r.status_code,'Website Nova chưa phản hồi hợp lệ.')
                    raise ValueError(msg)
                raw=bytearray()
                for part in r.iter_bytes():
                    raw.extend(part)
                    if len(raw)>8_000_000:raise ValueError('Phản hồi API vượt giới hạn dung lượng.')
                return json.loads(raw)
        except (httpx.HTTPError,json.JSONDecodeError):raise ValueError('Không kết nối được API Nova; dữ liệu đã đồng bộ vẫn được giữ.') from None
    def pages(self,path):
        result=[];ids=set();total=None
        for page in range(1,102):
            data=self.get('/api/v1/integration/'+path,page=page,page_size=100)
            count=integer(data['total'],0)
            if total is None:total=count
            if count!=total or total>10000:raise ValueError('Danh sách nguồn thay đổi hoặc quá lớn; hãy đồng bộ lại.')
            items=data['items']
            if not isinstance(items,list) or len(items)>100:raise ValueError('Phân trang API không hợp lệ.')
            for item in items:
                if item['id'] in ids:raise ValueError('API trả bản ghi trùng; chưa thay dữ liệu.')
                ids.add(item['id']);result.append(item)
            if len(result)==total:return result
            if not items or len(result)>total:raise ValueError('API trả thiếu trang dữ liệu.')
        raise ValueError('Vượt giới hạn số trang đồng bộ.')

def fetch_snapshot(key):
    with NovaClient(key) as api:
        company=api.get('/api/v1/integration/company')
        if company.get('currency')!='VND' or company.get('timezone')!='Asia/Ho_Chi_Minh':raise ValueError('Tiền tệ hoặc múi giờ nguồn chưa được hỗ trợ.')
        products=api.pages('products');inventory=api.pages('inventory');orders=api.pages('orders');movements=api.pages('inventory/movements')
        categories={r['id']:r['name'] for r in api.get('/api/v1/categories')}
        stocks={r['id']:r for r in inventory}
        if set(stocks)!={p['id'] for p in products}:raise ValueError('Sản phẩm và tồn kho chưa đồng nhất; thử đồng bộ lại.')
        skus=set();product_ids={p['id'] for p in products}
        for p in products:
            if not isinstance(p['sku'],str) or not 1<=len(p['sku'])<=30 or p['sku'] in skus:raise ValueError('SKU trùng hoặc vượt giới hạn APBWAS.')
            skus.add(p['sku']);integer(p['price'],0);integer(stocks[p['id']]['stock'],0)
            if p.get('stock') is not None and p['stock']!=stocks[p['id']]['stock']:raise ValueError('Tồn kho thay đổi trong lúc lấy dữ liệu; thử đồng bộ lại.')
            if len(p['name'])>120 or len(str(categories.get(p['category_id'],'Hàng hóa')))>80:raise ValueError('Tên hàng hoặc danh mục vượt giới hạn APBWAS.')
        months={m.now().astimezone(TZ).strftime('%Y-%m')};sales=[]
        created_months={}
        for o in orders:
            created=stamp(o['created_at']).astimezone(TZ).strftime('%Y-%m');months.add(created)
            created_months[created]=created_months.get(created,0)+1
            for sign,field in ((1,'recognized_at'),(-1,'returned_at')):
                if not o.get(field):continue
                date=stamp(o[field]);months.add(date.astimezone(TZ).strftime('%Y-%m'))
                for pos,l in enumerate(o['lines']):
                    if l['product_id'] not in product_ids:raise ValueError('Dòng đơn hàng tham chiếu sản phẩm không tồn tại.')
                    qty=integer(l['quantity'],1);price=integer(l['price'],0);discount=integer(l['discount'],0)
                    if discount>price:raise ValueError('Giảm giá vượt giá bán.')
                    if 'cost' not in l:raise ValueError('API key cần finance:read để đọc giá vốn.')
                    cost=l['cost']
                    if cost is not None:integer(cost,0)
                    sales.append({'id':identity('sale',f'{o["id"]}:{field}:{pos}'),'reference':PREFIX+f'{o["id"]}:{field}:{pos}','product_id':identity('product',l['product_id']),'date':date,'quantity':sign*qty,'revenue':sign*(price-discount)*qty,'unit_cost':cost,'order_number':'NOVA-'+str(o['id'])})
        # Include expense-only months between the first source order and now.
        first=min(months);cursor=datetime.strptime(first,'%Y-%m').replace(tzinfo=TZ)
        last=max(months)
        while cursor.strftime('%Y-%m')<=last:
            months.add(cursor.strftime('%Y-%m'));cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
            if len(months)>36:raise ValueError('Nguồn vượt 36 tháng; cần chia kỳ đồng bộ.')
        reports={}
        for month in sorted(months):
            r=api.get('/api/v1/integration/finance/summary',month=month)
            if r.get('currency')!='VND' or stamp(r['period']['start']).astimezone(TZ).strftime('%Y-%m')!=month:raise ValueError('Kỳ báo cáo API không khớp.')
            lines=[s for s in sales if s['date'].astimezone(TZ).strftime('%Y-%m')==month]
            total=sum(s['revenue'] for s in lines)
            cost=None if any(s['unit_cost'] is None for s in lines) else sum(s['quantity']*s['unit_cost'] for s in lines)
            expense=integer(r['recorded_expenses'],0)
            if total!=r['net_revenue'] or cost!=r['cogs'] or created_months.get(month,0)!=r['orders_count']:raise ValueError('Dữ liệu nguồn thay đổi hoặc chưa đối chiếu được doanh thu/giá vốn/số đơn; chưa thay dữ liệu.')
            if r['gross_profit']!=(None if cost is None else total-cost):raise ValueError('Lợi nhuận gộp API không khớp.')
            complete=r['completeness']['expenses_complete']
            if not isinstance(complete,bool):raise ValueError('Trạng thái chi phí không hợp lệ.')
            profit=None if cost is None or not complete else total-cost-expense
            if r['operating_result']!=profit:raise ValueError('Kết quả vận hành API không khớp.')
            reports[month]=r
        safe_orders=[{'id':o['id'],'order_number':'NOVA-'+str(o['id']),'date':stamp(o['created_at']).isoformat(),'status':o['status'],'payment_status':o.get('payment_status'),'total':integer(o['total'],0),'units':sum(integer(l['quantity'],1) for l in o['lines'])} for o in orders]
        balances={id:integer(s['stock'],0) for id,s in stocks.items()};ledger=[]
        for event in sorted(movements,key=lambda e:e['id'],reverse=True):
            pid=event['product_id']
            if pid not in balances:raise ValueError('Biến động kho tham chiếu sản phẩm không tồn tại.')
            after=balances[pid];before=after-integer(event['delta'])
            if before<0:raise ValueError('Sổ kho chưa khớp với tồn hiện tại; thử đồng bộ lại.')
            balances[pid]=before
            ledger.append({'id':identity('movement',event['id']),'product_id':identity('product',pid),'reference':PREFIX+'movement:'+str(event['id']),'before':before,'after':after,'reason':str(event['reason'])[:250],'created_at':stamp(event['updated_at'])})
        return {'company':company,'products':products,'stocks':stocks,'categories':categories,'sales':sales,'movements':ledger,'reports':reports,'order_count':len(orders),'orders':safe_orders,'orders_created_by_month':created_months}

def backup_business(db):
    from .config import settings
    path=Path(settings.upload_dir)/'backups'/('before-nova-api-'+uuid.uuid4().hex+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    tables=(m.Product,m.Inventory,m.Sale,m.Expense,m.FinancePeriod,m.InventoryMovement)
    data={t.__tablename__:[{c.name:getattr(r,c.name) for c in t.__table__.columns} for r in db.scalars(select(t))] for t in tables}
    with path.open('x',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,default=lambda v:v.isoformat() if isinstance(v,datetime) else str(v))
        f.flush();os.fsync(f.fileno())
    return str(path)

def retire_generated_knowledge(db,actor):
    manifest=db.get(m.SystemSetting,'nova-commerce-operational-v2')
    ids=set(manifest.value.get('document_ids',[])) if manifest else set()
    if not ids:return
    admin=db.scalar(select(m.User).where(m.User.role=='Admin',m.User.active.is_(True)).limit(1))
    if not admin:raise ValueError('Cần Admin hoạt động trước khi thay nguồn.')
    for a in db.scalars(select(m.Agent)):
        draft=db.get(m.AgentConfig,a.id)
        published=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==a.id,m.AgentVersion.number==a.published_version)) if a.published_version else None
        if draft and ids.intersection(draft.config.get('knowledge_ids',[])):
            cfg=copy.deepcopy(draft.config);cfg['knowledge_ids']=[id for id in cfg['knowledge_ids'] if id not in ids];draft.config=cfg;draft.revision+=1
            snap={'name':a.name,'description':a.description,'avatar':a.avatar,'visibility':a.visibility,**cfg}
            db.add(m.AgentDraftRevision(agent_id=a.id,revision=draft.revision,snapshot=snap,created_by=admin.id))
        if published and ids.intersection(published.snapshot.get('knowledge_ids',[])):
            snap=copy.deepcopy(published.snapshot);snap['knowledge_ids']=[id for id in snap['knowledge_ids'] if id not in ids]
            number=(db.scalar(select(func.max(m.AgentVersion.number)).where(m.AgentVersion.agent_id==a.id)) or 0)+1
            db.add(m.AgentVersion(agent_id=a.id,number=number,draft_revision=published.draft_revision,snapshot=snap,created_by=admin.id));a.published_version=number
    db.execute(delete(m.AgentKnowledge).where(m.AgentKnowledge.document_id.in_(ids)))
    for t in (m.DocumentChunk,m.DocumentFile):db.execute(delete(t).where(t.document_id.in_(ids)))
    db.execute(delete(m.Job).where(m.Job.kind=='document',m.Job.resource.in_(ids)))
    for d in db.scalars(select(m.Document).where(m.Document.id.in_(ids))):d.status='archived';d.content='';d.chunks=0;d.path=None
    audit(db,actor,'shop.old_generated_knowledge_removed',KEY,{'documents':len(ids)})

def sync(db,actor='worker',replace=False):
    if db.bind.dialect.name=='postgresql' and not db.scalar(text('SELECT pg_try_advisory_xact_lock(730042)')):raise ValueError('Một lượt đồng bộ đang chạy.')
    row=setting(db)
    if not row or not row.value.get('enabled'):raise ValueError('Chưa bật kết nối Nova Commerce.')
    value=dict(row.value);snapshot=fetch_snapshot(reveal(value['api_key_ciphertext']))
    foreign=db.scalar(select(func.count()).select_from(m.Product).where(~m.Product.id.in_([identity('product',p['id']) for p in snapshot['products']])))
    first=not value.get('last_sync')
    if first and (foreign or db.scalar(select(func.count()).select_from(m.Sale)) or db.scalar(select(func.count()).select_from(m.Expense))) and not replace:raise ValueError('Cần xác nhận thay dữ liệu cũ sau khi sao lưu.')
    if first:
        active=db.scalar(select(func.count()).select_from(m.Workflow).where(m.Workflow.status.in_(['queued','planning','running','waiting_approval'])))
        mail=db.scalar(select(func.count()).select_from(m.MailCampaign).where(m.MailCampaign.status.in_(['queued','sending'])))
        if active or mail:raise ValueError('Cần kết thúc workflow và lượt gửi email trước khi thay nguồn dữ liệu.')
        value['backup']=backup_business(db)
    # Serialize against local writers after remote I/O, following audit lock order.
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730019)'))
    if first:
        retire_generated_knowledge(db,actor)
        for table in (m.InventoryMovement,m.Sale,m.ProductImage,m.Inventory,m.Product,m.Expense,m.FinancePeriod):db.execute(delete(table))
        db.execute(delete(m.Report))
        # Prevent generated old reports being offered as the current company's data.
        for f in db.scalars(select(m.GeneratedFile).where(m.GeneratedFile.workspace_id=='primary')):
            if f.source.get('type') in ('finance','inventory','products'):f.source={**f.source,'superseded_source':True}
        for k in ('nova-commerce-operational-v2','nova-finance-sample-v1','nova-commerce-business-v1'):
            old=db.get(m.SystemSetting,k)
            if old:db.delete(old)
        db.flush()
    else:
        db.execute(delete(m.Sale).where(m.Sale.reference.startswith(PREFIX)))
        db.execute(delete(m.Expense).where(m.Expense.reference.startswith(PREFIX)))
        db.execute(delete(m.InventoryMovement).where(m.InventoryMovement.reference.startswith(PREFIX)))
    incoming=set()
    for p in snapshot['products']:
        pid=identity('product',p['id']);incoming.add(pid);rowp=db.get(m.Product,pid)
        if not rowp:rowp=m.Product(id=pid);db.add(rowp)
        rowp.sku=p['sku'];rowp.name=p['name'];rowp.category=snapshot['categories'].get(p['category_id'],'Hàng hóa');rowp.description=p.get('description','');rowp.price=p['price'];rowp.active=bool(p['active']);rowp.version=(rowp.version or 0)+1
        db.flush();stock=db.get(m.Inventory,pid)
        if not stock:stock=m.Inventory(product_id=pid,version=0);db.add(stock)
        stock.quantity=snapshot['stocks'][p['id']]['stock'];stock.threshold=5;stock.version+=1
    for p in db.scalars(select(m.Product)):
        if p.id not in incoming:p.active=False
    for item in snapshot['sales']:db.add(m.Sale(**item))
    admin=db.scalar(select(m.User).where(m.User.role=='Admin',m.User.active.is_(True)).limit(1))
    if snapshot.get('movements') and not admin:raise ValueError('Thiếu Admin để ghi nhận nguồn biến động kho.')
    for item in snapshot.get('movements',[]):db.add(m.InventoryMovement(**item,user_id=admin.id))
    for month,r in snapshot['reports'].items():
        period=db.get(m.FinancePeriod,month)
        if not period:period=m.FinancePeriod(month=month,version=0);db.add(period)
        period.expenses_confirmed=r['completeness']['expenses_complete'];period.version+=1
        if r['recorded_expenses']:
            db.add(m.Expense(id=identity('expense',month),reference=PREFIX+'expense:'+month,date=stamp(r['period']['start']),category='Chi phí từ website',amount=r['recorded_expenses'],note='Tổng hợp theo tháng từ API Nova; không phải chi tiết từng khoản.'))
    company=db.get(m.SystemSetting,'company')
    if company:company.value={**company.value,'name':snapshot['company']['name']}
    order_row=db.get(m.SystemSetting,'nova-shop-orders-v1')
    if not order_row:order_row=m.SystemSetting(key='nova-shop-orders-v1',value={});db.add(order_row)
    order_row.value={'orders':snapshot.get('orders',[]),'synced_at':m.now().isoformat()}
    value.update(last_sync=m.now().isoformat(),last_attempt=m.now().isoformat(),last_error='',counts={'products':len(incoming),'orders':snapshot['order_count'],'sale_events':len(snapshot['sales'])},periods={month:{'revenue':r['net_revenue'],'cost_of_goods':r['cogs'],'expenses':r['recorded_expenses'],'operating_profit':r['operating_result'],'complete':r['completeness']['complete'],'orders_created':r['orders_count']} for month,r in snapshot['reports'].items()},source_as_of=snapshot['company']['as_of'],images={identity('product',p['id']):p.get('image') for p in snapshot['products'] if p.get('image')})
    row.value=value;audit(db,actor,'shop.synchronized',KEY,{'counts':value['counts'],'source':BASE,'replaced':first});db.commit()
    return public(db)

class Connect(StrictModel):
    api_key:SecretStr=Field(min_length=10,max_length=500)
    replace_existing:bool=False

@router.get('')
def status(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'inventory.read')
    if user.workspace_id!='primary':raise HTTPException(403,'Kết nối chỉ thuộc workspace primary.')
    result=public(db)
    allowed=permissions(db,user)
    if 'settings.manage' not in allowed:result.pop('backup',None)
    if 'sales.read' not in allowed:result.pop('periods',None);result['counts']={k:v for k,v in result.get('counts',{}).items() if k=='products'}
    return result

@router.put('')
def connect(body:Connect,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    if user.workspace_id!='primary':raise HTTPException(403,'Kết nối chỉ thuộc workspace primary.')
    row=setting(db)
    if not row:row=m.SystemSetting(key=KEY,value={});db.add(row)
    row.value={**row.value,'enabled':True,'api_key_ciphertext':protect(body.api_key.get_secret_value().strip()),'revision':row.value.get('revision',0)+1}
    db.flush()
    try:return sync(db,user,replace=body.replace_existing)
    except (ValueError,KeyError,TypeError) as exc:
        db.rollback();raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else 'API Nova chưa đúng cấu trúc dữ liệu; không thay dữ liệu cũ.') from None

@router.post('/sync')
def resync(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    if user.workspace_id!='primary':raise HTTPException(403,'Kết nối chỉ thuộc workspace primary.')
    try:return sync(db,user)
    except (ValueError,KeyError,TypeError) as exc:
        db.rollback();raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else 'API Nova chưa đúng cấu trúc dữ liệu.') from None

def sync_if_due(db):
    row=setting(db)
    if not row or not row.value.get('enabled') or not row.value.get('last_sync'):return
    last=row.value.get('last_attempt',row.value['last_sync'])
    if (m.now()-stamp(last)).total_seconds()<300:return
    try:sync(db)
    except Exception:
        db.rollback();row=setting(db)
        if row:row.value={**row.value,'last_attempt':m.now().isoformat(),'last_error':'Đồng bộ chưa thành công. Kiểm tra API key và website; dữ liệu hiện tại là bản đồng bộ trước.'};db.commit()

def block_local_write(db):
    if enabled(db):raise HTTPException(409,'Dữ liệu đang đồng bộ từ Nova Commerce. Hãy cập nhật trên website bán hàng rồi đồng bộ lại.')

def order_summary(db,args,fresh=False):
    row=db.get(m.SystemSetting,'nova-shop-orders-v1')
    if not row:raise ValueError('Chưa kết nối nguồn đơn hàng website.')
    query=(args.get('query') or '').lower().strip();month=args.get('month');today=m.now().astimezone(TZ).date()
    orders=row.value.get('orders',[])
    read_at=row.value['synced_at']
    if fresh:
        config=setting(db)
        if not enabled(db):raise ValueError('Chưa bật kết nối đơn hàng website.')
        with NovaClient(reveal(config.value['api_key_ciphertext'])) as api:
            raw=api.pages('orders')
        orders=[{'id':o['id'],'order_number':'NOVA-'+str(o['id']),'date':stamp(o['created_at']).isoformat(),'status':o['status'],'payment_status':o.get('payment_status'),'total':integer(o['total'],0),'units':sum(integer(l['quantity'],1) for l in o['lines'])} for o in raw]
        read_at=m.now().isoformat()
    day=args.get('date') or (today.isoformat() if query=='today' else None)
    if day:
        requested=datetime.strptime(day,'%Y-%m-%d').date()
        orders=[o for o in orders if stamp(o['date']).astimezone(TZ).date()==requested]
    elif month:orders=[o for o in orders if stamp(o['date']).astimezone(TZ).strftime('%Y-%m')==month]
    status=args.get('order_status') or (query if query in ('unfinished','pending','confirmed','shipping','delivered','cancelled','returned') else None)
    if status=='unfinished':orders=[o for o in orders if o['status'] in ('pending','confirmed','shipping')]
    elif status:orders=[o for o in orders if o['status']==status]
    if query and query not in ('today','unfinished','pending','confirmed','shipping','delivered','cancelled','returned'):
        exact=re.fullmatch(r'#?(?:nova-|nc)0*(\d+)',query)
        if exact:
            orders=[o for o in orders if o['order_number'].lower()==f'nova-{int(exact[1])}']
        else:
            orders=[o for o in orders if query in o['order_number'].lower()]
    counts={status:sum(o['status']==status for o in orders) for status in ('pending','confirmed','shipping','delivered','cancelled','returned')}
    orders.sort(key=lambda o:o['date'],reverse=True)
    return {'month':None if day else month,'date':day,'order_status':status,'as_of':read_at,'synced_at':read_at,'live_source':fresh,'created_order_count':len(orders),'rows':orders[:20],'truncated':len(orders)>20,'order_status_counts':counts,'basis':'Đếm đơn theo ngày tạo tại Asia/Ho_Chi_Minh. pending=chờ xác nhận; confirmed=đã xác nhận. Không có định danh khách hàng để đếm số người riêng biệt. Giá trị đơn không phải doanh thu ghi nhận.','source':'Nova Commerce API trực tiếp' if fresh else 'Nova Commerce API','summary':f"Có {len(orders)} đơn tạo trong phạm vi được hỏi, chưa có dữ liệu đếm số khách hàng riêng biệt. Giá trị đơn chưa phải doanh thu ghi nhận; nguồn website Nova Commerce, đọc lúc {read_at}."}
