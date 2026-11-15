"""Explicit owner-requested generated operational dataset; never auto-seeded."""
import argparse,calendar,hashlib,json
from datetime import datetime,timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select,func,text
from . import models as m
from .db import Session
from .audit import audit
from .business_data_pack import CATALOG
from .remove_sample_data import protected
from .provider import embed,model_id,embedding_provider
from .retrieval import word_text
from .seed_product_media import illustration

KEY='nova-commerce-operational-v2'
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
ASSETS=Path(__file__).parent/'assets'
RATES={'Điện tử':72,'Gia dụng':66,'Nội thất':63,'Thiết bị văn phòng':73,'Thiết bị mạng':70,'Văn phòng phẩm':59,'Thiết bị hội nghị':69,'Thiết bị lưu trữ':75}

def populate(db,as_of=None):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730031)'))
    existing=db.get(m.SystemSetting,KEY)
    if existing:return {**existing.value,'already_imported':True}
    if any(db.scalar(select(func.count()).select_from(table)) for table in (m.Product,m.Sale,m.Expense,m.FinancePeriod)):
        raise ValueError('Chỉ nạp bộ dữ liệu mới vào các bảng nghiệp vụ trống; không ghi đè dữ liệu hiện có.')
    if embedding_provider()!='lexical':raise ValueError('Cần lập chỉ mục nội bộ; không tự gửi tài liệu mới tới dịch vụ embedding bên ngoài.')
    admin=db.scalar(select(m.User).where(m.User.role=='Admin',m.User.active.is_(True)).order_by(m.User.created_at))
    if not admin or admin.workspace_id!='primary':raise ValueError('Cần Admin hoạt động của workspace primary.')
    before=protected(db)
    as_of=(as_of or m.now()).astimezone(TZ)
    if as_of.year!=2026:raise ValueError('Bộ dữ liệu này chỉ định nghĩa năm 2026.')
    counts={'products':0,'sales':0,'orders':0,'expenses':0,'documents':0,'movements':0,'images':0}
    product_ids=[];sale_ids=[];expense_ids=[];document_ids=[];orders=set();periods={}
    catalog=[('NC-EL-001','Tai nghe không dây Nova','Điện tử',890000),('NC-EL-002','Bàn phím cơ NovaType','Điện tử',1290000),('NC-EL-003','Chuột không dây NovaClick','Điện tử',349000),('NC-EL-004','Loa Bluetooth NovaSound','Điện tử',690000)]
    for code,category,items in CATALOG:
        for i,(name,price) in enumerate(items[:3],1):catalog.append((f'NC-{code}-{i+10:03}',name,category,price))
    for idx,(sku,name,category,price) in enumerate(catalog):
        cost=price*RATES[category]//100//1000*1000
        p=m.Product(sku=sku,name=name,category=category,price=price,description=f'{name}. Đơn vị tính: chiếc; nhóm {category}. Giá niêm yết bằng VND, giá giao dịch và tồn kho được theo dõi riêng trong hệ thống.')
        db.add(p);db.flush();product_ids.append(p.id);counts['products']+=1
        img=illustration(name,sku);db.add(m.ProductImage(product_id=p.id,content=img,mime_type='image/svg+xml',sha256=hashlib.sha256(img).hexdigest(),source='illustration'));counts['images']+=1
        current=0
        def movement(when,after,ref,reason):
            nonlocal current
            db.add(m.InventoryMovement(product_id=p.id,user_id=admin.id,reference=ref,before=current,after=after,reason=reason,created_at=when));current=after;counts['movements']+=1
        for month in range(1,as_of.month+1):
            events=[]
            for day in (3,7,12,17,22,27):
                when=datetime(2026,month,day,10+idx%5,15,tzinfo=TZ)
                if when>as_of:continue
                qty=2+(idx*7+month*3+day)%8
                if category=='Văn phòng phẩm':qty*=5
                # Month-on-month demand changes without changing historical prices.
                if month in (8,9) and idx%3==0:qty=max(1,qty-2)
                events.append((when,qty))
            target=0 if idx==0 else (5 if idx%7==0 else 25+(idx*11+month)%65)
            required=sum(q for _,q in events)+target
            receipt=max(0,required-current)
            if receipt:movement(datetime(2026,month,1,8,tzinfo=TZ),current+receipt,f'NC2-IN-{month:02}-{sku}','Nhập hàng đầu kỳ theo kế hoạch cung ứng')
            for when,qty in events:
                order=f'NC-SO-{when:%Y%m%d}-{category[:2].upper()}-{idx//2:02}'
                discount=2 if (idx+month)%4==0 else 0
                amount=price*qty*(100-discount)//100
                sale=m.Sale(product_id=p.id,date=when,quantity=qty,revenue=amount,reference=f'NC2-S-{when:%Y%m%d}-{sku}',unit_cost=cost,order_number=order)
                db.add(sale);db.flush();sale_ids.append(sale.id);orders.add(order);counts['sales']+=1
                entry=periods.setdefault(when.strftime('%Y-%m'),{'revenue':0,'cost':0,'lines':0})
                entry['revenue']+=amount;entry['cost']+=qty*cost;entry['lines']+=1
                movement(when,current-qty,'NC2-OUT-'+sale.reference,'Xuất hàng theo đơn '+order)
            if current<0:raise ValueError('Tồn kho âm; hủy toàn bộ lần nạp.')
        db.add(m.Inventory(product_id=p.id,quantity=current,threshold=15 if category!='Văn phòng phẩm' else 50))
    for month,totals in sorted(periods.items()):
        number=int(month[-2:]);complete=number<as_of.month
        portion=calendar.monthrange(2026,number)[1] if complete else max(1,as_of.day-1)
        days=calendar.monthrange(2026,number)[1]
        entries=[('RENT','Thuê kho và văn phòng',18000000*portion//days),('PAY','Lương và phụ cấp',65000000*portion//days),('SHIP','Vận chuyển',totals['revenue']*2//100),('MKT','Tiếp thị',totals['revenue']*3//100),('IT','Phần mềm và hạ tầng',3500000*portion//days),('DEP','Khấu hao thiết bị',4500000*portion//days)]
        totals['expenses']=0
        for code,category,amount in entries:
            amount=amount//1000*1000
            e=m.Expense(reference=f'NC2-EXP-{month}-{code}',date=datetime(2026,number,1,9,tzinfo=TZ),category=category,amount=amount,note='Chi phí phân bổ kỳ '+month+('' if complete else '; kỳ đang mở, chưa chốt đủ chi phí'))
            db.add(e);db.flush();expense_ids.append(e.id);counts['expenses']+=1;totals['expenses']+=amount
        db.add(m.FinancePeriod(month=month,expenses_confirmed=complete))
        totals['operating_profit']=totals['revenue']-totals['cost']-totals['expenses'];totals['complete']=complete
    docs=json.loads((ASSETS/'company-library-v2.json').read_text(encoding='utf-8'))
    existing_documents=list(db.scalars(select(m.Document).where(m.Document.workspace_id==admin.workspace_id)))
    has_leave_policy=any('nghỉ phép' in d.content.lower() or 'nghi phep' in d.name.lower() for d in existing_documents)
    for item in docs:
        if item['code']=='NC-HR-101' and has_leave_policy:continue
        if any(item['code'] in d.name for d in existing_documents):continue
        raw=(ASSETS/'company-library-v2'/(item['code']+'.docx')).read_bytes()
        content=word_text(BytesIO(raw))
        doc=m.Document(user_id=admin.id,workspace_id=admin.workspace_id,name=f"[{item['code']}] {item['title']}.docx",scope=item['scope'],status='indexed',content=content)
        db.add(doc);db.flush();document_ids.append(doc.id)
        db.add(m.DocumentFile(document_id=doc.id,content=raw))
        position=0
        for offset in range(0,len(content),850):
            chunk=content[offset:offset+1000].strip()
            if chunk:db.add(m.DocumentChunk(document_id=doc.id,content=chunk,position=position,embedding=embed(chunk),model=model_id()));position+=1
        doc.chunks=position;counts['documents']+=1
    counts['orders']=len(orders)
    result={'origin':'generated','owner_requested':True,'real_transactions':False,'as_of':as_of.isoformat(),'counts':counts,'periods':periods,'product_ids':product_ids,'sale_ids':sale_ids,'expense_ids':expense_ids,'document_ids':document_ids,'policy_status':'owner_review_required','rules':['No legal registration or tax identifiers invented.','No accounts, credentials, quotas, Agent settings or demo flags changed.','Current inventory is reconciled with movements.','Open-month expenses are not confirmed.']}
    db.flush()
    if before!=protected(db):raise ValueError('Cấu hình hoặc tài khoản thay đổi ngoài phạm vi; hủy transaction.')
    db.add(m.SystemSetting(key=KEY,value=result))
    audit(db,admin,'dataset.operational_created',KEY,{'origin':'generated','counts':counts,'as_of':result['as_of']})
    db.commit();return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:raise SystemExit('Cần --apply để nạp bộ dữ liệu được chủ workspace yêu cầu; không tự chạy khi khởi động.')
    with Session() as db:
        result=populate(db)
        print(json.dumps({k:v for k,v in result.items() if not k.endswith('_ids')},ensure_ascii=False))
