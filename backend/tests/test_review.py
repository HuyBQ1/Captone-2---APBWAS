import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Role, User, Workflow, Approval, Message, Product, Inventory, SystemSetting, UsageRecord, WorkflowStep, Report
from app.tools import run_tool
from app.schemas import Plan, PlanStep, ToolArgs, Decision
from app.approvals import decide
from app import workflows
from conftest import login, create, execute


def test_historical_conversation_and_idempotent_response_recheck_permissions(env):
    client,factory,users,_=env;login(client)
    wf=create(client,'Phân tích doanh thu tháng này')
    execute(factory,wf['id'])
    with factory() as db:
        item=db.get(Workflow,wf['id']);key=item.idempotency_key
        db.get(Role,'Manager').permissions=['inventory.read','documents.read','audit.read']
        db.commit()
    assert client.get('/api/workflows/'+wf['id']).status_code==403
    assert client.get('/api/conversations/'+wf['conversation_id']).status_code==403
    response=client.post('/api/workflows',json={'request':'Phân tích doanh thu tháng này','idempotency_key':key})
    assert response.status_code==403
    log=client.get('/api/audit').json()
    assert all('total' not in str(row['payload']) for row in log['items'])


def test_cached_role_and_tool_toggle_cannot_override_revocation(env):
    _,factory,users,_=env
    step={'tool':'get_inventory_status','arguments':{}}
    with factory() as worker:
        user=worker.get(User,users['Manager'])
        role=worker.get(Role,'Manager')
        assert role.permissions
        with factory() as admin:
            admin.get(Role,'Manager').permissions=['documents.read'];admin.commit()
        with pytest.raises(HTTPException):run_tool(worker,user,None,step)
    with factory() as admin:
        admin.get(Role,'Manager').permissions=['inventory.read']
        admin.add(SystemSetting(key='tools',value={'get_inventory_status':True}));admin.commit()
    with factory() as worker:
        toggle=worker.get(SystemSetting,'tools');assert toggle.value['get_inventory_status']
        with factory() as admin:
            admin.get(SystemSetting,'tools').value={'get_inventory_status':False};admin.commit()
        with pytest.raises(ValueError,match='tắt'):run_tool(worker,worker.get(User,users['Manager']),None,step)


def test_proposal_must_be_last_before_any_tool_executes(env,monkeypatch):
    client,factory,_,product=env;login(client)
    plan=Plan(steps=[PlanStep(tool='propose_inventory_adjustment',label='Propose',arguments=ToolArgs(product_id=product,quantity=40)),
                     PlanStep(tool='get_inventory_status',label='Read')])
    monkeypatch.setattr(workflows,'make_plan',lambda *args,**kwargs:(plan,0))
    wf=create(client,'Đề xuất thay đổi rồi kiểm tra')
    execute(factory,wf['id'])
    with factory() as db:
        item=db.get(Workflow,wf['id'])
        assert item.status=='failed' and item.checkpoint==0
        assert db.scalar(select(Approval).where(Approval.workflow_id==item.id)) is None
        assert db.get(Inventory,product).quantity==10


def test_approval_completion_is_added_to_conversation(env):
    client,factory,users,product=env;login(client)
    wf=create(client,f'Đề xuất điều chỉnh tồn kho product_id={product} quantity=40')
    execute(factory,wf['id'])
    with factory() as db:
        approval=db.scalar(select(Approval).where(Approval.workflow_id==wf['id']))
        decide(db,db.get(User,users['Manager']),approval.id,Decision(decision='approved',revision=1))
    response=client.get('/api/conversations/'+wf['conversation_id'])
    assert response.status_code==200
    assert any('Đã cập nhật tồn kho' in m['content'] for m in response.json()['messages'] if m['role']=='assistant')


def test_inventory_filters_sku_and_returns_actual_quantity(env):
    _,factory,users,product=env
    with factory() as db:
        other=Product(sku='OTHER',name='Other item',category='Other',price=2000);db.add(other);db.flush()
        db.add(Inventory(product_id=other.id,quantity=500,threshold=5));db.commit()
        output=run_tool(db,db.get(User,users['Manager']),None,{'tool':'get_inventory_status','arguments':{'query':'T01'}})
        assert len(output['rows'])==1 and output['rows'][0]['id']==product
        assert '10' in output['summary'] and 'T01' in output['summary']
        assert not output.get('truncated')


def test_business_search_accepts_sku(env):
    client,_,_,_=env;login(client)
    response=client.get('/api/data/products?q=T01')
    assert response.status_code==200 and response.json()['total']==1


