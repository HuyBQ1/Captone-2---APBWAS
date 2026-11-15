import json
import httpx
import pytest
from pydantic import SecretStr,ValidationError
from app import provider
from app.config import settings,Settings
from app.models import Workflow,User,AuditLog,Product
from app.tools import REGISTRY
from app.workflows import process
from sqlalchemy import select
from conftest import login

@pytest.fixture
def compatible(monkeypatch):
    values={'demo_mode':False,'provider':'openai_compatible','ai_model':'deepseek-v4-flash-vision',
            'ai_base_url':'https://provider.example/v1','ai_api_key':SecretStr('test-only-credential'),
            'ai_provider_label':'Intern AI / DeepSeek','ai_json_mode':True,'embedding_provider':'lexical','sample_data':True}
    for key,value in values.items():monkeypatch.setattr(settings,key,value)
    return values

def transport(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(provider.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))

def result(steps=None,content=None):
    return {'choices':[{'finish_reason':'stop','message':{'content':content if content is not None else json.dumps({'steps':steps or [
        {'tool':'get_inventory_status','label':'Kiểm tra tồn kho','arguments':{}}],'clarification':None})}}],
        'usage':{'total_tokens':321}}

def test_exact_custom_endpoint_model_and_key_stays_server_side(compatible,monkeypatch):
    def handler(request):
        assert str(request.url)=='https://provider.example/v1/chat/completions'
        assert request.headers['Authorization']=='Bearer test-only-credential'
        body=json.loads(request.content)
        assert body['model']=='deepseek-v4-flash-vision'
        assert body['response_format']=={'type':'json_object'}
        assert body['stream'] is False
        assert 'test-only-credential' not in json.dumps(body)
        return httpx.Response(200,json=result())
    transport(monkeypatch,handler)
    plan,tokens=provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY)
    assert plan.steps[0].tool=='get_inventory_status' and tokens==321
    public=provider.public_configuration()
    assert 'api_key' not in public and 'test-only-credential' not in json.dumps(public)
    assert provider.key_configured() and public['sample_data'] and not public['demo_mode']

def test_business_answer_does_not_repeat_file_creation_instructions(compatible,monkeypatch):
    def handler(request):
        body=json.loads(request.content);system=body['messages'][0]['content']
        assert 'Khi được yêu cầu tạo tệp, tạo DOCX' not in system
        assert 'context.files_created' in system
        assert json.loads(body['messages'][1]['content'])['context']['files_created'][0]['kind']=='docx'
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Doanh thu là {{v0}}.'})))
    transport(monkeypatch,handler)
    p,_=provider.connected_plan('Tạo Word',{'files_created':[{'kind':'docx','filename':'report.docx'}]}, {},agent_config={'instructions':'Khi được yêu cầu tạo tệp, tạo DOCX'},purpose='business_answer')
    assert not p.steps

def test_compact_planner_keeps_constraints_and_sends_only_tool_descriptions(compatible,monkeypatch):
    schema=provider.planner_schema()
    assert schema['$defs']['ToolArgs']['additionalProperties'] is False
    assert schema['properties']['steps']['maxItems']==12
    assert schema['$defs']['ToolArgs']['properties']['month']['anyOf'][0]['pattern']
    assert 'title' in schema['$defs']['ToolArgs']['properties']
    original=provider.Plan.model_json_schema()
    assert len(provider.compact_json(schema))<len(provider.compact_json(original))
    def handler(request):
        body=json.loads(request.content)
        prompt=body['messages'][0]['content']
        allowlist=json.loads(prompt.split('Allowlist: ',1)[1].split('\nJSON schema:',1)[0])
        assert allowlist['get_inventory_status']['description']==REGISTRY['get_inventory_status']['description']
        assert 'permission' not in allowlist['get_inventory_status']
        assert 'risk' not in allowlist['get_inventory_status']
        assert json.loads(body['messages'][1]['content'])['request']=='Kiểm tra tồn kho'
        return httpx.Response(200,json=result())
    transport(monkeypatch,handler)
    plan,_=provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY)
    assert plan.steps[0].tool=='get_inventory_status'

