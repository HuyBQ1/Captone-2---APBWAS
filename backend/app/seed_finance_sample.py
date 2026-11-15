"""Explicit synthetic finance completion for the existing 2026 sample catalog."""
import json,re
from datetime import datetime
from sqlalchemy import select,func
from . import models as m
from .db import Session
from .config import settings
from .finance import TZ,lock,state
from .audit import audit

PACK='nova-finance-sample-v1'
RATES={'Điện tử':76,'Gia dụng':68,'Nội thất':65,'Thiết bị văn phòng':78,'Thiết bị mạng':74,'Văn phòng phẩm':62,'Thiết bị hội nghị':73,'Thiết bị lưu trữ':81}

def populate(db):
    if db.get(m.SystemSetting,'sample-data-removed-v1'):raise ValueError('Dữ liệu mẫu đã được xóa theo yêu cầu; không tự nạp lại.')
    if not (settings.sample_data or settings.demo_mode):raise ValueError('Chỉ được bổ sung tài chính mô phỏng trong môi trường SAMPLE_DATA/DEMO_MODE.')
    lock(db)
    existing=db.get(m.SystemSetting,PACK)
    if existing:return {**existing.value,'already_imported':True}
    today=m.now().astimezone(TZ)
    rows=db.execute(select(m.Sale,m.Product).join(m.Product,m.Product.id==m.Sale.product_id).order_by(m.Sale.date,m.Sale.id)).all()
    cost_ids=[];order_ids=[];months={};eligible=[]
    for sale,p in rows:
        when=sale.date.astimezone(TZ)
        sample_nc=bool(re.fullmatch(r'NCV1-S-\d{8}-NC-[A-Z]{2}-\d{3}',sale.reference or ''))
        sample_legacy=sale.reference is None and bool(re.fullmatch(r'AP-00[1-8]',p.sku))
        if when.year!=2026 or when.strftime('%Y-%m')>=today.strftime('%Y-%m') or not (sample_nc or sample_legacy):continue
        eligible.append((sale,p,when));months.setdefault(when.strftime('%Y-%m'),[]).append(sale)
    for sale,p,when in eligible:
        if sale.quantity<=0 or sale.revenue<0:raise ValueError('Dòng bán mẫu không hợp lệ; không tự sửa dữ liệu.')
        if sale.unit_cost is None:
            # Explicit scenario assumption, never claimed to be supplier cost.
            sale.unit_cost=max(0,int(sale.revenue)*RATES.get(p.category,75)//(sale.quantity*100*1000)*1000)
            cost_ids.append(sale.id)
        if not sale.order_number:
            if p.sku.startswith('NC-'):
                code=p.sku.split('-')[1];group=(int(p.sku.split('-')[-1])-1)//3+1
                sale.order_number=f'NC-SO-{when:%Y%m%d}-{code}-{group:02}'
            else:sale.order_number=f'AP-SO-{when:%Y%m%d}-{(int(p.sku[-3:])-1)//2+1:02}'
            order_ids.append(sale.id)
    expenses=[];confirmed=[]
    for month,sales in sorted(months.items()):
        start=datetime.fromisoformat(month+'-01T08:00:00').replace(tzinfo=TZ)
        # Preserve any period that already has operator-entered finance data.
        end=datetime(start.year+int(start.month==12),start.month%12+1,1,tzinfo=TZ)
        has_expenses=db.scalar(select(m.Expense.id).where(m.Expense.date>=start.replace(hour=0),m.Expense.date<end).limit(1))
        old_period=db.get(m.FinancePeriod,month)
        total_lines=db.scalar(select(func.count()).select_from(m.Sale).where(m.Sale.date>=start.replace(hour=0),m.Sale.date<end))
        if has_expenses or old_period or total_lines!=len(sales):continue
        revenue=sum(int(s.revenue) for s in sales)
        assumptions=[('RENT','Thuê kho và văn phòng',42000000),('PAYROLL','Lương và phụ cấp',190000000),
                     ('SHIP','Vận chuyển',revenue*3//100//1000*1000),('MKT','Tiếp thị',revenue*4//100//1000*1000),
                     ('IT','Phần mềm và hạ tầng',12000000),('DEPR','Khấu hao mô phỏng',8000000)]
        for code,category,amount in assumptions:
            ref=f'NC-FIN-V1-{month}-{code}'
            if db.scalar(select(m.Expense.id).where(m.Expense.reference==ref)):raise ValueError('Trùng mã chi phí mẫu; cần đối soát trước.')
            expense=m.Expense(reference=ref,date=start,category=category,amount=amount,
                note='DỮ LIỆU MÔ PHỎNG Nova Commerce; giả định phục vụ kiểm thử, không phải chứng từ thực tế.')
            db.add(expense);db.flush();expenses.append(expense.id)
        p=state(db,month);p.expenses_confirmed=True;p.version+=1;confirmed.append(month)
    manifest={'synthetic':True,'dataset':PACK,'months':sorted(months),'confirmed_months':confirmed,
              'cost_sale_ids':cost_ids,'order_sale_ids':order_ids,'expense_ids':expenses,
              'counts':{'costs':len(cost_ids),'order_lines':len(order_ids),'expenses':len(expenses)},
              'assumptions':{'cost_percent_by_category':RATES,'monthly_rent':42000000,'monthly_payroll':190000000,
                             'delivery_percent':3,'marketing_percent':4,'monthly_it':12000000,'monthly_depreciation':8000000},
              'rules':['Only known 2026 sample sales in completed months.','Existing non-null costs/orders and operator-entered expenses/periods preserved.',
                       'Sample order numbers group up to three NC SKUs per day/category, or two AP SKUs per day.','No changes to revenue, quantity or stock.','No external AI calls.']}
    db.add(m.SystemSetting(key=PACK,value=manifest))
    audit(db,'system','finance.sample_completed',PACK,{'synthetic':True,'counts':manifest['counts'],'months':confirmed})
    db.commit();return manifest

if __name__=='__main__':
    with Session() as db:
        result=populate(db);print(json.dumps({k:v for k,v in result.items() if not k.endswith('_ids')},ensure_ascii=True))
