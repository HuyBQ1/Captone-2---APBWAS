import json,uuid
import httpx,pytest
from sqlalchemy import select
from conftest import login,create,execute
from test_provider import compatible,transport,result
from app import models as m,agent,business_ai,retrieval
from app.schemas import Plan,PlanStep
from app.provider import ProviderError

def test_company_question_uses_configured_profile_and_synthesizes_short_answer(env,compatible,monkeypatch):
    client,factory,*_=env;login(client)
    with factory() as db:db.add(m.SystemSetting(key='company',value={'name':'Acme Commerce','email':'hello@acme.example','address':'','tax_code':''}));db.commit()
    calls=[]
    def handler(request):
        payload=json.loads(json.loads(request.content)['messages'][1]['content']);calls.append(payload)
        context=payload['context']
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'get_company_profile','label':'Đọc hồ sơ công ty','arguments':{}}]))
        assert context['evidence'][0]['data']['company_profile']['name']=='Acme Commerce'
        assert context['evidence'][0]['data']['sample_data'] is True
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Bạn đang làm việc tại Acme Commerce. Hệ thống hiện sử dụng dữ liệu mẫu; hồ sơ chưa có thông tin pháp lý đầy đủ.'})))
    transport(monkeypatch,handler)
    w=create(client,'đây là công ty gì');execute(factory,w['id']);r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed',r['error']
    assert r['result']['business_analysis']['answer_kind']=='sourced_text'
    assert r['result']['summary'].startswith('Bạn đang làm việc tại Acme Commerce.')
    assert 'Họ tên và ký' not in r['result']['summary'] and len(calls)==2

def test_rag_answers_question_without_dumping_raw_document_or_losing_sources(env,compatible,monkeypatch):
    client,factory,users,*_=env;login(client)
    content='Nhân viên được nghỉ phép 12 ngày mỗi năm.\nKiểm soát tài liệu: Họ tên và ký __________. '+('Đầu chân trang lặp. '*50)
    with factory() as db:
        d=m.Document(user_id=users['Manager'],name='Chính sách nghỉ phép',scope='all',status='indexed',content=content);db.add(d);db.commit();did=d.id
    source={'document_id':did,'chunk_id':'chunk-one','name':'Chính sách nghỉ phép','content':content,'page':1,'score':.8}
    monkeypatch.setattr(retrieval,'search',lambda *a,**kw:[source])
    def handler(request):
        context=json.loads(json.loads(request.content)['messages'][1]['content'])['context']
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'search_internal_documents','label':'Tìm chính sách','arguments':{'query':'nghỉ phép'}}]))
        assert 'Nhân viên được nghỉ phép 12 ngày' in context['evidence'][0]['data']['sources'][0]['content']
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Theo chính sách nghỉ phép, nhân viên được nghỉ {{d0}} ngày mỗi năm.'})))
    transport(monkeypatch,handler)
    w=create(client,'Nhân viên được phép nghỉ bao nhiêu ngày trong năm?');execute(factory,w['id']);r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed',r['error']
    assert r['result']['summary']=='Theo chính sách nghỉ phép, nhân viên được nghỉ 12 ngày mỗi năm.'
    assert r['result']['sources'][0]['document_id']==did and 'Họ tên và ký' not in r['result']['summary']

