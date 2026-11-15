import re
import unicodedata
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .schemas import Plan, PlanStep, ToolArgs
from .provider import connected_plan
from .config import settings
from .tools import REGISTRY

def guard(request):
    patterns = [r'ignore.{0,40}(instruction|rule)',r' bỏ qua.{0,40}(chỉ dẫn|quy tắc|phê duyệt|quyền)',r'\b(drop|truncate|delete|update|insert)\s+(table|from|into|users|sales)',
                r'(system prompt|api.?key|mật khẩu.{0,20}(admin|người dùng)|bypass|jailbreak|developer message)']
    return any(re.search(pattern,' '+request,re.I) for pattern in patterns)

def request_month(request,context,today=None):
    """An explicit month overrides history; a missing year inherits only the year."""
    text=''.join(c for c in unicodedata.normalize('NFD',request.lower()) if not unicodedata.combining(c))
    today=today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    inherited=context.get('month')
    year=inherited[:4] if isinstance(inherited,str) and re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])',inherited) else str(today.year)
    iso=re.search(r'\b(20\d{2})-(\d{1,2})\b',text)
    local=re.search(r'\b(\d{1,2})\s*[/.-]\s*(20\d{2})\b',text)
    named=re.search(r'\bthang\s+(\d{1,2})\b(?:\s+(?:nam\s+)?(20\d{2})\b)?',text)
    if iso or local or named:
        if iso:year,number=iso[1],int(iso[2])
        elif local:number,year=int(local[1]),local[2]
        else:number,year=int(named[1]),named[2] or year
        if not 1<=number<=12:raise ValueError('Tháng phải từ 1 đến 12. Bạn muốn báo cáo tháng nào, năm nào?')
        return f'{year}-{number:02}'
    if any(v in text for v in ('thang truoc','thang nay')) and not ('so sanh' in text and inherited):
        number=today.year*12+today.month-1-int('thang truoc' in text)
        return f'{number//12}-{number%12+1:02}'
    if any(day in text for day in ('hom nay','hom qua')):
        return (today-timedelta(days=int('hom qua' in text))).strftime('%Y-%m')
    return inherited

def order_request_filters(request,today=None):
    today=today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    text=''.join(c for c in unicodedata.normalize('NFD',request.lower()) if not unicodedata.combining(c)).replace('đ','d')
    date=(today-timedelta(days=1)).date().isoformat() if 'hom qua' in text else today.date().isoformat() if 'hom nay' in text else None
    status=None
    for phrases,value in [(('cho xac nhan','chua xac nhan','cho xu ly'),'pending'),(('da xac nhan',),'confirmed'),(('chua hoan thanh',),'unfinished'),(('dang giao',),'shipping'),(('da giao',),'delivered'),(('da huy',),'cancelled'),(('hoan hang',),'returned')]:
        if any(p in text for p in phrases):status=value;break
    return date,status

