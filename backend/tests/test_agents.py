import copy,uuid
from sqlalchemy import select
from conftest import login,execute
from app import models as m
from app.config import settings
from app.audit import verify

def body(tools=None,**kw):
    tools=tools or ['query_financial_summary']
    return {'name':'Finance Agent','description':'Monthly operational finance','visibility':'private','config':{
        'model':settings.ai_model,'instructions':'Trả lời dựa trên dữ liệu được phép.','tools':tools,
        'permissions':['inventory.read','sales.read'] if 'query_financial_summary' in tools else ['inventory.read']},**kw}

def create_agent(client,payload=None):
    response=client.post('/api/agents',json=payload or body());assert response.status_code==201,response.text
    return response.json()

def start(client,a,request='Tính lời lỗ 07/2026',draft=False):
    response=client.post(f"/api/agents/{a['id']}/"+('playground' if draft else 'runs'),json={
        'request':request,'idempotency_key':str(uuid.uuid4()),**({'revision':a['revision']} if draft else {})})
    assert response.status_code==202,response.text
    return response.json()

def test_slash_available_uses_published_snapshot_permissions_and_search(env):
    client,factory,users,*_=env;login(client)
    finance=create_agent(client,body(name='Phân tích tài chính',visibility='workspace'))
    inventory=create_agent(client,body(['get_inventory_status'],name='Tra cứu tồn kho',visibility='workspace'))
    private=create_agent(client,body(['get_inventory_status'],name='Private inventory'))
    for a in (finance,inventory,private):assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    draft=create_agent(client,body(name='Unpublished Agent'))
    assert client.put('/api/agents/'+finance['id'],json=body(name='Secret draft name',visibility='workspace',revision=1)).status_code==200
    available=client.get('/api/agents/available?q=tai%20chinh').json()['items']
    assert [a['name'] for a in available]==['Phân tích tài chính'] and available[0]['published_version']==1
    assert not client.get('/api/agents/available?q=Secret').json()['items']
    assert draft['id'] not in {a['id'] for a in client.get('/api/agents/available').json()['items']}
    login(client,'Employee')
    assert [a['id'] for a in client.get('/api/agents/available').json()['items']]==[inventory['id']]
    login(client);client.post('/api/agents/'+inventory['id']+'/archive')
    login(client,'Employee');assert not client.get('/api/agents/available').json()['items']

def test_agent_chat_continues_own_conversation_without_mixing_agents(env):
    client,factory,users,*_=env;login(client)
    a=create_agent(client,body(['get_inventory_status'],visibility='workspace'))
    assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    one=start(client,a,request='Kiểm tra tồn kho');execute(factory,one['id'])
    payload={'request':'Kiểm tra tồn kho lần nữa','idempotency_key':str(uuid.uuid4()),'conversation_id':one['conversation_id'],'version':1}
    response=client.post('/api/agents/'+a['id']+'/runs',json=payload);assert response.status_code==202,response.text
    two=response.json();assert two['conversation_id']==one['conversation_id']
    assert client.post('/api/agents/'+a['id']+'/runs',json=payload).json()['id']==two['id']
    execute(factory,two['id'])
    with factory() as db:
        workflows=list(db.scalars(select(m.Workflow).where(m.Workflow.conversation_id==one['conversation_id'])))
        assert len(workflows)==2 and all(w.agent_id==a['id'] and w.agent_version_id for w in workflows)
        assert all(w.status=='completed' for w in workflows)
    another=create_agent(client,body(['get_inventory_status'],name='Other inventory'))
    client.post('/api/agents/'+another['id']+'/publish',json={'revision':1})
    assert client.post('/api/agents/'+another['id']+'/runs',json={**payload,'idempotency_key':str(uuid.uuid4())}).status_code==409
    login(client,'Employee')
    assert client.post('/api/agents/'+a['id']+'/runs',json={**payload,'idempotency_key':str(uuid.uuid4())}).status_code==404

