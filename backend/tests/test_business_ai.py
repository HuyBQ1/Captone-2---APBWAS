import json
import pytest
import httpx
from sqlalchemy import select
from app import business_ai,models as m,provider
from app.schemas import Plan,PlanStep,ToolArgs
from conftest import login,create,execute
from test_provider import compatible,transport,result

@pytest.mark.parametrize('workflow_timeout',[60,10])
def test_answer_uses_configured_timeout_without_exceeding_workflow_deadline(env,compatible,monkeypatch,workflow_timeout):
    from app import agent
    from app.config import settings
    client,factory,*_=env;login(client)
    monkeypatch.setattr(settings,'ai_timeout_seconds',120)
    with factory() as db:
        row=db.get(m.SystemSetting,'limits');row.value={**row.value,'timeout':workflow_timeout};db.commit()
    monkeypatch.setattr(agent,'connected_plan',lambda *args,**kwargs:(Plan(steps=[PlanStep(tool='get_inventory_status',label='Đọc tồn kho')]),5))
    seen=[]
    def analyze(db,user,wf,config,timeout):
        seen.append(timeout)
        assert min(25,workflow_timeout-2)<timeout<=workflow_timeout
        return {'status':'completed','text':'Đã đọc dữ liệu được cấp quyền.'},3
    monkeypatch.setattr(business_ai,'analyze',analyze)
    w=create(client,'Đọc tồn kho');execute(factory,w['id'])
    assert len(seen)==1
    assert client.get('/api/workflows/'+w['id']).json()['status']=='completed'

def test_company_metrics_are_sent_to_selected_llm_and_answer_is_saved(env,compatible,monkeypatch):
    client,factory,*_=env;login(client)
    calls=[]
    def handler(request):
        data=json.loads(request.content);payload=json.loads(data['messages'][1]['content']);calls.append(payload)
        assert payload['request']=='Tính lợi nhuận tháng này'
        context=payload['context']
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'query_financial_summary','label':'Tính tài chính','arguments':{'month':context['month']}}]))
        assert data['max_tokens']==1200
        assert context['evidence'][0]['tool']=='query_financial_summary'
        revenue=context['evidence'][0]['data']['revenue'];assert revenue['value']==400000
        assert context['evidence'][0]['data']['average_unit_revenue']['value']==100000
        assert context['evidence'][0]['data']['average_order_value'] is None
        assert 'password' not in json.dumps(context) and 'api_key' not in json.dumps(context)
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Doanh thu ghi nhận là '+revenue['reference']+'. Chưa đủ dữ liệu xác nhận lợi nhuận vận hành.'})))
    transport(monkeypatch,handler)
    w=create(client,'Tính lợi nhuận tháng này');execute(factory,w['id'])
    r=client.get('/api/workflows/'+w['id']).json();assert r['status']=='completed',r['error']
    assert r['result']['business_analysis']['status']=='completed'
    assert '400.000' in r['result']['summary'] and r['tokens']==642 and len(calls)==2
    with factory() as db:
        assert db.scalar(select(m.UsageRecord).where(m.UsageRecord.workflow_id==w['id'])).tokens==642
        assert db.scalars(select(m.Message).where(m.Message.conversation_id==w['conversation_id'],m.Message.role=='assistant')).one().content==r['result']['business_analysis']['text']

@pytest.mark.parametrize('text',['Doanh thu 999999 đồng.','Doanh thu {{v99}}.','Không có số liệu.','Đọc tại https://evil.example {{v0}}'])
def test_ai_cannot_insert_unverified_numbers_or_links(text):
    with pytest.raises(provider.ProviderError):business_ai.render_answer(text,{'v0':400000})

def test_grounded_decimal_is_formatted_from_actual_calculation():
    assert business_ai.render_answer('Giá trị trung bình {{v0}}.',{'v0':12345.678})=='Giá trị trung bình 12.345,68.'