def make_plan(request,context,timeout=None,agent_config=None):
    if guard(request):
        raise ValueError('Yêu cầu bị chặn bởi guardrails: chỉ dẫn vượt quyền hoặc thao tác không an toàn.')
    text = request.lower()
    def step(name,**args):
        return PlanStep(tool=name,label=REGISTRY[name]['label'],arguments=ToolArgs(**args))
    try:month=request_month(request,context)
    except ValueError as exc:return Plan(steps=[],clarification=str(exc)),0
    if month:context={**context,'month':month}
    if not settings.demo_mode:
        # Connected Mode has one planner: the selected LLM chooses every tool.
        # The deterministic routes below are confined to the isolated demo.
        names=agent_config.get('tools',REGISTRY) if agent_config else REGISTRY
        registry={k:v for k,v in REGISTRY.items() if k in names and k!='apply_approved_inventory_adjustment'}
        date,status=order_request_filters(request)
        context={**context,'today':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat(),'timezone':'Asia/Ho_Chi_Minh',**({'date':date} if date else {}),**({'order_status':status} if status else {})}
        plan,tokens=connected_plan(request,context,registry,timeout=timeout,agent_config=agent_config)
        # The LLM still selects tools. Explicit user filters constrain its
        # arguments, preventing inherited months and swapped business statuses.
        for item in plan.steps:
            if item.tool!='query_shop_orders':continue
            if date:item.arguments.date=date;item.arguments.month=None
            if status:item.arguments.order_status=status
            if item.arguments.query in ('today','pending','confirmed','shipping','delivered','cancelled','returned','unfinished') and (date or status):
                if item.arguments.query=='today' and not date:item.arguments.date=context['today']
                elif not status and item.arguments.query!='today':item.arguments.order_status=item.arguments.query
                item.arguments.query=None
        return plan,tokens
    if re.fullmatch(r'\s*(?:xem người nhận và xác nhận gửi|(?:mở|xem)(?: lại)? (?:bản nháp|email đã soạn|thư đã soạn)(?: email)?)[.!?\s]*',text):
        return Plan(steps=[step('open_employee_email')]),0
    mail_words=('gửi mail','gửi email','soạn email','soạn mail','gửi thư','soạn thư','gửi cho nhân viên')
    previous=context.get('previous_request','').lower()
    continuation=bool(re.match(r'\s*(?:nội dung|chủ đề|báo cáo doanh thu|báo cáo tháng)',text)) and any(v in previous for v in mail_words)
    mail=any(v in text for v in mail_words) or continuation
    mail_text=previous+' '+text if continuation else text
    all_staff=bool(re.search(r'(?:tất cả|toàn bộ|các)\s+nhân viên',mail_text) or re.search(r'cho\s+nhân viên[.!?\s]*$',mail_text))
    if mail and all_staff and any(v in mail_text for v in ('file','tệp','báo cáo')) and not re.search(r'tiêu đề\s*:',text):
        return Plan(steps=[step('prepare_report_email',month=month)]),0
    word_file=bool(re.search(r'\b(word|docx)\b',text));excel_file=bool(re.search(r'\b(excel|exel|xlsx)\b',text))
    followup_file=bool(re.search(r'\b(?:thêm|lại|chuyển|đổi|bản|cho tôi)\b',text))
    if (word_file or excel_file) and (followup_file or any(v in text for v in ('tạo','xuất','làm','soạn','lập','tải file','cho tôi file'))):
        explicit=re.search(r'tiêu đề\s*:\s*([^\r\n]+)\s*\n\s*nội dung\s*:\s*([\s\S]+)',request,re.I)
        if word_file and not excel_file and explicit:
            return Plan(steps=[step('create_word_file',source='custom',title=explicit[1].strip(),body_text=explicit[2].strip())]),0
        source='finance' if any(v in text for v in ('doanh thu','tài chính','lời lỗ','lợi nhuận','giá vốn','lãi lỗ','chi phí','số đơn')) else 'inventory' if any(v in text for v in ('tồn kho','hết hàng')) else 'products' if any(v in text for v in ('danh mục sản phẩm','danh sách sản phẩm','danh mục hàng hóa','giá sản phẩm')) else 'knowledge' if word_file and any(v in text for v in ('tài liệu nội bộ','chính sách','quy trình')) else None
        if source is None and followup_file and context.get('file_source') in ('finance','inventory','products','knowledge'):
            source=context['file_source']
        if source:
            if source=='knowledge' and excel_file:return Plan(steps=[],clarification='Chọn Word để trích nội dung tài liệu nội bộ; Excel dành cho bảng dữ liệu. Bạn muốn tạo định dạng nào?'),0
            steps=[]
            if word_file:steps.append(step('create_word_file',source=source,month=month,query=request if source=='knowledge' else None))
            if excel_file:steps.append(step('create_excel_file',source=source,month=month))
            return Plan(steps=steps),0
        if settings.demo_mode:
            return Plan(steps=[],clarification='Bạn muốn tạo tài liệu hoặc bảng tính về chủ đề gì? Có thể yêu cầu báo cáo tài chính theo tháng, danh sách tồn kho, hoặc cung cấp tiêu đề và nội dung. Demo Mode chưa tự soạn bảng tùy ý.'),0
    if mail:
        if 'doanh thu' in text and not re.search(r'nội dung\s*:',text):
            all_staff=bool(re.search(r'(?:tất cả|toàn bộ|các)\s+nhân viên',text) or re.search(r'cho\s+nhân viên[.!?\s]*$',text))
            if not all_staff:return Plan(steps=[],clarification='Bạn muốn gửi báo cáo doanh thu cho toàn bộ nhân viên hay một nhóm? Hãy ghi “cho toàn bộ nhân viên”, hoặc chọn nhóm trong trang Gmail.'),0
            # This is a database-backed business template, independent of the
            # external language planner. It creates a reviewable draft only.
            return Plan(steps=[step('prepare_revenue_email',month=month)]),0
        match=re.search(r'tiêu đề\s*:\s*([^\r\n]+)\s*\n\s*nội dung\s*:\s*([\s\S]+)',request,re.I)
        if not match:return Plan(steps=[],clarification='Hãy cung cấp Tiêu đề: ... và Nội dung: ... trên hai dòng để tạo bản nháp gửi toàn bộ nhân viên. Bạn sẽ xem trước và xác nhận trước khi gửi.'),0
        if not any(word in text for word in ('tất cả','toàn bộ')):return Plan(steps=[],clarification='Bạn muốn gửi toàn bộ nhân viên hay một nhóm? Chọn nhóm cụ thể tại Gmail → Soạn email.'),0
        return Plan(steps=[step('prepare_employee_email',subject=match.group(1).strip(),body_text=match.group(2).strip())]),0
    finance=any(word in text for word in ('lời','lỗ','lãi','lợi nhuận','giá vốn','chi phí','số đơn','bao nhiêu đơn','excel'))
    if finance and not any(word in text for word in ('chính sách','quy trình','tài liệu','điều chỉnh')):
        # Isolated Demo Mode only: deterministic arithmetic route.
        return Plan(steps=[step('query_financial_summary',month=month)]),0
    if any(word in text for word in ('điều chỉnh','sửa tồn','cập nhật tồn')):
        product = re.search(r'product_id[=: ]+([\w-]+)',text)
        quantity = re.search(r'(?:quantity|số lượng)[=: ]+(\d+)',text)
        if not product or not quantity:
            return Plan(steps=[],clarification='Bạn muốn điều chỉnh sản phẩm nào và số lượng mới là bao nhiêu? Dùng: product_id=<mã trong Dữ liệu doanh nghiệp> quantity=<số lượng>.') ,0
        return Plan(steps=[step('get_inventory_status'),step('propose_inventory_adjustment',product_id=product.group(1),quantity=int(quantity.group(1)))]),0
    if any(word in text for word in ('chính sách','nghỉ phép','tài liệu')):
        return Plan(steps=[step('search_internal_documents',query=request)]),0
    if any(word in text for word in ('tồn kho','hết hàng','còn bao nhiêu')):
        low=any(word in text for word in ('hết hàng','sắp hết','tồn kho thấp'))
        generic=low or any(word in text for word in ('tất cả','danh sách'))
        return Plan(steps=[step('get_inventory_status',query=None if generic else request,low_stock=low)]),0
    if any(word in text for word in ('doanh thu','báo cáo','so sánh','doanh số')):
        if '5 sản phẩm' in text:
            return Plan(steps=[step('query_declining_products',month=month)]),0
        return Plan(steps=[step('query_sales',month=month),step('compare_revenue_periods',month=month),step('generate_business_report',month=month)]),0
    if any(word in text for word in ('giá','sku','sản phẩm','hàng hóa')):
        listing=any(word in text for word in ('danh sách','liệt kê'))
        return Plan(steps=[step('lookup_products',query='' if listing else request)]),0
    return Plan(steps=[],clarification='Bạn hãy chọn tra giá hàng hóa, doanh thu, chính sách nghỉ phép, kiểm tra tồn kho hoặc đề xuất điều chỉnh tồn kho.'),0