def test_publish_pins_snapshot_restore_and_run_history(env):
    client,factory,users,pid=env;login(client)
    a=create_agent(client);id=a['id']
    assert client.post(f'/api/agents/{id}/publish',json={'revision':1}).status_code==200
    run=start(client,a)
    changed=body(['lookup_products'],revision=1,name='Updated draft')
    changed['config']['instructions']='New instructions'
    updated=client.put(f'/api/agents/{id}',json=changed).json();assert updated['revision']==2
    assert client.put(f'/api/agents/{id}',json=changed).status_code==409
    execute(factory,run['id'])
    result=client.get('/api/workflows/'+run['id']).json()
    assert result['status']=='completed' and result['plan'][0]['tool']=='query_financial_summary'
    assert result['agent_version_id'] and 'agent_snapshot' not in result
    assert client.post(f'/api/agents/{id}/publish',json={'revision':2}).status_code==200
    versions=client.get(f'/api/agents/{id}/versions').json()['items'];assert [v['number'] for v in versions]==[2,1]
    assert versions[1]['snapshot']['instructions']!='New instructions'
    diff=client.get(f'/api/agents/{id}/versions/1/compare').json();assert any(c['field']=='tools' for c in diff['changes'])
    restored=client.post(f'/api/agents/{id}/versions/1/restore',json={'revision':2})
    assert restored.status_code==200,restored.text
    assert restored.json()['revision']==3 and restored.json()['published_version']==2
    assert [d['revision'] for d in client.get(f'/api/agents/{id}/versions').json()['drafts']]==[3,2,1]
    assert client.post(f'/api/agents/{id}/drafts/2/restore',json={'revision':3}).status_code==200
    history=client.get(f'/api/agents/{id}/runs').json()['items'];assert history[0]['result']=={} and history[0]['plan']==[]
    with factory() as db:
        wf=db.get(m.Workflow,run['id']);assert wf.agent_snapshot['name']=='Finance Agent'
        assert db.get(m.AgentConfig,id).config['tools']==['lookup_products'];assert verify(db)

def test_config_validation_and_no_privilege_escalation(env):
    client,*_=env;login(client,'Employee');assert client.post('/api/agents',json=body()).status_code==403
    login(client)
    for key,value in [('model','https://evil.test'),('tools',['apply_approved_inventory_adjustment']),('permissions',['users.manage']),('instructions','api_key=sk-testsecret123456789012345')]:
        payload=body();payload['config'][key]=value
        assert client.post('/api/agents',json=payload).status_code in (403,422)
    payload=body();payload['config']['api_key']='secret';assert client.post('/api/agents',json=payload).status_code==422
    payload=body();payload['config']['permissions']=[];assert client.post('/api/agents',json=payload).status_code==422

def test_workspace_isolation_private_agents_and_shared_current_permissions(env):
    client,factory,users,pid=env;login(client)
    a=create_agent(client,body(['get_inventory_status']));id=a['id']
    login(client,'Employee');assert client.get('/api/agents/'+id).status_code==404
    assert client.get('/api/agents').json()['total']==0
    login(client)
    payload=body(['get_inventory_status'],visibility='workspace',revision=1)
    assert client.put('/api/agents/'+id,json=payload).status_code==200
    assert client.post(f'/api/agents/{id}/publish',json={'revision':2}).status_code==200
    login(client,'Employee');assert 'config' not in client.get('/api/agents/'+id).json()
    run=start(client,a,'Kiểm tra tồn kho');execute(factory,run['id'])
    assert client.get('/api/workflows/'+run['id']).json()['status']=='completed'
    with factory() as db:
        db.add(m.Workspace(id='other',name='Other workspace'));db.flush()
        db.get(m.User,users['Employee']).workspace_id='other';db.commit()
    assert client.get('/api/agents/'+id).status_code==404
    assert client.get('/api/workflows/'+run['id']).status_code==404
    assert all(r['id']!=run['id'] for r in client.get('/api/workflows').json()['items'])

def test_draft_run_tool_allowlist_revocation_and_archiving(env):
    client,factory,users,pid=env;login(client)
    a=create_agent(client,body(['lookup_products']));run=start(client,a,draft=True)
    execute(factory,run['id']);assert client.get('/api/workflows/'+run['id']).json()['status']=='failed'
    assert client.post(f"/api/agents/{a['id']}/publish",json={'revision':1}).status_code==200
    run=start(client,a,'Giá Test product');
    with factory() as db:
        role=db.get(m.Role,'Manager');role.permissions=[p for p in role.permissions if p!='inventory.read'];db.commit()
    execute(factory,run['id'])
    with factory() as db:assert db.get(m.Workflow,run['id']).status=='failed'
    login(client,'Admin');assert client.post(f"/api/agents/{a['id']}/archive").status_code==200
    assert client.post(f"/api/agents/{a['id']}/runs",json={'request':'price Test','idempotency_key':str(uuid.uuid4())}).status_code==409