def test_greeting_returns_model_answer_without_tools(compatible,monkeypatch):
    def handler(request):
        body=json.loads(request.content)
        assert 'chào hỏi' in body['messages'][0]['content']
        assert 'Không bao giờ trả steps=[] cùng clarification null hoặc rỗng' in body['messages'][0]['content']
        return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Chào bạn! Tôi có thể giúp gì?'})))
    transport(monkeypatch,handler)
    plan,tokens=provider.connected_plan('chào',{},REGISTRY)
    assert not plan.steps and plan.clarification=='Chào bạn! Tôi có thể giúp gì?' and tokens==321

def test_synthesis_prose_steps_are_text_and_still_grounded():
    from app.business_ai import render_answer
    raw=json.dumps({'steps':['Nhân viên được nghỉ {{v0}} ngày mỗi tháng.'],'clarification':'Chưa có sổ phép cá nhân.'})
    answer=provider.parse_response(raw,'business_answer')
    assert not answer.steps
    assert render_answer(answer.clarification,{'v0':5},allow_prose=True).startswith('Nhân viên được nghỉ 5 ngày')
    with pytest.raises(ValidationError):provider.parse_response(raw,'plan')
    unsupported=provider.parse_response(json.dumps({'steps':['Có 99 ngày phép.'],'clarification':None}),'business_answer')
    with pytest.raises(provider.ProviderError):render_answer(unsupported.clarification,{'v0':5},allow_prose=True)
    tool=provider.parse_response(json.dumps({'steps':[{'tool':'get_inventory_status','label':'Kiểm kho','arguments':{}}],'clarification':None}),'business_answer')
    assert tool.steps  # The synthesis caller rejects tool plans as before.

def test_connection_failure_retried_once_but_read_timeout_not_replayed(compatible,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(1)
        if len(calls)==1:raise httpx.ConnectError('private connection context')
        return httpx.Response(200,json=result())
    transport(monkeypatch,handler)
    plan,_=provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY);assert len(calls)==2 and plan.steps
    calls.clear()
    class TimeoutClient:
        def post(self,*args,**kwargs):calls.append(1);raise httpx.ReadTimeout('private request context')
    with pytest.raises(provider.ProviderError,match='quá thời gian'):provider._post(TimeoutClient(),'https://provider.example/v1/chat/completions')
    assert len(calls)==1

def test_agent_configuration_applies_to_existing_provider_request(compatible,monkeypatch):
    def handler(request):
        body=json.loads(request.content)
        assert body['model']=='approved-custom-model' and body['temperature']==0.3 and body['max_tokens']==512
        assert 'Only selected knowledge' in body['messages'][0]['content']
        assert 'test-only-credential' not in json.dumps(body)
        return httpx.Response(200,json=result())
    transport(monkeypatch,handler)
    plan,tokens=provider.connected_plan('check inventory',{}, {'get_inventory_status':REGISTRY['get_inventory_status']},
        agent_config={'model':'approved-custom-model','temperature':0.3,'max_output_tokens':512,'instructions':'Only selected knowledge'})
    assert tokens==321 and plan.steps[0].tool=='get_inventory_status'

@pytest.mark.parametrize('status',[401,403,404,429,500])
def test_provider_errors_do_not_echo_upstream_credentials(compatible,monkeypatch,status):
    transport(monkeypatch,lambda request:httpx.Response(status,json={'error':'test-only-credential'}))
    with pytest.raises(provider.ProviderError) as error:provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY)
    assert 'test-only-credential' not in str(error.value)
    assert str(status) in str(error.value)

def test_invalid_plan_does_not_expose_response_or_run_tools(compatible,monkeypatch):
    transport(monkeypatch,lambda request:httpx.Response(200,json=result(content='bad response test-only-credential')))
    with pytest.raises(provider.ProviderError) as error:provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY)
    assert 'test-only-credential' not in str(error.value)