def test_deleted_document_sources_are_no_longer_disclosed(env):
    client,factory,users,_=env;login(client)
    with factory() as db:
        wf=Workflow(user_id=users['Manager'],request='Policy',idempotency_key=uuid.uuid4().hex,
                    plan=[{'tool':'search_internal_documents','label':'Search','arguments':{}}],
                    result={'sources':[{'document_id':str(uuid.uuid4()),'content':'deleted private content'}]})
        db.add(wf);db.commit();wid=wf.id
    assert client.get('/api/workflows/'+wid).status_code==403


def test_tokens_are_charged_when_valid_model_plan_is_denied(env,monkeypatch):
    client,factory,users,_=env;login(client,'Employee')
    monkeypatch.setattr(workflows,'make_plan',lambda *args,**kwargs:(Plan(steps=[PlanStep(tool='query_sales',label='Read revenue')]),321))
    wf=create(client,'Đọc doanh thu')
    execute(factory,wf['id'])
    with factory() as db:
        assert db.get(Workflow,wf['id']).status=='failed'
        assert db.scalar(select(UsageRecord).where(UsageRecord.workflow_id==wf['id'])).tokens==321


def test_tool_failure_updates_step_without_exposing_internal_error(env,monkeypatch):
    client,factory,_,_=env;login(client)
    def broken(*args):raise RuntimeError('private-internal-detail')
    monkeypatch.setattr(workflows,'run_tool',broken)
    wf=create(client,'Kiểm tra tồn kho')
    execute(factory,wf['id'])
    with factory() as db:
        item=db.get(Workflow,wf['id'])
        step=db.scalar(select(WorkflowStep).where(WorkflowStep.workflow_id==wf['id']))
        assert item.status=='failed' and step.status=='failed'
        assert 'private-internal-detail' not in item.error


def test_recovered_plan_gets_a_new_deadline(env):
    _,factory,users,_=env
    with factory() as db:
        wf=Workflow(user_id=users['Manager'],request='Retry test',idempotency_key=uuid.uuid4().hex,
                    plan=[PlanStep(tool='get_inventory_status',label='Read inventory').model_dump()])
        db.add(wf);db.flush();db.add(WorkflowStep(workflow_id=wf.id,position=0,tool='get_inventory_status'));db.commit()
        workflows.process(db,wf)
        assert wf.status=='completed' and wf.deadline is not None


def test_stock_warning_excludes_healthy_products(env):
    _,factory,users,_=env
    with factory() as db:
        p=Product(sku='HEALTHY',name='Healthy',category='Test',price=1);db.add(p);db.flush()
        db.add(Inventory(product_id=p.id,quantity=200,threshold=10));db.commit()
        result=run_tool(db,db.get(User,users['Manager']),None,{'tool':'get_inventory_status','arguments':{'low_stock':True}})
        assert all(row['quantity']<=row['threshold'] for row in result['rows'])
        assert 'HEALTHY' not in result['summary']


def test_upload_rejects_non_utf8_and_zip_disguised_as_docx(env):
    import io,zipfile
    client,_,_,_=env;login(client)
    assert client.post('/api/documents',files={'file':('bad.txt',b'\xff\xfe','text/plain')}).status_code==422
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('not-word.txt','Hello')
    assert client.post('/api/documents',files={'file':('fake.docx',stream.getvalue(),'application/zip')}).status_code==422


def test_csv_formula_neutralized_and_large_pdf_paginates(env):
    import io,csv
    from pypdf import PdfReader
    client,factory,users,_=env;login(client)
    with factory() as db:
        wf=Workflow(user_id=users['Manager'],request='Export',idempotency_key=uuid.uuid4().hex);db.add(wf);db.flush()
        report=Report(user_id=users['Manager'],workflow_id=wf.id,title='Export test',data={
            'month':'2026-11','total':1000,'source':'Test data','summary':'Summary',
            'rows':[{'category':'=HYPERLINK("https://example.invalid")','revenue':1}]+[{'category':f'Category {i}','revenue':1} for i in range(100)]})
        db.add(report);db.commit();rid=report.id
    response=client.get(f'/api/reports/{rid}/export?format=csv')
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[1][0].startswith("'=")
    response=client.get(f'/api/reports/{rid}/export?format=pdf')
    pdf=PdfReader(io.BytesIO(response.content))
    assert len(pdf.pages)>1
    assert 'Category 99' in ''.join(p.extract_text() for p in pdf.pages)


def test_readiness_and_login_configuration_do_not_expose_secrets(env,monkeypatch):
    from app.config import settings
    client,_,_,_=env
    assert client.get('/api/health').json()=={'status':'ok'}
    assert client.get('/api/health/ready').status_code==200
    monkeypatch.setattr(settings,'demo_mode',False);monkeypatch.setattr(settings,'sample_data',False)
    assert client.get('/api/auth/config').json()=={'demo_accounts':False}