def test_order_identifiers_and_local_dates_are_verified_without_allowing_invented_counts():
    context=business_ai.grounded_context([{'data':{'as_of':'2026-11-11','created_order_count':1,'rows':[{'order_number':'NOVA-385','date':'2026-11-10T20:18:50.962752+00:00'}]}}])
    values=context['values']
    assert context['evidence'][0]['data']['rows'][0]['date']=='2026-11-11T03:18:50.962752+07:00'
    answer='Ngày 11/11/2026 có 1 đơn NOVA-385, tạo lúc 03:18 11/11/2026. Chưa xác định số khách riêng biệt.'
    assert business_ai.render_answer(answer,values,allow_prose=True)==answer
    for text in ('Có 999 đơn NOVA-385.','Đơn NOVA-386.','Ngày 12/11/2026 có 1 đơn.','Có 2 khách đặt hàng.'):
        with pytest.raises(provider.ProviderError):business_ai.render_answer(text,values,allow_prose=True)

def test_order_answer_cannot_claim_zero_when_source_has_orders():
    evidence=[{'tool':'query_shop_orders','data':{'created_order_count':1}}]
    with pytest.raises(provider.ProviderError):business_ai.validate_order_answer('Có 1 đơn. Dữ liệu không cho thấy đơn nào được tạo hôm nay.',evidence)
    assert business_ai.validate_order_answer('Có 1 đơn tạo hôm nay. Chưa có dữ liệu đếm khách hàng riêng biệt.',evidence)

def test_order_count_context_omits_details_and_sums_disjoint_statuses_once(env):
    _,factory,users,_=env
    with factory() as db:
        wf=m.Workflow(user_id=users['Manager'],request='Hiện tại có bao nhiêu đơn hàng chưa hoàn thành',idempotency_key='compact-order-count',plan=[{'tool':'query_shop_orders','arguments':{'query':s}} for s in ('pending','confirmed','shipping','pending')])
        db.add(wf);db.flush()
        for i,(status,total) in enumerate([('pending',27),('confirmed',27),('shipping',23),('pending',27)]):
            rows=[{'order_number':'NOVA-'+str(n),'date':'2026-11-11T03:18:00+07:00','total':10000000,'units':1,'status':status} for n in range(20)]
            db.add(m.WorkflowStep(workflow_id=wf.id,position=i,tool='query_shop_orders',status='completed',output={'created_order_count':total,'rows':rows,'truncated':True,'synced_at':'2026-11-11T03:30:00+07:00'}))
        db.flush();evidence=business_ai.collect(db,db.get(m.User,users['Manager']),wf)
        assert all('rows' not in e['data'] for e in evidence)
        assert evidence[-1]['data']['unfinished_order_count']==77
        assert len(json.dumps(business_ai.grounded_context(evidence),ensure_ascii=False))<5000
        # Detailed listing requests retain source rows and original counts.
        wf.request='Liệt kê đơn chờ xử lý';db.flush()
        detail=business_ai.collect(db,db.get(m.User,users['Manager']),wf)
        assert len(detail[0]['data']['rows'])==20 and detail[0]['data']['created_order_count']==27

def test_analysis_cannot_claim_saved_file_was_not_created():
    with pytest.raises(provider.ProviderError,match='mô tả sai trạng thái tệp'):
        business_ai.render_answer('Tôi chưa thể tạo tệp DOCX. Doanh thu {{v0}}.',{'v0':400000},files_created=True)

def test_verified_sku_month_and_product_name_digits_are_not_false_numeric_claims():
    context=business_ai.grounded_context([{'data':{'month':'2026-07','rows':[{'sku':'AP-001','name':'Màn hình 27 inch','quantity':50,'threshold':20}]}}])
    row=context['evidence'][0]['data']['rows'][0]
    answer='AP-001: Màn hình 27 inch trong tháng 2026-07 còn '+row['quantity']['reference']+', ngưỡng '+row['threshold']['reference']+'.'
    rendered=business_ai.render_answer(answer,context['values']);assert 'AP-001' in rendered and 'còn 50, ngưỡng 20' in rendered
    assert business_ai.render_answer('AP-001 còn 50 đơn vị, ngưỡng 20.',context['values'])=='AP-001 còn 50 đơn vị, ngưỡng 20.'
    with pytest.raises(provider.ProviderError):business_ai.render_answer('AP-001 còn 500 đơn vị, ngưỡng 20.',context['values'])
    assert business_ai.render_answer('Mã {{t1}} còn '+row['quantity']['reference']+'.',context['values']).startswith('Mã AP-001')
    for code in ['AP-0019','AP-999','XAP-001','AP-001.A']:
        with pytest.raises(provider.ProviderError):business_ai.render_answer(code+' còn '+row['quantity']['reference']+'.',context['values'])
    with pytest.raises(provider.ProviderError):business_ai.render_answer('AP-001 còn 999 đơn vị, ngưỡng '+row['threshold']['reference']+'.',context['values'])