def test_no_silent_fallback_when_custom_key_missing(compatible,monkeypatch):
    monkeypatch.setattr(settings,'ai_api_key',SecretStr(''))
    monkeypatch.setattr(settings,'openai_api_key','another-provider-key')
    transport(monkeypatch,lambda request:pytest.fail('No network request is permitted without the selected provider key.'))
    with pytest.raises(provider.ProviderError,match='AI_API_KEY'):provider.connected_plan('Kiểm tra tồn kho',{},REGISTRY)
    assert not provider.key_configured()

def test_lexical_retrieval_explicit_and_compatible_with_sample_chunks(compatible,monkeypatch):
    transport(monkeypatch,lambda request:pytest.fail('Lexical search must not call a chat/embedding API.'))
    vector=provider.embed('chính sách nghỉ phép')
    assert len(vector)==384 and provider.model_id()=='demo-hash-v1-384'
    monkeypatch.setattr(settings,'embedding_provider','')
    with pytest.raises(provider.ProviderError,match='embedding riêng'):provider.embed('test')

@pytest.mark.parametrize('url',['http://provider.example/v1','https://user:password@provider.example/v1','https://provider.example/v1?key=hidden'])
def test_custom_url_requires_https_and_no_inline_credentials(url):
    with pytest.raises(ValidationError):Settings(ai_base_url=url,_env_file=None)

def test_custom_plan_cannot_bypass_employee_permissions(env,compatible,monkeypatch):
    client,factory,users,product=env
    transport(monkeypatch,lambda request:httpx.Response(200,json=result(steps=[{'tool':'query_sales','label':'Query','arguments':{}}])))
    with factory() as db:
        wf=Workflow(user_id=users['Employee'],request='Phân tích doanh thu',idempotency_key='provider-rbac-check')
        db.add(wf);db.commit();process(db,wf)
        assert wf.status=='failed' and wf.checkpoint==0
        assert db.scalar(select(AuditLog).where(AuditLog.event=='workflow.failed'))

def test_admin_metadata_does_not_expose_key(env,compatible):
    client,_,_,_=env;login(client,'Admin')
    config=client.get('/api/admin/settings').json()
    assert config['key_configured'] and config['model']=='deepseek-v4-flash-vision'
    assert config['embedding_provider']=='lexical'
    assert 'test-only-credential' not in json.dumps(config)


def test_product_planner_sees_no_catalog_then_analysis_receives_authorized_result(env,compatible,monkeypatch):
    _,factory,users,product_id=env
    def handler(request):
        body=json.loads(request.content)
        prompt=body['messages'][0]['content']
        context=json.loads(body['messages'][1]['content'])['context']
        if 'evidence' in context:
            price=context['evidence'][0]['data']['products'][0]['price']
            assert price['value']==987654
            return httpx.Response(200,json=result(content=json.dumps({'steps':[],'clarification':'Giá bán hiện tại là '+price['reference']+' ₫.'})))
        assert 'lookup_products' in prompt and 'Giá bán/SKU' in prompt
        assert '987654' not in json.dumps(body)
        return httpx.Response(200,json=result(steps=[{'tool':'lookup_products','label':'Tra giá',
                                                    'arguments':{'query':'T01'}}]))
    transport(monkeypatch,handler)
    with factory() as db:
        db.get(Product,product_id).price=987654
        db.commit()
        wf=Workflow(user_id=users['Manager'],request='Giá sản phẩm SKU T01 là bao nhiêu?',idempotency_key='provider-product-price')
        db.add(wf);db.commit();process(db,wf)
        assert wf.status=='completed', wf.error
        assert wf.result['products'][0]['id']==product_id
        assert '987.654 ₫' in wf.result['summary']


@pytest.mark.parametrize('embedding',[None,[0.0]*383,[float('nan')]*384,['not-a-number']*384])
def test_invalid_embedding_is_rejected_without_database_error(compatible,monkeypatch,embedding):
    monkeypatch.setattr(settings,'embedding_provider','openai')
    monkeypatch.setattr(settings,'openai_api_key','test-only-key')
    # JSON cannot carry NaN in a real response, but malformed number vectors
    # are tested directly by substituting the parsed provider response.
    monkeypatch.setattr(provider,'_post',lambda *args,**kwargs:{'data':[{'embedding':embedding}]})
    with pytest.raises(provider.ProviderError):provider.embed('test')