def test_source_permission_is_rechecked_before_sending_document_to_synthesis(env,compatible,monkeypatch):
    client,factory,users,*_=env;login(client,'Employee')
    with factory() as db:
        d=m.Document(user_id=users['Manager'],name='Restricted',scope='Manager',status='indexed',content='Secret');db.add(d);db.commit();did=d.id
    monkeypatch.setattr(agent,'connected_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool='search_internal_documents',label='Search')]),1))
    monkeypatch.setattr(retrieval,'search',lambda *a,**kw:[{'document_id':did,'name':'Restricted','content':'Secret'}])
    monkeypatch.setattr(business_ai,'connected_plan',lambda *a,**kw:pytest.fail('Restricted content must not be sent to the model'))
    w=create(client,'Tìm chính sách nội bộ');execute(factory,w['id'])
    with factory() as db:assert db.get(m.Workflow,w['id']).status=='failed'

def test_other_workspace_company_tool_cannot_read_primary_profile(env):
    from app.tools import run_tool
    client,factory,users,*_=env
    with factory() as db:
        db.add(m.SystemSetting(key='company',value={'name':'Primary Secret','tax_code':'123456'}));db.add(m.Workspace(id='other',name='Other company'))
        u=db.get(m.User,users['Manager']);u.workspace_id='other';db.flush()
        w=m.Workflow(user_id=u.id,request='Company',idempotency_key=str(uuid.uuid4()));db.add(w);db.flush()
        output=run_tool(db,u,w,{'tool':'get_company_profile','arguments':{}})
        assert output['company_profile']=={'name':'Other company'} and output['categories']==[]

def test_plain_sourced_answer_does_not_require_artificial_numeric_references():
    assert business_ai.render_answer('Đây là Acme Commerce.',{},allow_prose=True)=='Đây là Acme Commerce.'
    with pytest.raises(ProviderError):business_ai.render_answer('Công ty có 999 nhân viên.',{},allow_prose=True)

def test_document_codes_citations_and_list_ordinals_do_not_block_honest_missing_policy():
    context=business_ai.grounded_context([{'data':{'sources':[{'name':'[NC-HR-002] Quy trình đăng ký nghỉ.docx','content':'Quyền lợi và số ngày nghỉ theo chính sách chính thức; không suy từ quy trình này.'}]}}])
    text='1. Tài liệu NC-HR-002 chỉ hướng dẫn đăng ký nghỉ [1].\n2. Chưa có chính sách xác định số ngày được nghỉ.'
    assert business_ai.render_answer(text,context['values'],allow_prose=True,citation_count=1)==text
    with pytest.raises(ProviderError):business_ai.render_answer('Nhân viên được nghỉ 12 ngày.',context['values'],allow_prose=True)

def test_empty_knowledge_is_sent_to_model_and_gets_an_honest_ai_answer(env,compatible,monkeypatch):
    client,factory,*_=env;login(client);monkeypatch.setattr(retrieval,'search',lambda *a,**kw:[])
    def handler(request):
        context=json.loads(json.loads(request.content)['messages'][1]['content'])['context']
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'search_internal_documents','label':'Tìm chính sách','arguments':{'query':'nghỉ phép'}}]))
        assert context['evidence'][0]['data']['no_matches']
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Kho tri thức chưa có chính sách xác định số ngày nghỉ phép của công ty. Bạn cần bổ sung chính sách nhân sự đã ban hành để tôi trả lời chính xác.'})))
    transport(monkeypatch,handler);w=create(client,'Nhân viên được phép nghỉ bao nhiêu ngày?');execute(factory,w['id']);r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed' and r['result']['summary'].startswith('Kho tri thức chưa có chính sách')

def test_ai_repairs_an_unsupported_leave_number_once_instead_of_exposing_validator_error(env,compatible,monkeypatch):
    client,factory,*_=env;login(client);monkeypatch.setattr(retrieval,'search',lambda *a,**kw:[]);calls=[]
    def handler(request):
        context=json.loads(json.loads(request.content)['messages'][1]['content'])['context'];calls.append(context)
        if 'evidence' not in context:return httpx.Response(200,json=result(steps=[{'tool':'search_internal_documents','label':'Tìm chính sách','arguments':{}}]))
        if 'validation_feedback' not in context:return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Nhân viên được nghỉ 12 ngày.'})))
        assert context['evidence'][0]['data']['no_matches']
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Chưa có chính sách xác định số ngày nghỉ phép của công ty trong kho tri thức.'})))
    transport(monkeypatch,handler);w=create(client,'Được nghỉ bao nhiêu ngày?');execute(factory,w['id']);r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed' and r['result']['summary'].startswith('Chưa có chính sách') and len(calls)==3
    assert r['tokens']==963