def test_knowledge_attachment_limits_rag_and_scope(env):
    client,factory,users,pid=env
    from app.retrieval import index_document
    with factory() as db:
        docs=[]
        for title in ['Attached','Not attached']:
            doc=m.Document(user_id=users['Manager'],name=title,scope='all',content='Chính sách nghỉ phép năm dành cho nhân viên có quy trình đăng ký.');db.add(doc);db.commit();index_document(db,doc);docs.append(doc.id)
        private=m.Document(user_id=users['Admin'],name='Secret',scope='Admin',status='indexed',content='secret');db.add(private);db.commit();private_id=private.id
    login(client)
    payload=body(['search_internal_documents']);payload['config']['permissions']=['documents.read'];payload['config']['knowledge_ids']=[private_id]
    assert client.post('/api/agents',json=payload).status_code==403
    payload['config']['knowledge_ids']=[docs[0]];a=create_agent(client,payload)
    run=start(client,a,'Tóm tắt chính sách nghỉ phép',True);execute(factory,run['id'])
    result=client.get('/api/workflows/'+run['id']).json()
    assert result['status']=='completed' and result['result']['sources']
    assert {s['document_id'] for s in result['result']['sources']}=={docs[0]}
    with factory() as db:db.get(m.Document,docs[0]).scope='Admin';db.commit()
    assert client.get('/api/workflows/'+run['id']).status_code==403

def test_duplicate_soft_delete_and_idempotent_enqueue(env):
    client,factory,*_=env;login(client)
    a=create_agent(client);id=a['id'];assert client.post(f'/api/agents/{id}/publish',json={'revision':1}).status_code==200
    duplicate=client.post(f'/api/agents/{id}/duplicate').json()
    assert duplicate['id']!=id and duplicate['published_version'] is None and duplicate['visibility']=='private'
    payload={'request':'Tính lời lỗ 2026-07','idempotency_key':str(uuid.uuid4())}
    one=client.post(f'/api/agents/{id}/runs',json=payload);two=client.post(f'/api/agents/{id}/runs',json=payload)
    assert one.json()['id']==two.json()['id']
    assert client.delete('/api/agents/'+id).status_code==200
    assert client.get('/api/agents/'+id).status_code==404
    with factory() as db:assert db.get(m.Agent,id).status=='deleted' and db.get(m.Workflow,one.json()['id']).agent_version_id

def test_agent_sensitive_tool_keeps_approval_and_rechecks_archive(env):
    client,factory,users,pid=env;login(client)
    payload=body(['get_inventory_status','propose_inventory_adjustment']);payload['config']['permissions']=['inventory.read','inventory.propose']
    a=create_agent(client,payload);run=start(client,a,f'Đề xuất điều chỉnh tồn kho product_id={pid} quantity=50',True)
    execute(factory,run['id']);wf=client.get('/api/workflows/'+run['id']).json();assert wf['status']=='waiting_approval'
    with factory() as db:assert db.get(m.Inventory,pid).quantity==10
    assert client.post(f"/api/agents/{a['id']}/archive").status_code==200
    decision=client.post('/api/approvals/'+wf['result']['approval_id']+'/decision',json={'decision':'approved','revision':1})
    assert decision.status_code==403
    with factory() as db:assert db.get(m.Inventory,pid).quantity==10

def test_agent_limits_record_consumed_tokens_and_stop_before_tools(env,monkeypatch):
    client,factory,*_=env;login(client)
    payload=body();payload['config']['token_budget']=6000
    a=create_agent(client,payload);run=start(client,a,draft=True)
    from app import workflows
    from app.schemas import Plan,PlanStep
    monkeypatch.setattr(workflows,'make_plan',lambda *args,**kw:(Plan(steps=[PlanStep(tool='query_financial_summary',label='Finance')]),6001))
    execute(factory,run['id'])
    with factory() as db:
        assert db.get(m.Workflow,run['id']).status=='failed'
        assert db.scalar(select(m.UsageRecord).where(m.UsageRecord.workflow_id==run['id'])).tokens==6001
        assert list(db.scalars(select(m.ToolExecution).where(m.ToolExecution.workflow_id==run['id'])))==[]

def test_agent_example_seed_creates_published_configs_without_running_ai(env,monkeypatch):
    _,factory,*_=env
    from app import seed_agents
    monkeypatch.setattr(seed_agents,'Session',factory)
    result=seed_agents.seed();assert len(result['agent_ids'])==2
    assert seed_agents.seed()==result
    with factory() as db:
        for id in result['agent_ids']:
            assert db.get(m.Agent,id).status=='published'
            assert db.get(m.AgentDraftRevision,(id,1))
