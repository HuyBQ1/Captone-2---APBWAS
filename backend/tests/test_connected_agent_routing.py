import pytest
from app import agent,models as m
from app.config import settings
from app.schemas import Plan,PlanStep,ToolArgs
from app.provider import ProviderError
from conftest import login,create,execute
from sqlalchemy import select,func

def test_explicit_today_and_pending_override_inherited_month_and_wrong_model_status(monkeypatch):
    monkeypatch.setattr(settings,'demo_mode',False)
    def planner(request,context,*args,**kwargs):
        assert context['month']!='2026-05'
        assert context['date']==context['today'] and context['order_status']=='pending'
        return Plan(steps=[PlanStep(tool='query_shop_orders',label='Đọc đơn',arguments=ToolArgs(query='confirmed',month='2026-05'))]),12
    monkeypatch.setattr(agent,'connected_plan',planner)
    plan,_=agent.make_plan('kiểm tra đơn hàng chờ xác nhận hôm nay',{'month':'2026-05'})
    args=plan.steps[0].arguments
    assert args.month is None and args.date and args.order_status=='pending' and args.query is None

def test_yesterday_filter_crosses_month_boundary():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today=datetime(2026,11,1,1,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
    assert agent.request_month('đơn hôm qua',{'month':'2026-05'},today)=='2026-10'
    assert agent.order_request_filters('đơn chờ xác nhận hôm qua',today)==('2026-10-31','pending')


@pytest.mark.parametrize(('text','status'),[
    ('đơn đã xác nhận','confirmed'),('đơn đang giao','shipping'),
    ('đơn đã giao','delivered'),('đơn đã hủy','cancelled'),
])
def test_order_status_handles_vietnamese_letter_d(text,status):
    assert agent.order_request_filters(text)[1]==status

def test_greeting_saves_model_reply_without_tool_execution(env,monkeypatch):
    client,factory,*_=env;login(client);monkeypatch.setattr(settings,'demo_mode',False)
    answer='Chào bạn! Bạn cần hỗ trợ gì hôm nay?'
    monkeypatch.setattr(agent,'connected_plan',lambda *args,**kwargs:(Plan(steps=[],clarification=answer),15))
    w=create(client,'chào');execute(factory,w['id'])
    with factory() as db:
        wf=db.get(m.Workflow,w['id'])
        assert wf.status=='completed' and wf.result['summary']==answer
        assert db.scalar(select(func.count()).select_from(m.ToolExecution).where(m.ToolExecution.workflow_id==wf.id))==0
        assert db.scalar(select(m.Message).where(m.Message.conversation_id==wf.conversation_id,m.Message.role=='assistant')).content==answer

@pytest.mark.parametrize('prompt',[
 'Tính lợi nhuận tháng 8 năm 2026',
 'Tạo Word và Excel báo cáo doanh thu tháng 7',
 'gửi mail file báo cáo này cho toàn bộ nhân viên',
 'Xem người nhận và xác nhận gửi',
 'cho tôi thêm file exel',
 'Tạo Word\nTiêu đề: Họp\nNội dung: Họp lúc 9 giờ.',
 'Kiểm tra tồn kho AP-001',
 'Giá tai nghe Nova bao nhiêu?',
 'Tóm tắt chính sách nghỉ phép',
])
def test_every_connected_business_request_reaches_selected_llm(prompt,monkeypatch):
    monkeypatch.setattr(settings,'demo_mode',False);calls=[]
    def planner(request,context,registry,**kwargs):
        calls.append((request,context,registry,kwargs))
        return Plan(steps=[PlanStep(tool='lookup_products',label='Model chọn tra sản phẩm',arguments=ToolArgs(query='T01'))]),42
    monkeypatch.setattr(agent,'connected_plan',planner)
    config={'model':'selected-model','tools':['lookup_products'],'permissions':['inventory.read']}
    plan,tokens=agent.make_plan(prompt,{'month':'2026-07','file_source':'finance'},timeout=15,agent_config=config)
    assert len(calls)==1 and set(calls[0][2])=={'lookup_products'}
    assert calls[0][3]['agent_config']==config and calls[0][3]['timeout']==15
    assert plan.steps[0].tool=='lookup_products' and tokens==42

def test_connected_quota_error_does_not_execute_a_default_report(env,monkeypatch):
    client,factory,*_=env;login(client);monkeypatch.setattr(settings,'demo_mode',False)
    def unavailable(*args,**kwargs):raise ProviderError('Nhà cung cấp đang giới hạn lượt gọi hoặc quota. (HTTP 429)')
    monkeypatch.setattr(agent,'connected_plan',unavailable)
    w=create(client,'Tạo Excel báo cáo doanh thu tháng 7');execute(factory,w['id'])
    response=client.get('/api/workflows/'+w['id']).json()
    assert response['status']=='failed' and '429' in response['error']
    assert response['result']['execution_mode']=='llm_agent' and not response['plan']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.GeneratedFile))==0
        assert db.scalar(select(func.count()).select_from(m.ToolExecution))==0

def test_generic_planner_receives_only_tools_allowed_for_current_role(env,monkeypatch):
    client,factory,*_=env;login(client,'Employee');monkeypatch.setattr(settings,'demo_mode',False)
    def planner(request,context,registry,**kwargs):
        assert 'prepare_report_email' not in registry and 'query_financial_summary' not in registry
        assert 'apply_approved_inventory_adjustment' not in registry and 'lookup_products' in registry
        return Plan(steps=[],clarification='Bạn muốn tra sản phẩm nào?'),7
    monkeypatch.setattr(agent,'connected_plan',planner)
    w=create(client,'Tra sản phẩm');execute(factory,w['id'])
    assert client.get('/api/workflows/'+w['id']).json()['status']=='completed'
