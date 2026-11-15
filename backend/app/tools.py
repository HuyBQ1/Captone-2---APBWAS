from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from .models import Product, Sale, Inventory, Report, SystemSetting
from .permissions import require,permissions
from . import retrieval
from .db import read_only_db
from .products import lookup_products, matching_products, inventory_query

REGISTRY = {
    'query_shop_orders': {'label':'Tra cứu đơn hàng website','permission':'sales.read','risk':'low','description':'Đọc đơn tạo trên website Nova Commerce, gồm đơn chờ/xác nhận/đang giao/đã giao/hủy/hoàn. date lọc ngày tạo YYYY-MM-DD, order_status lọc độc lập; month chỉ dùng khi không lọc ngày. pending=chờ xác nhận; confirmed=đã xác nhận. Đọc trực tiếp API để thấy đơn mới. query=today cho số đơn hôm nay; query=unfinished gộp pending+confirmed+shipping cho đơn chưa hoàn thành; query có thể là mã NOVA-id hoặc một trạng thái pending/confirmed/shipping/delivered/cancelled/returned. Tổng giá trị đơn chưa phải doanh thu ghi nhận. Không có dữ liệu cá nhân khách hàng.'},
    'get_company_profile': {'label':'Đọc hồ sơ doanh nghiệp','permission':'agents.run','risk':'low','description':'Đọc tên doanh nghiệp, liên hệ/địa chỉ/mã số thuế đã cấu hình của workspace và nhóm hàng nếu có quyền inventory.read. Dùng cho “đây là công ty gì”, “giới thiệu công ty”, thông tin doanh nghiệp. Không suy đoán pháp nhân, lĩnh vực đăng ký hoặc số liệu tài chính. Không cần tìm quy trình nội bộ cho câu hỏi chỉ hỏi tên công ty.'},
    'prepare_report_email': {'label':'Soạn email và đính kèm báo cáo trong hội thoại','permission':'mail.send','risk':'high','description':'Tạo bản nháp gửi toàn bộ nhân viên, đính kèm Word/Excel đã tạo trong chính hội thoại, theo month nếu có. Kiểm tra quyền từng tệp. Không tự gửi; người dùng xem người nhận, nội dung và tệp rồi xác nhận trên trang email.'},
    'create_word_file': {'label':'Tạo tệp Word','permission':'agents.run','risk':'low','description':'Tạo DOCX thật, lưu database và trả nút tải. source=finance cho báo cáo tháng (cần sales.read+inventory.read), inventory/products cho dữ liệu kho/hàng hóa (inventory.read), knowledge cho trích nguồn tài liệu (documents.read), custom cho nội dung tự soạn. title là tiêu đề; body_text toàn văn cho custom; columns/rows tùy chọn cho bảng Word tối đa 8 cột. Không bịa số liệu doanh nghiệp; chọn source database phù hợp. Chỉ tạo tệp, không gửi mail.'},
    'create_excel_file': {'label':'Tạo tệp Excel','permission':'agents.run','risk':'low','description':'Tạo XLSX thật có công thức và giá trị tính sẵn. source=finance xuất báo cáo tháng từ DB (sales.read+inventory.read); inventory/products xuất dữ liệu hiện tại (inventory.read); custom dùng title, columns và rows (mỗi dòng đủ số cột, tối đa 1000 dòng 20 cột). Công thức truyền riêng formulas=[{cell:"C2",expression:"=A2*B2"}], ô đầu bảng A1 là tên cột, dữ liệu từ dòng 2. Chỉ hỗ trợ + - * /, SUM AVERAGE MIN MAX COUNT ROUND, tham chiếu cùng sheet trong phạm vi bảng; ô đích phải nằm trong rows. Không tạo macro, mã Python, liên kết ngoài hoặc bịa dữ liệu doanh nghiệp.'},
    'open_employee_email': {'label':'Mở lại email trong hội thoại','permission':'mail.send','risk':'low','description':'Đọc đợt email gần nhất trong cùng hội thoại của người dùng và trả liên kết xem lại. Không tạo email, không xác nhận gửi, không gọi Google.'},
    'prepare_revenue_email': {'label':'Đọc doanh thu và soạn thư cho nhân viên','permission':'mail.send','risk':'high','description':'Đọc doanh thu tháng từ SQL rồi tạo bản nháp email cho toàn bộ nhân viên. Cần thêm sales.read. month định dạng YYYY-MM; không bịa số liệu, không gửi ngay. Người dùng phải xem danh sách, nội dung và xác nhận gửi.'},
    'prepare_employee_email': {'label':'Soạn email cho nhân viên','permission':'mail.send','risk':'high','description':'Chỉ tạo bản nháp email, chưa gửi. subject là tiêu đề một dòng, body_text là toàn văn nội dung. recipient_ids bỏ trống để chọn tất cả nhân viên đang hoạt động; chỉ dùng ID thật nếu người dùng chỉ định. Người dùng phải mở bản nháp xem danh sách và xác nhận gửi.'},
    'query_financial_summary': {'label':'Tính số đơn, doanh thu và lời lỗ tháng','permission':'sales.read','risk':'low','description':'Tổng hợp SQL theo tháng: số dòng bán, số đơn có mã, doanh thu, giá vốn, chi phí, lợi nhuận vận hành. Nêu rõ dữ liệu thiếu, không suy đoán lời lỗ. Tồn kho là số hiện tại.'},
    'lookup_products': {'label':'Tra cứu hàng hóa và giá bán','permission':'inventory.read','risk':'low',
                        'description':'Đọc bảng products để tìm giá bán, tên, SKU, danh mục sản phẩm. query là tên hoặc SKU được người dùng cung cấp (bỏ phần câu hỏi); product_id tùy chọn nếu biết ID thật. Không cần product_id khi có tên/SKU. query trống để liệt kê tối đa 20 sản phẩm. Không tìm giá hàng hóa trong tài liệu.'},
    'query_declining_products': {'label':'Tìm sản phẩm giảm doanh số','permission':'sales.read','risk':'low'},
    'query_sales': {'label':'Truy vấn doanh thu','permission':'sales.read','risk':'low'},
    'compare_revenue_periods': {'label':'So sánh kỳ doanh thu','permission':'sales.read','risk':'low'},
    'get_inventory_status': {'label':'Kiểm tra tồn kho','permission':'inventory.read','risk':'low',
                             'description':'Đọc số lượng tồn kho và ngưỡng cảnh báo. query là tên/SKU, product_id nếu biết ID thật; bỏ query để xem danh sách. low_stock=true chỉ lấy sản phẩm có quantity <= threshold. Không tự bịa ID.'},
    'search_internal_documents': {'label':'Tìm tài liệu nội bộ','permission':'documents.read','risk':'low','description':'Chỉ tìm nội dung tài liệu như chính sách, quy trình, hướng dẫn. Giá bán/SKU/danh mục hàng hóa dùng lookup_products; tồn kho dùng get_inventory_status.'},
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

def revenue(db,month=None,cutoff=None):
    month,start,end,previous = period(month)
    def rows(a,b):
        result=db.execute(select(Product.category,func.sum(Sale.revenue)).join(Sale,Sale.product_id==Product.id)
                          .where(Sale.date >= a,Sale.date < b).group_by(Product.category).limit(1001)).all()
        if len(result)>1000:raise ValueError('Quá 1000 danh mục: cần thu hẹp phạm vi báo cáo. Không trả tổng tài chính bị cắt ngầm.')
        return result
    effective_end=min(end,cutoff) if cutoff else end
    current = rows(start,effective_end)
    before = sum(value for _,value in rows(previous,start))
    total = sum(value for _,value in current)
    change=float(round((total-before)/before*100,2)) if before else None
    amount=lambda value:f'{int(value):,}'.replace(',','.')+' ₫'
    comparison=f'Biến động {change:+.2f}%.' if change is not None else 'Kỳ trước chưa có doanh thu để tính phần trăm biến động.'
    return {'month':month,'start':start.isoformat(),'end':effective_end.isoformat(),'total':int(total),'previous_total':int(before),
            'change_percent':change,
            'rows':[{'category':category,'revenue':int(value)} for category,value in current],
            'source':'sales / products • SQL tổng hợp có tham số',
            'summary':f'Doanh thu tháng {month}: **{amount(total)}**; kỳ trước: **{amount(before)}**. {comparison} Chưa có bằng chứng xác định nguyên nhân thay đổi.'}

def run_tool(db,user,workflow,step):
    from .agent_runtime import assert_tool
    agent_config=assert_tool(db,user,workflow,step['tool'])
    name=step['tool']
    read_tools={'lookup_products','query_sales','compare_revenue_periods','get_inventory_status','query_declining_products','query_financial_summary','query_shop_orders'}
    if name in read_tools:
        # Permission and tool toggles use application metadata, reads execute in
        # a dedicated PostgreSQL READ ONLY transaction (optionally separate role).
        if name not in REGISTRY: raise ValueError('Công cụ không hợp lệ.')
        require(db,user,REGISTRY[name]['permission'])
        if name=='query_financial_summary':require(db,user,'inventory.read')
        toggles=db.get(SystemSetting,'tools',populate_existing=True)
        if toggles and not toggles.value.get(name,True):raise ValueError('Công cụ đã bị quản trị viên tắt.')
        with read_only_db(db) as reader:
            result=_execute_read(reader,name,step['arguments'])
            from .shop_connection import setting
            source=setting(reader)
            if source and source.value.get('last_sync'):
                result={**result,'source':result.get('source') if result.get('live_source') else 'Nova Commerce API → APBWAS','synced_at':result.get('synced_at') or source.value['last_sync']}
            return result
    return _execute_tool(db,user,workflow,step)

def _execute_read(db,name,args):
    if name=='query_shop_orders':
        from .shop_connection import order_summary
        return order_summary(db,args,fresh=True)
    if name=='query_financial_summary':
        from .finance import finance_summary
        return finance_summary(db,args.get('month'))
    if name=='lookup_products':
        return lookup_products(db,args)
    if name in ('query_sales','compare_revenue_periods'):
        return revenue(db,args.get('month'))
    if name=='get_inventory_status':
        selected=matching_products(db,{**args,'query':inventory_query(args.get('query'))})
        query=select(Product,Inventory).join(Inventory,Inventory.product_id==Product.id).where(Product.id.in_(selected.with_only_columns(Product.id)))
        if args.get('low_stock'):query=query.where(Inventory.quantity<=Inventory.threshold)
        found=db.execute(query.order_by(Product.sku).limit(21)).all()
        rows=[{'id':p.id,'sku':p.sku,'name':p.name,'quantity':i.quantity,'threshold':i.threshold,'version':i.version} for p,i in found[:20]]
        summary=('Không có sản phẩm sắp hết hàng trong phạm vi tra cứu.' if args.get('low_stock') else 'Không tìm thấy dữ liệu tồn kho phù hợp.') if not rows else '\n'.join(
            f"- {row['name']} (SKU: {row['sku']}): **{row['quantity']} đơn vị**, ngưỡng cảnh báo {row['threshold']}." for row in rows)
        if len(found)>20:summary+='\n\nChỉ hiển thị 20 sản phẩm đầu tiên. Hãy thu hẹp tên hoặc SKU.'
        return {'rows':rows,'truncated':len(found)>20,'source':'products / inventory • SQL chỉ đọc, có tham số','summary':summary}
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
    toggles = db.get(SystemSetting,'tools',populate_existing=True)
    if toggles and not toggles.value.get(name,True):
        raise ValueError('Công cụ đã bị quản trị viên tắt.')
    args = step['arguments']
    if name=='get_company_profile':
        from .models import Workspace
        workspace=db.get(Workspace,user.workspace_id)
        row=db.get(SystemSetting,'company') if user.workspace_id=='primary' else None
        profile={k:(row.value.get(k) or '') for k in ('name','email','phone','address','tax_code')} if row else {'name':workspace.name if workspace else ''}
        categories=[]
        if user.workspace_id=='primary' and 'inventory.read' in permissions(db,user) and (not workflow.agent_id or 'inventory.read' in workflow.agent_snapshot.get('permissions',[])):
            with read_only_db(db) as reader:categories=list(reader.scalars(select(Product.category).where(Product.active.is_(True)).distinct().order_by(Product.category).limit(10)))
        from .config import settings
        sample=bool(settings.sample_data or settings.demo_mode)
        summary='Doanh nghiệp trong workspace là **'+profile['name']+'**.' if profile.get('name') else 'Workspace chưa cấu hình tên doanh nghiệp.'
        if categories:summary+=' Danh mục hàng hóa hiện có: '+', '.join(categories)+'.'
        if sample:summary+=' Hệ thống đang sử dụng dữ liệu mẫu/mô phỏng.'
        return {'company_profile':profile,'categories':categories,'sample_data':sample,'workspace_id':user.workspace_id,'source':'Hồ sơ workspace và danh mục hàng hóa được cấp quyền','summary':summary}
    if name=='prepare_report_email':
        from .mail_campaigns import report_draft
        return report_draft(db,user,workflow,args)
    if name in ('create_word_file','create_excel_file'):
        from .office_files import create_file
        return create_file(db,user,workflow,args,'docx' if name=='create_word_file' else 'xlsx')
    if name == 'open_employee_email':
        from .mail_campaigns import open_from_conversation
        return open_from_conversation(db,user,workflow)
    if name == 'prepare_revenue_email':
        require(db,user,'sales.read')
        from .mail_campaigns import revenue_draft
        return revenue_draft(db,user,workflow,args)
    if name == 'prepare_employee_email':
        from .mail_campaigns import draft_from_tool
        return draft_from_tool(db,user,workflow,args)
    if name == 'search_internal_documents':
        ids=workflow.agent_snapshot.get('knowledge_ids',[]) if workflow.agent_id else None
        sources = retrieval.search(db,user,args.get('query') or workflow.request,document_ids=ids) if ids is not None else retrieval.search(db,user,args.get('query') or workflow.request)
        # Never execute or interpret instructions inside retrieved chunks.
        return {'sources':sources,'summary':f'Đã tìm thấy {len(sources)} đoạn tài liệu được phép truy cập. Xem các nguồn bên dưới để đọc nội dung gốc.' if sources else 'Chưa đủ bằng chứng trong tài liệu được phép truy cập.'}
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
        from .shop_connection import block_local_write
        block_local_write(db)
        inv = db.get(Inventory,args.get('product_id'))
        if not inv or args.get('quantity') is None:
            raise ValueError('Cần mã sản phẩm và số lượng tồn kho mới hợp lệ.')
        product = db.get(Product,inv.product_id)
        return {'product_id':product.id,'name':product.name,'before':inv.quantity,'quantity':args['quantity'],'version':inv.version,
                'summary':'Đề xuất đã được kiểm tra. Chưa thay đổi dữ liệu; cần người có quyền phê duyệt.'}
    raise ValueError('Công cụ không có implementation.')
