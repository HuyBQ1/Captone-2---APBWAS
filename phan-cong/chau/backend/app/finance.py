"""Operational monthly profit, with explicit missing-cost and expense completeness."""
import hashlib,json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Query
from fastapi.responses import Response
from sqlalchemy import select,func,text
from pydantic import Field
from . import models as m
from .db import get_db
from .auth import current_user
from .permissions import require
from .schemas import StrictModel
from .audit import audit
from .tools import period

router=APIRouter(prefix='/api/finance')
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
MONTH=Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')

def dates(month):
    try:return period(month)[1:3]
    except (ValueError,OverflowError):raise HTTPException(422,'Tháng không hợp lệ.')

def lock(db):
    # Match audit lock ordering; all finance writers serialize before reading baselines.
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730019)'))

def state(db,month):
    row=db.get(m.FinancePeriod,month)
    if not row:row=m.FinancePeriod(month=month,expenses_confirmed=False,version=1);db.add(row);db.flush()
    return row

def dataset(db,month):
    start,end=dates(month);end=min(end,m.now().astimezone(TZ))
    sales=[{'id':s.id,'date':s.date.astimezone(TZ).isoformat(),'sku':p.sku,'name':p.name,'order_number':s.order_number,
            'quantity':s.quantity,'revenue':int(s.revenue),'unit_cost':int(s.unit_cost) if s.unit_cost is not None else None}
           for s,p in db.execute(select(m.Sale,m.Product).join(m.Product,m.Sale.product_id==m.Product.id).where(m.Sale.date>=start,m.Sale.date<end).order_by(m.Sale.date,m.Sale.id))]
    expenses=[{'reference':e.reference,'date':e.date.astimezone(TZ).isoformat(),'category':e.category,'amount':int(e.amount),'note':e.note}
              for e in db.scalars(select(m.Expense).where(m.Expense.date>=start,m.Expense.date<end).order_by(m.Expense.date,m.Expense.reference))]
    stock=[{'sku':p.sku,'name':p.name,'category':p.category,'quantity':i.quantity,'threshold':i.threshold,'price':int(p.price)}
           for p,i in db.execute(select(m.Product,m.Inventory).join(m.Inventory,m.Product.id==m.Inventory.product_id).order_by(m.Product.sku))]
    record=db.get(m.FinancePeriod,month)
    sample=db.get(m.SystemSetting,'nova-finance-sample-v1')
    synthetic=bool(sample and month in sample.value.get('months',[]))
    from .shop_connection import setting
    shop=setting(db)
    source={'source':'Nova Commerce API','synced_at':shop.value.get('last_sync'),'created_order_count':shop.value.get('periods',{}).get(month,{}).get('orders_created')} if shop and shop.value.get('last_sync') else {}
    return {**source,'month':month,'as_of':m.now().isoformat(),'sales':sales,'expenses':expenses,'inventory':stock,
            'expenses_confirmed':bool(record and record.expenses_confirmed),'period_version':record.version if record else 0,'synthetic_finance':synthetic}

def summarize(data):
    sales=data['sales'];missing=sum(s['unit_cost'] is None for s in sales)
    revenue=sum(s['revenue'] for s in sales);known_cost=sum(s['quantity']*s['unit_cost'] for s in sales if s['unit_cost'] is not None)
    gross=None if missing else revenue-known_cost
    expenses=sum(e['amount'] for e in data['expenses'])
    profit=gross-expenses if gross is not None and data['expenses_confirmed'] else None
    unknown_orders=sum(not s['order_number'] for s in sales)
    return {**{k:data[k] for k in ('source','synced_at','created_order_count') if k in data},'month':data['month'],'as_of':data['as_of'],'synthetic_finance':data.get('synthetic_finance',False),'revenue':revenue,'sale_lines':len(sales),'units_sold':sum(s['quantity'] for s in sales),
            'known_orders':len({s['order_number'] for s in sales if s['order_number']}),'unassigned_order_lines':unknown_orders,
            'order_count':None if unknown_orders else len({s['order_number'] for s in sales}),
            'missing_cost_lines':missing,'known_cost':known_cost,'cost_of_goods':None if missing else known_cost,
            'gross_profit':gross,'expenses':expenses,'expenses_confirmed':data['expenses_confirmed'],'period_version':data['period_version'],
            'operating_profit':profit,'margin':profit/revenue if profit is not None and revenue else None,
            'average_order_value':revenue/len({s['order_number'] for s in sales}) if sales and not unknown_orders else None,
            'average_unit_revenue':revenue/sum(s['quantity'] for s in sales) if sum(s['quantity'] for s in sales) else None,
            'gross_margin_percent':gross/revenue*100 if gross is not None and revenue else None,
            'operating_margin_percent':profit/revenue*100 if profit is not None and revenue else None,
            'expense_ratio_percent':expenses/revenue*100 if revenue and data['expenses_confirmed'] else None,
            'stock_units':sum(i['quantity'] for i in data['inventory']),'out_of_stock':sum(i['quantity']==0 for i in data['inventory']),
            'low_stock':sum(i['quantity']<=i['threshold'] for i in data['inventory']),
            'basis':'Lợi nhuận vận hành = doanh thu ghi nhận − giá vốn từng dòng bán − chi phí đã nhập. Không phải lợi nhuận sau thuế. Tồn kho là số hiện tại, không phải số cuối tháng.'}

