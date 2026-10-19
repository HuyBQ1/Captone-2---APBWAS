import re
from .schemas import Plan, PlanStep, ToolArgs
from .provider import connected_plan
from .config import settings
from .tools import REGISTRY

def guard(request):
    patterns = [r'ignore.{0,40}(instruction|rule)',r' bỏ qua.{0,40}(chỉ dẫn|quy tắc|phê duyệt|quyền)',r'\b(drop|truncate|delete|update|insert)\s+(table|from|into|users|sales)',
                r'(system prompt|api.?key|mật khẩu.{0,20}(admin|người dùng)|bypass|jailbreak|developer message)']
    return any(re.search(pattern,' '+request,re.I) for pattern in patterns)

def make_plan(request,context):
    if guard(request):
        raise ValueError('Yêu cầu bị chặn bởi guardrails: chỉ dẫn vượt quyền hoặc thao tác không an toàn.')
    if not settings.demo_mode:
        return connected_plan(request,context,REGISTRY)
    text = request.lower()
    def step(name,**args):
        return PlanStep(tool=name,label=REGISTRY[name]['label'],arguments=ToolArgs(**args))
    month = re.search(r'\b(20\d{2}-(?:0[1-9]|1[0-2]))\b',text)
    month = month.group(1) if month else context.get('month')
    if any(word in text for word in ('điều chỉnh','sửa tồn','cập nhật tồn')):
        product = re.search(r'product_id[=: ]+([\w-]+)',text)
        quantity = re.search(r'(?:quantity|số lượng)[=: ]+(\d+)',text)
        if not product or not quantity:
            return Plan(steps=[],clarification='Bạn muốn điều chỉnh sản phẩm nào và số lượng mới là bao nhiêu? Dùng: product_id=<mã trong Dữ liệu doanh nghiệp> quantity=<số lượng>.') ,0
        return Plan(steps=[step('get_inventory_status'),step('propose_inventory_adjustment',product_id=product.group(1),quantity=int(quantity.group(1)))]),0
    if any(word in text for word in ('chính sách','nghỉ phép','tài liệu')):
        return Plan(steps=[step('search_internal_documents',query=request)]),0
    if any(word in text for word in ('tồn kho','hết hàng')):
        return Plan(steps=[step('get_inventory_status')]),0
    if any(word in text for word in ('doanh thu','báo cáo','so sánh','doanh số')):
        if '5 sản phẩm' in text:
            return Plan(steps=[step('query_declining_products',month=month)]),0
        return Plan(steps=[step('query_sales',month=month),step('compare_revenue_periods',month=month),step('generate_business_report',month=month)]),0
    return Plan(steps=[],clarification='Demo Mode hỗ trợ 4 kịch bản định trước. Bạn hãy chọn doanh thu, chính sách nghỉ phép, kiểm tra tồn kho hoặc đề xuất điều chỉnh tồn kho.'),0
