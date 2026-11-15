import json,uuid
import httpx,pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from conftest import login,create,execute
from app import llm_models as llm,models as m
from app.config import settings
from test_agents import body,create_agent
HTTP_CLIENT=httpx.Client

@pytest.fixture
def vault(monkeypatch):
    monkeypatch.setattr(settings,'llm_encryption_key',SecretStr(Fernet.generate_key().decode()))

def payload(**kwargs):
    return {'name':'Alternative LLM','base_url':'https://provider.example/v1','api_key':'private-model-key',
            'model_ids':['model-one','model-two'],'allowed_roles':['Admin','Manager'],**kwargs}

def add(client,**kwargs):
    r=client.post('/api/llm/providers',json=payload(**kwargs));assert r.status_code==201,r.text;return r.json()

def patch(client,p,**kwargs):return client.put('/api/llm/providers/'+p['id'],json=payload(api_key='',revision=p['revision'],**kwargs))

def transport(monkeypatch,handler):
    monkeypatch.setattr(llm.httpx,'Client',lambda **kwargs:HTTP_CLIENT(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setattr(llm,'public_host',lambda base:None)

def test_llm_keys_encrypted_admin_only_and_catalog_role_scoped(env,vault):
    client,factory,users,*_=env;login(client)
    assert client.get('/api/llm/providers').status_code==403
    assert client.post('/api/llm/providers',json=payload()).status_code==403
    login(client,'Admin');p=add(client)
    assert 'private-model-key' not in json.dumps(p)
    with factory() as db:
        row=db.get(m.LLMProvider,p['id']);assert 'private-model-key' not in row.api_key_ciphertext
        assert llm.reveal(row.api_key_ciphertext)=='private-model-key'
        assert 'private-model-key' not in json.dumps([a.payload for a in db.scalars(select(m.AuditLog))])
    assert client.get('/api/llm/providers').json()['items'][0]['key_configured']
    login(client);models=client.get('/api/llm/models').json()['items'];assert any(x['id']==f"llm:{p['id']}:model-two" for x in models)
    login(client,'Employee');assert not any(x['source']=='database' for x in client.get('/api/llm/models').json()['items'])
    with factory() as db:
        db.add(m.Workspace(id='other',name='Other'));db.commit();db.get(m.User,users['Manager']).workspace_id='other';db.commit()
    login(client);assert not any(x['source']=='database' for x in client.get('/api/llm/models').json()['items'])
    wf=create(client,'tra giá',None)
    with factory() as db:assert db.get(m.Workflow,wf['id']).model_ref is None

@pytest.mark.parametrize('url',['http://provider.example/v1','https://localhost/v1','https://127.0.0.1/v1','https://10.0.0.1/v1','https://user:key@provider.example/v1','https://provider.example/v1?key=secret','https://provider.example:8443/v1'])
def test_llm_rejects_private_or_credential_urls(env,vault,url):
    client,*_=env;login(client,'Admin');r=client.post('/api/llm/providers',json=payload(base_url=url));assert r.status_code==422
    assert 'private-model-key' not in r.text

def test_dns_private_network_is_blocked(monkeypatch):
    monkeypatch.setattr(llm.socket,'getaddrinfo',lambda *a,**kw:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(__import__('fastapi').HTTPException) as e:llm.public_host('https://provider.example/v1')
    assert e.value.status_code==422

def test_llm_revision_fixed_endpoint_rotation_and_disable(env,vault):
    client,factory,*_=env;login(client,'Admin');p=add(client)
    assert patch(client,p,base_url='https://other.example/v1').status_code==422
    r=patch(client,p,name='Updated connection');assert r.status_code==200
    assert patch(client,p,name='Stale').status_code==409
    p=r.json();r=client.put('/api/llm/providers/'+p['id'],json=payload(revision=p['revision'],api_key='rotated-private-key',enabled=False));assert r.status_code==200
    with factory() as db:assert llm.reveal(db.get(m.LLMProvider,p['id']).api_key_ciphertext)=='rotated-private-key'
    login(client);assert not any(i['source']=='database' for i in client.get('/api/llm/models').json()['items'])
    r=client.post('/api/workflows',json={'request':'tra giá sản phẩm','model':f"llm:{p['id']}:model-one",'idempotency_key':str(uuid.uuid4())});assert r.status_code==403

def test_discovery_and_explicit_connection_test_use_only_fixed_payload(env,vault,monkeypatch):
    client,factory,*_=env;login(client,'Admin');p=add(client);calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers['authorization']=='Bearer private-model-key'
        if request.method=='GET':
            assert str(request.url)=='https://provider.example/v1/models'
            return httpx.Response(200,json={'data':[{'id':'model-one'},{'id':'another-model'}]})
        assert str(request.url)=='https://provider.example/v1/chat/completions'
        data=json.loads(request.content);assert data['model']=='model-one'
        assert 'private-model-key' not in json.dumps(data) and 'doanh thu' not in json.dumps(data)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"steps":[],"clarification":"OK"}'}}]})
    transport(monkeypatch,handler)
    assert client.post('/api/llm/providers/'+p['id']+'/discover').json()['items']==['another-model','model-one']
    endpoint='/api/llm/providers/'+p['id']+'/test'
    assert client.post(endpoint,json={'model_id':'model-one','confirmed':False}).status_code==422 and len(calls)==1
    assert client.post(endpoint,json={'model_id':'model-one','confirmed':True}).json()['ok']
    with factory() as db:assert db.get(m.LLMProvider,p['id']).last_test_status=='passed'

def test_selected_custom_chat_model_routes_to_its_provider_without_persisting_key(env,vault,monkeypatch):
    client,factory,users,*_=env;login(client,'Admin');p=add(client)
    ref=f"llm:{p['id']}:model-two";login(client)
    monkeypatch.setattr(settings,'demo_mode',False)
    seen=[]
    def handler(request):
        assert str(request.url)=='https://provider.example/v1/chat/completions'
        assert request.headers['authorization']=='Bearer private-model-key'
        data=json.loads(request.content);assert data['model']=='model-two';seen.append(data)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"steps":[{"tool":"get_inventory_status","label":"Stock","arguments":{}}]}'}}],'usage':{'total_tokens':24}})
    transport(monkeypatch,handler)
    key=str(uuid.uuid4());r=client.post('/api/workflows',json={'request':'Kiểm tra tồn kho','model':ref,'idempotency_key':key});assert r.status_code==202,r.text
    execute(factory,r.json()['id'])
    w=client.get('/api/workflows/'+r.json()['id']).json();assert w['status']=='completed',w['error'];assert w['model_ref']==ref and w['tokens']==48
    with factory() as db:
        assert 'private-model-key' not in json.dumps(db.get(m.Workflow,w['id']).plan)
        assert 'private-model-key' not in json.dumps([a.payload for a in db.scalars(select(m.AuditLog))])
    assert client.post('/api/workflows',json={'request':'Kiểm tra tồn kho','model':settings.ai_model,'idempotency_key':key}).status_code==409
    assert len(seen)==2

def test_custom_agent_model_is_workspace_scoped_and_rechecked_before_execution(env,vault,monkeypatch):
    client,factory,users,*_=env;login(client,'Admin');p=add(client);login(client)
    config=body(['get_inventory_status']);config['config']['model']=f"llm:{p['id']}:model-one"
    a=create_agent(client,config);assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    run=client.post('/api/agents/'+a['id']+'/runs',json={'request':'Kiểm tra tồn kho','idempotency_key':str(uuid.uuid4())}).json()
    login(client,'Admin');assert patch(client,p,enabled=False).status_code==200
    transport(monkeypatch,lambda r:pytest.fail('Disabled provider must not be called'))
    execute(factory,run['id'])
    with factory() as db:
        w=db.get(m.Workflow,run['id']);assert w.status=='failed' and 'Model' in w.error