def finance_summary(db,month=None):
    month=month or datetime.now(TZ).strftime('%Y-%m');result=summarize(dataset(db,month))
    amount=lambda v:f'{v:,}'.replace(',','.')+' ₫'
    lines=[f'### Kết quả kinh doanh tháng {month}']
    if result.get('source')=='Nova Commerce API':lines.append(f"Nguồn: website Nova Commerce, đồng bộ lúc {result['synced_at']}. Số đơn tạo trong tháng: {result['created_order_count']}. Số đơn bên dưới là đơn có phát sinh giao/hoàn trong kỳ; doanh thu đã trừ hoàn hàng.")
    if result['synthetic_finance']:lines.append('Dữ liệu tài chính **mô phỏng Nova Commerce**, dùng để kiểm thử.')
    lines.extend([f"- Doanh thu: **{amount(result['revenue'])}**.",
                  f"- Đơn hàng: **{result['order_count']} đơn**." if result['order_count'] is not None else f"- Chưa xác định tổng số đơn: {result['unassigned_order_lines']} dòng chưa có mã đơn.",
                  f"- Đã bán: **{result['units_sold']} đơn vị**, thuộc {result['sale_lines']} dòng hàng."])
    if result['operating_profit'] is None:
        lines.append(f"Chưa đủ dữ liệu kết luận lời/lỗ: {result['missing_cost_lines']} dòng thiếu giá vốn; chi phí {'đã' if result['expenses_confirmed'] else 'chưa'} xác nhận đầy đủ.")
    else:
        lines.extend([f"- Giá vốn: **{amount(result['cost_of_goods'])}**.",f"- Lợi nhuận gộp: **{amount(result['gross_profit'])}**.",
                      f"- Chi phí vận hành: **{amount(result['expenses'])}**.",
                      f"**{'Lãi' if result['operating_profit']>0 else 'Lỗ' if result['operating_profit']<0 else 'Hòa vốn'} vận hành: {amount(abs(result['operating_profit']))}**.",
                      f"Phép tính: {amount(result['revenue'])} − {amount(result['cost_of_goods'])} − {amount(result['expenses'])} = **{amount(result['operating_profit'])}**."])
        if result['margin'] is not None:lines.append(f"Biên lợi nhuận vận hành: **{result['margin']*100:.2f}%**.")
    lines.append(f"Tồn kho **hiện tại**: {result['stock_units']} đơn vị; {result['low_stock']} SKU tồn thấp, gồm {result['out_of_stock']} SKU hết hàng. Đây không phải tồn kho cuối tháng {month}.")
    lines.append('Lợi nhuận vận hành chưa phải lợi nhuận sau thuế.')
    result['summary']='\n\n'.join(lines)
    return result

