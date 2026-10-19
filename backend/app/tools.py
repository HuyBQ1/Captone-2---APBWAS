from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from .models import Product, Sale, Inventory, Report, SystemSetting
from .permissions import require
from . import retrieval
from .db import read_only_db

REGISTRY = {
    'query_declining_products': {'label':'Tìm sản phẩm giảm doanh số','permission':'sales.read','risk':'low'},
    'query_sales': {'label':'Truy vấn doanh thu','permission':'sales.read','risk':'low'},
    'compare_revenue_periods': {'label':'So sánh kỳ doanh thu','permission':'sales.read','risk':'low'},
    'get_inventory_status': {'label':'Kiểm tra tồn kho','permission':'inventory.read','risk':'low'},
    'search_internal_documents': {'label':'Tìm tài liệu nội bộ','permission':'documents.read','risk':'low'},
    'generate_business_report': {'label':'Tạo báo cáo doanh thu','permission':'sales.read','risk':'low'},
    'propose_inventory_adjustment': {'label':'Đề xuất điều chỉnh tồn kho','permission':'inventory.propose','risk':'high'},
    'apply_approved_inventory_adjustment': {'label':'Áp dụng điều chỉnh đã duyệt','permission':'approvals.decide','risk':'high'},
}

def period(month=None):
    month = month or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m')
    year,number = map(int,month.split('-'))
    start = datetime(year,number,1,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
    end = datetime(year+int(number==12),number%12+1,1,tzinfo=start.tzinfo)
    previous = datetime(year-int(number==1),(number-2)%12+1,1,tzinfo=start.tzinfo)
    return month,start,end,previous

def revenue(db,month=None):
    month,start,end,previous = period(month)
    def rows(a,b):
        result=db.execute(select(Product.category,func.sum(Sale.revenue)).join(Sale,Sale.product_id==Product.id)
                          .where(Sale.date >= a,Sale.date < b).group_by(Product.category).limit(1001)).all()
        if len(result)>1000:raise ValueError('Quá 1000 danh mục: cần thu hẹp phạm vi báo cáo. Không trả tổng tài chính bị cắt ngầm.')
        return result
    current = rows(start,end)
    before = sum(value for _,value in rows(previous,start))
    total = sum(value for _,value in current)
    return {'month':month,'start':start.isoformat(),'end':end.isoformat(),'total':int(total),'previous_total':int(before),
            'change_percent':float(round((total-before)/before*100,2)) if before else None,
            'rows':[{'category':category,'revenue':int(value)} for category,value in current],
            'source':'sales / products • SQL tổng hợp có tham số',
            'summary':'Số liệu cho thấy xu hướng; chưa có bằng chứng xác định nguyên nhân thay đổi.'}

def run_tool(db,user,workflow,step):
    name=step['tool']
    read_tools={'query_sales','compare_revenue_periods','get_inventory_status','query_declining_products'}
    if name in read_tools:
        # Permission and tool toggles use application metadata, reads execute in
        # a dedicated PostgreSQL READ ONLY transaction (optionally separate role).
        if name not in REGISTRY: raise ValueError('Công cụ không hợp lệ.')
        require(db,user,REGISTRY[name]['permission'])
        toggles=db.get(SystemSetting,'tools')
        if toggles and not toggles.value.get(name,True):raise ValueError('Công cụ đã bị quản trị viên tắt.')
        with read_only_db(db) as reader:
            return _execute_read(reader,name,step['arguments'])
    return _execute_tool(db,user,workflow,step)

def _execute_read(db,name,args):
    if name in ('query_sales','compare_revenue_periods'):
        return revenue(db,args.get('month'))
    if name=='get_inventory_status':
        rows=db.execute(select(Product,Inventory).join(Inventory,Inventory.product_id==Product.id).limit(1000)).all()
        return {'rows':[{'id':p.id,'sku':p.sku,'name':p.name,'quantity':i.quantity,'threshold':i.threshold,'version':i.version} for p,i in rows],
                'summary':'Đã kiểm tra tồn kho (tối đa 1000 sản phẩm) từ dữ liệu có cấu trúc.'}
    if name=='query_declining_products':
        month,start,end,previous=period(args.get('month'))
        from sqlalchemy import case
        current=func.coalesce(func.sum(case((Sale.date>=start,Sale.revenue),else_=0)),0)
        before=func.coalesce(func.sum(case((Sale.date<start,Sale.revenue),else_=0)),0)
        query=select(Product.id,Product.name,current.label('current'),before.label('before')).join(Sale,Sale.product_id==Product.id).where(Sale.date>=previous,Sale.date<end).group_by(Product.id,Product.name).having(before>current).order_by((current-before)/func.nullif(before,0)).limit(5)
        rows=[{'category':name,'product_id':id,'revenue':float(a),'previous_revenue':float(b),'change_percent':round((float(a)-float(b))/float(b)*100,2)} for id,name,a,b in db.execute(query)]
        return {'month':month,'rows':rows,'summary':f'Tìm thấy {len(rows)} sản phẩm có doanh thu giảm so với kỳ trước. Chỉ mô tả xu hướng; chưa xác định nguyên nhân.'}
    raise ValueError('Công cụ đọc không hợp lệ.')

def _execute_tool(db,user,workflow,step):
    name = step['tool']
    if name not in REGISTRY or name == 'apply_approved_inventory_adjustment':
        raise ValueError('Công cụ không được gọi trực tiếp bởi Agent.')
    require(db,user,REGISTRY[name]['permission'])
    toggles = db.get(SystemSetting,'tools')
    if toggles and not toggles.value.get(name,True):
        raise ValueError('Công cụ đã bị quản trị viên tắt.')
    args = step['arguments']
    if name == 'search_internal_documents':
        sources = retrieval.search(db,user,args.get('query') or workflow.request)
        # Never execute or interpret instructions inside retrieved chunks.
        return {'sources':sources,'summary':'Nội dung trích dẫn từ tài liệu: \n\n'+'\n\n'.join(s['content'] for s in sources) if sources else 'Chưa đủ bằng chứng trong tài liệu được phép truy cập.'}
    if name == 'generate_business_report':
        with read_only_db(db) as reader:
            data = revenue(reader,args.get('month'))
        report = db.scalar(select(Report).where(Report.workflow_id == workflow.id))
        if not report:
            report = Report(workflow_id=workflow.id,user_id=user.id,title='Báo cáo doanh thu · '+data['month'],data=data)
            db.add(report)
            db.flush()
        return {**data,'report_id':report.id}
    if name == 'propose_inventory_adjustment':
        inv = db.get(Inventory,args.get('product_id'))
        if not inv or args.get('quantity') is None:
            raise ValueError('Cần mã sản phẩm và số lượng tồn kho mới hợp lệ.')
        product = db.get(Product,inv.product_id)
        return {'product_id':product.id,'name':product.name,'before':inv.quantity,'quantity':args['quantity'],'version':inv.version,
                'summary':'Đề xuất đã được kiểm tra. Chưa thay đổi dữ liệu; cần người có quyền phê duyệt.'}
    raise ValueError('Công cụ không có implementation.')