def test_stock_analysis_can_quote_the_actual_sku_without_being_rejected(env,compatible,monkeypatch):
    client,factory,users,pid=env;login(client)
    with factory() as db:db.get(m.Inventory,pid).quantity=50;db.commit()
    def handler(request):
        context=json.loads(json.loads(request.content)['messages'][1]['content'])['context']
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'get_inventory_status','label':'Kiểm tra kho','arguments':{'query':'T01'}}]))
        row=context['evidence'][0]['data']['rows'][0]
        assert row['quantity']['value']==50 and row['threshold']['value']==20
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Sản phẩm '+row['sku']+' còn '+row['quantity']['reference']+' đơn vị, ngưỡng '+row['threshold']['reference']+'.'})))
    transport(monkeypatch,handler)
    w=create(client,'Kiểm tra tồn kho T01');execute(factory,w['id']);r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed' and r['result']['business_analysis']['status']=='completed'
    assert 'T01 còn 50 đơn vị, ngưỡng 20' in r['result']['business_analysis']['text']

def test_ai_failure_keeps_verified_calculations_and_reports_honest_status(env,compatible,monkeypatch):
    client,factory,*_=env;login(client)
    from app import agent
    monkeypatch.setattr(agent,'connected_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool='query_financial_summary',label='Tính')]),0))
    monkeypatch.setattr(business_ai,'connected_plan',lambda *a,**kw:(_ for _ in ()).throw(provider.ProviderError('Unavailable')))
    w=create(client,'Tính lợi nhuận tháng này');execute(factory,w['id'])
    r=client.get('/api/workflows/'+w['id']).json();assert r['status']=='completed'
    assert r['result']['revenue']==400000 and r['result']['business_analysis']['status']=='unavailable'

def test_denied_finance_never_sends_data_to_ai(env,compatible,monkeypatch):
    client,factory,*_=env;login(client,'Employee')
    from app import agent
    monkeypatch.setattr(agent,'connected_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool='query_financial_summary',label='Tính')]),2))
    monkeypatch.setattr(business_ai,'connected_plan',lambda *a,**kw:pytest.fail('No finance data may leave without permission'))
    w=create(client,'Tính lợi nhuận tháng này');execute(factory,w['id'])
    assert client.get('/api/workflows/'+w['id']).json()['status']=='failed'

def test_file_ai_reads_exact_saved_finance_snapshot(env,compatible,monkeypatch):
    client,factory,*_=env;login(client)
    from app import agent
    monkeypatch.setattr(agent,'connected_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool=tool,label='Tạo tệp',arguments=ToolArgs(source='finance')) for tool in ['create_word_file','create_excel_file']]),0))
    def answer(request,context,*a,**kw):
        assert context['evidence'][0]['tool']=='file_financial_snapshot'
        revenue=context['evidence'][0]['data']['revenue'];assert revenue['value']==400000
        return Plan(steps=[],clarification='Doanh thu báo cáo là '+revenue['reference']+'.'),12
    monkeypatch.setattr(business_ai,'connected_plan',answer)
    w=create(client,'Tạo Word và Excel doanh thu tháng này');execute(factory,w['id'])
    r=client.get('/api/workflows/'+w['id']).json();assert r['status']=='completed',r['error']
    assert len(r['result']['files'])==2 and r['result']['business_analysis']['status']=='completed'