@router.get('/summary')
def summary(month:str=MONTH,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read');require(db,user,'inventory.read')
    return finance_summary(db,month)

class ExpenseInput(StrictModel):
    reference:str=Field(min_length=3,max_length=100)
    date:datetime
    category:str=Field(min_length=2,max_length=100)
    amount:int=Field(ge=0,le=99999999999999)
    note:str=Field(default='',max_length=500)

@router.post('/expenses')
def expense(body:ExpenseInput,user=Depends(current_user),db=Depends(get_db)):
    from .shop_connection import block_local_write
    block_local_write(db)
    require(db,user,'business.manage');require(db,user,'sales.read');lock(db)
    if body.date.tzinfo is None:raise HTTPException(422,'Ngày chi phí cần múi giờ.')
    if body.date>m.now():raise HTTPException(422,'Không ghi nhận chi phí thực tế ở tương lai.')
    month=body.date.astimezone(TZ).strftime('%Y-%m')
    existing=db.scalar(select(m.Expense).where(m.Expense.reference==body.reference))
    if existing:
        if any(getattr(existing,k)!=v for k,v in body.model_dump().items()):raise HTTPException(409,'Mã chi phí đã dùng cho nội dung khác.')
        return {'id':existing.id,'existing':True}
    row=m.Expense(**body.model_dump());db.add(row)
    p=state(db,month);p.expenses_confirmed=False;p.version+=1
    audit(db,user,'finance.expense_added',body.reference,{'month':month,'amount':body.amount});db.commit()
    return {'id':row.id}

class ConfirmInput(StrictModel):
    version:int=Field(ge=0)
    confirmed:bool

@router.put('/period/{month}')
def confirm(month:str,body:ConfirmInput,user=Depends(current_user),db=Depends(get_db)):
    from .shop_connection import block_local_write
    block_local_write(db)
    require(db,user,'business.manage');require(db,user,'sales.read');dates(month);lock(db)
    old=db.get(m.FinancePeriod,month)
    if (old.version if old else 0)!=body.version:raise HTTPException(409,'Kỳ đã thay đổi, hãy tải lại.')
    row=state(db,month);row.expenses_confirmed=body.confirmed;row.version+=1
    audit(db,user,'finance.expenses_confirmed',month,{'confirmed':body.confirmed});db.commit()
    return {'ok':True}

@router.get('/export')
def export(month:str=MONTH,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'sales.read');require(db,user,'inventory.read')
    from .finance_excel import export_workbook
    data=dataset(db,month)
    raw=export_workbook(data)
    audit(db,user,'finance.excel_exported',month);db.commit()
    return Response(raw,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':f'attachment; filename="NovaCommerce-{month}.xlsx"','Cache-Control':'no-store'})

@router.post('/imports/preview')
async def preview(month:str=MONTH,file:UploadFile=File(...),user=Depends(current_user),db=Depends(get_db)):
    from .shop_connection import block_local_write
    block_local_write(db)
    require(db,user,'business.manage');require(db,user,'sales.read');require(db,user,'inventory.read');dates(month)
    raw=await file.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise HTTPException(413,'File Excel tối đa 8 MB.')
    from .finance_excel import parse_inputs
    data=dataset(db,month);changes=parse_inputs(raw,data)
    row=m.FinanceImport(user_id=user.id,month=month,preview=changes,content=raw,sha256=hashlib.sha256(raw).hexdigest())
    db.add(row);db.flush();audit(db,user,'finance.import_previewed',row.id,{'month':month});db.commit()
    return {'id':row.id,'cost_lines':len(changes['sales']),'expense_rows':len(changes['expenses']),'expenses_confirmed':changes['confirmed'],
            'message':'Chỉ cập nhật giá vốn, mã đơn và chi phí. Không nhập/xóa giao dịch bán hoặc thay đổi tồn kho.'}

@router.post('/imports/{id}/commit')
def commit(id:str,user=Depends(current_user),db=Depends(get_db)):
    from .shop_connection import block_local_write
    block_local_write(db)
    require(db,user,'business.manage');require(db,user,'sales.read');require(db,user,'inventory.read');lock(db)
    row=db.scalar(select(m.FinanceImport).where(m.FinanceImport.id==id).with_for_update())
    if not row or row.user_id!=user.id:raise HTTPException(404,'Không tìm thấy bản xem trước.')
    if row.status=='committed':return {'ok':True,'existing':True}
    if (m.now()-row.created_at).total_seconds()>86400:raise HTTPException(409,'Bản xem trước đã hết hạn sau 24 giờ.')
    changes=row.preview
    current=dataset(db,row.month)
    from .finance_excel import baseline
    if baseline(current)!=changes['baseline']:raise HTTPException(409,'Số liệu đã thay đổi sau khi xem trước. Xuất file mới và xem trước lại.')
    # Lock sale rows as well so concurrent postings/imports cannot overwrite cost inputs.
    for item in changes['sales']:
        sale=db.scalar(select(m.Sale).where(m.Sale.id==item['id']).with_for_update())
        sale.unit_cost=item['unit_cost'];sale.order_number=item['order_number']
    for item in changes['expenses']:
        expense=db.scalar(select(m.Expense).where(m.Expense.reference==item['reference']))
        if expense and expense.date.astimezone(TZ).strftime('%Y-%m')!=row.month:raise HTTPException(409,'Mã chi phí thuộc kỳ khác.')
        if not expense:expense=m.Expense(reference=item['reference']);db.add(expense)
        for key,value in item.items():setattr(expense,key,datetime.fromisoformat(value) if key=='date' else value)
    p=state(db,row.month);p.expenses_confirmed=changes['confirmed'];p.version+=1
    row.status='committed';audit(db,user,'finance.import_committed',id,{'month':row.month,'cost_lines':len(changes['sales']),'expenses':len(changes['expenses'])});db.commit()
    return {'ok':True}
