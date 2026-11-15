import json,uuid
from sqlalchemy import select,func
from app import models as m
from app.workflow_graph import execution_graph
from conftest import login

def saved_mail(factory,users):
    with factory() as db:
        plan=[{'tool':'prepare_report_email','label':'Soạn email kèm Excel','arguments':{'month':'2026-01'}}]
        w=m.Workflow(user_id=users['Manager'],request='Soạn email',idempotency_key=str(uuid.uuid4()),status='completed',plan=plan,checkpoint=1,result={'execution_mode':'llm_agent','business_analysis':{'status':'completed'}})
        db.add(w);db.flush()
        c=m.MailCampaign(user_id=users['Manager'],workspace_id='primary',workflow_id=w.id,idempotency_key=str(uuid.uuid4()),subject='Report',body_text='Private body',attachment_ids=['saved-file-id'])
        db.add(c);db.flush()
        db.add(m.MailDelivery(campaign_id=c.id,employee_id=users['Employee'],recipient='staff.private@gmail.com',recipient_name='Staff'))
        db.add(m.WorkflowStep(workflow_id=w.id,position=0,tool='prepare_report_email',status='completed',output={'campaign_id':c.id,'month':'2026-01'}));db.commit()
        return w.id,c.id

def test_legacy_single_tool_expands_from_receipts_without_running_or_sending(env):
    client,factory,users,_=env;w,c=saved_mail(factory,users);login(client)
    for _ in range(2):
        response=client.get('/api/workflows/'+w);assert response.status_code==200
        graph=response.json()['execution_graph'];stages=graph['stages']
        assert graph['tool_count']==1 and len(stages)==9
        assert stages[-2]['status']=='waiting_approval' and stages[-1]['status']=='queued'
        assert stages[-2]['href']=='/mail/campaigns/'+c
        assert 'Private body' not in json.dumps(graph) and 'staff.private@gmail.com' not in json.dumps(graph)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.WorkflowStep))==1
        assert db.scalar(select(func.count()).select_from(m.Job))==0
        assert db.get(m.MailCampaign,c).status=='draft'
        assert db.scalar(select(m.MailDelivery)).attempted_at is None

def test_live_mail_status_updates_without_changing_the_completed_workflow(env):
    _,factory,users,_=env;id,cid=saved_mail(factory,users)
    with factory() as db:
        w=db.get(m.Workflow,id);u=db.get(m.User,users['Manager']);steps=list(db.scalars(select(m.WorkflowStep)))
        c=db.get(m.MailCampaign,cid);c.approved_at=m.now();c.status='sending';db.commit()
        stages=execution_graph(db,u,w,steps)['stages'];assert stages[-2]['status']=='completed' and stages[-1]['status']=='running'
        c.status='completed';delivery=db.scalar(select(m.MailDelivery));delivery.status='sent';db.commit()
        assert execution_graph(db,u,w,steps)['stages'][-1]['status']=='completed'
        delivery.status='unknown';db.commit()
        assert execution_graph(db,u,w,steps)['stages'][-1]['status']=='failed'
        assert w.status=='completed' and len(w.plan)==1

def test_foreign_mail_or_removed_content_is_not_expanded(env):
    _,factory,users,_=env;id,cid=saved_mail(factory,users)
    with factory() as db:
        w=db.get(m.Workflow,id);u=db.get(m.User,users['Manager']);steps=list(db.scalars(select(m.WorkflowStep)))
        c=db.get(m.MailCampaign,cid);c.user_id=users['Admin'];db.commit()
        graph=execution_graph(db,u,w,steps)
        assert not any(s['href'] for s in graph['stages'])
        assert not any(s['basis']=='live_email' for s in graph['stages'])
        w.result={'conversation_deleted':True}
        assert not execution_graph(db,u,w,steps)['stages']

def test_failed_tool_does_not_claim_internal_phases_completed(env):
    _,factory,users,_=env;id,_=saved_mail(factory,users)
    with factory() as db:
        w=db.get(m.Workflow,id);w.status='failed';w.result={'execution_mode':'llm_agent'}
        step=db.scalar(select(m.WorkflowStep));step.status='failed';step.output={};db.commit()
        stages=execution_graph(db,db.get(m.User,users['Manager']),w,[step])['stages']
        assert len(stages)==2 and stages[-1]['status']=='failed'
        assert not any('Lưu bản nháp' in s['label'] for s in stages)
