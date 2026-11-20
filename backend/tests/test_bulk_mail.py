import base64,json,uuid
from email import message_from_bytes
from datetime import timedelta
import httpx,pytest
from sqlalchemy import select,func
from conftest import login,create,execute
from test_gmail import google_config,oauth,transport
from app import models as m
from app import mail_campaigns as mail
from app.config import settings

def draft(client,**kwargs):
    return client.post('/api/mail/campaigns',json={'subject':'Thông báo họp','body_text':'Mời họp lúc 9 giờ.','idempotency_key':str(uuid.uuid4()),**kwargs})

def queue(client,c):return client.post('/api/mail/campaigns/'+c['id']+'/send',json={'confirmed':True,'revision':c['revision']})

def process(factory,id):
    with factory() as db:
        job=db.scalar(select(m.Job).where(m.Job.resource==id));mail.process_mail(db,job)

def contacts(factory,users):
    with factory() as db:
        for role,id in users.items():db.get(m.User,id).delivery_email=role.lower()+'@gmail.com'
        db.commit()

def test_contacts_rbac_and_sample_email_blocked(env):
    client,factory,users,*_=env
    login(client,'Employee');assert client.get('/api/mail/employees').status_code==403
    login(client);data=client.get('/api/mail/employees').json();assert not data['can_manage'] and not any(u['ready'] for u in data['items'])
    assert client.put('/api/mail/employees/'+users['Employee'],json={'delivery_email':'staff@gmail.com'}).status_code==403
    assert client.put('/api/mail/employees/'+users['Manager'],json={'delivery_email':'x@company.example'}).status_code==422
    assert client.put('/api/mail/employees/'+users['Manager'],json={'delivery_email':'manager@gmail.com'}).status_code==200
    with factory() as db:assert db.get(m.User,users['Manager']).email=='manager@apbwas.demo'
    login(client,'Admin');assert client.put('/api/mail/employees/'+users['Employee'],json={'delivery_email':'staff@gmail.com'}).status_code==200

def test_preview_dedup_owner_and_empty_selection(env):
    client,factory,users,*_=env;login(client)
    assert draft(client,recipient_ids=[]).status_code==422
    c=draft(client).json();assert not c['recipients'] and len(c['skipped'])==3
    contacts(factory,users)
    with factory() as db:db.get(m.User,users['Employee']).delivery_email='manager@gmail.com';db.commit()
    c=draft(client).json();assert len(c['recipients'])==2 and len(c['skipped'])==1
    login(client,'Admin');assert client.get('/api/mail/campaigns/'+c['id']).status_code==404
    with factory() as db:
        db.add(m.Workspace(id='elsewhere',name='Other'));db.commit()
        db.get(m.User,users['Employee']).workspace_id='elsewhere';db.commit()
    assert draft(client,recipient_ids=[users['Employee']]).status_code==422

def test_send_confirmation_queue_individual_mime_and_idempotency(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch);contacts(factory,users)
    c=draft(client).json();sent=[]
    assert client.post('/api/mail/campaigns/'+c['id']+'/send',json={'confirmed':False,'revision':1}).status_code==422
    assert client.post('/api/mail/campaigns/'+c['id']+'/send',json={'confirmed':True,'revision':2}).status_code==409
    assert queue(client,c).json()['status']=='queued';assert queue(client,c).json()['status']=='queued'
    def handler(request):
        assert str(request.url)=='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        msg=message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)['raw']))
        assert msg['From']=='sender@gmail.com' and not msg['Cc'] and not msg['Bcc']
        sent.append(msg['To']);return httpx.Response(200,json={'id':'remote-'+str(len(sent))})
    transport(monkeypatch,handler);process(factory,c['id']);process(factory,c['id'])
    assert set(sent)=={'admin@gmail.com','manager@gmail.com','employee@gmail.com'} and len(sent)==3
    result=client.get('/api/mail/campaigns/'+c['id']).json();assert result['status']=='completed' and result['counts']=={'sent':3}
    with factory() as db:assert len(list(db.scalars(select(m.Job).where(m.Job.resource==c['id']))))==1

def test_cancel_snapshot_and_daily_limit(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch);contacts(factory,users)
    c=draft(client).json()
    with factory() as db:db.get(m.User,users['Employee']).delivery_email='changed@gmail.com';db.commit()
    assert queue(client,c).status_code==409
    c=draft(client).json();monkeypatch.setattr(settings,'mail_bulk_daily_limit',2);assert queue(client,c).status_code==429
    monkeypatch.setattr(settings,'mail_bulk_daily_limit',100);assert queue(client,c).status_code==200
    assert client.post('/api/mail/campaigns/'+c['id']+'/cancel').status_code==200
    transport(monkeypatch,lambda r:pytest.fail('Cancelled emails must not be sent'))
    process(factory,c['id']);assert client.get('/api/mail/campaigns/'+c['id']).json()['status']=='cancelled'

def test_timeout_crash_recovery_and_revoked_user_never_resend(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch);contacts(factory,users)
    c=draft(client).json();queue(client,c);calls=[]
    with factory() as db:
        d=db.scalar(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c['id'],m.MailDelivery.employee_id==users['Admin']));d.status='sending';db.commit()
        db.get(m.User,users['Employee']).active=False;db.commit()
    def handler(r):calls.append(1);raise httpx.ReadTimeout('private transport error')
    transport(monkeypatch,handler);process(factory,c['id']);process(factory,c['id']);assert len(calls)==1
    result=client.get('/api/mail/campaigns/'+c['id']).json();assert result['counts']=={'unknown':2,'skipped':1} and result['status']=='unknown'
    c=draft(client).json();queue(client,c)
    with factory() as db:db.get(m.User,users['Manager']).active=False;db.commit()
    process(factory,c['id']);assert len(calls)==1

def test_ai_creates_only_draft_and_finance_in_body_is_not_rerouted(env):
    client,factory,*_=env;login(client)
    wf=create(client,'Gửi email cho tất cả nhân viên\nTiêu đề: Báo cáo tháng\nNội dung: Vui lòng chuẩn bị doanh thu, lợi nhuận và Excel.')
    execute(factory,wf['id'])
    with factory() as db:
        w=db.get(m.Workflow,wf['id']);assert w.status=='completed',w.error
        assert w.plan[0]['tool']=='prepare_employee_email'
        c=db.scalar(select(m.MailCampaign).where(m.MailCampaign.workflow_id==w.id));assert c.status=='draft'
        assert db.scalar(select(m.Job).where(m.Job.kind=='mail')) is None
        assert 'Chưa gửi' in w.result['summary']

def test_edit_draft_revision_invalidates_old_confirmation(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch);contacts(factory,users)
    c=draft(client).json()
    edited=client.put('/api/mail/campaigns/'+c['id'],json={'subject':'Thông báo đã sửa','body_text':'Nội dung mới','revision':1})
    assert edited.status_code==200 and edited.json()['revision']==2
    assert queue(client,c).status_code==409
    assert queue(client,edited.json()).json()['status']=='queued'
    assert client.put('/api/mail/campaigns/'+c['id'],json={'subject':'Không sửa được','body_text':'Sau xác nhận','revision':2}).status_code==409

def test_connected_agent_selects_revenue_mail_tool_and_does_not_send(env,monkeypatch):
    from app import agent
    client,factory,users,*_=env;login(client);contacts(factory,users)
    monkeypatch.setattr(settings,'demo_mode',False)
    from app.schemas import Plan,PlanStep,ToolArgs
    monkeypatch.setattr(agent,'connected_plan',lambda request,context,*a,**kw:(Plan(steps=[PlanStep(tool='prepare_revenue_email',label='Soạn email',arguments=ToolArgs(month=context['month']))]),123))
    from app import business_ai
    monkeypatch.setattr(business_ai,'connected_plan',lambda *a,**kw:(Plan(steps=[],clarification='Bản nháp đã sẵn sàng; mở để xem người nhận và xác nhận gửi.'),31))
    month=m.now().astimezone(__import__('zoneinfo').ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m')
    for request in ['soạn thư doanh thu tháng này và gửi cho nhân viên',f'gửi email doanh thu tháng {month} cho toàn bộ nhân viên']:
        with factory() as db:
            w=m.Workflow(user_id=users['Manager'],request=request,idempotency_key=str(uuid.uuid4()));db.add(w);db.commit();wid=w.id
        execute(factory,wid)
        with factory() as db:
            w=db.get(m.Workflow,wid);assert w.status=='completed',w.error
            c=db.scalar(select(m.MailCampaign).where(m.MailCampaign.workflow_id==wid))
            assert c.status=='draft' and c.subject.endswith(month) and '400.000 ₫' in c.body_text
            assert len(list(db.scalars(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id))))==3
            assert 'chưa phải lợi nhuận' in c.body_text
            assert db.scalar(select(m.Job).where(m.Job.kind=='mail')) is None
            assert w.tokens==154 and w.result['execution_mode']=='llm_agent'

def test_revenue_mail_empty_month_explicit_month_and_subset_are_honest(env,monkeypatch):
    from app import agent
    client,factory,users,*_=env;login(client)
    plan,_=agent.make_plan('soạn thư doanh thu tháng này gửi cho nhân viên An',{})
    assert not plan.steps and plan.clarification
    wf=create(client,'soạn thư doanh thu 07/2020 cho toàn bộ nhân viên');execute(factory,wf['id'])
    with factory() as db:
        w=db.get(m.Workflow,wf['id']);assert w.status=='completed',w.error
        c=db.scalar(select(m.MailCampaign).where(m.MailCampaign.workflow_id==w.id));assert c.subject.endswith('2020-07')
        assert 'Chưa có giao dịch' in c.body_text and 'không đủ để kết luận' in c.body_text
    login(client,'Employee');wf=create(client,'soạn thư doanh thu tháng này gửi cho nhân viên');execute(factory,wf['id'])
    with factory() as db:assert db.get(m.Workflow,wf['id']).status=='failed'

def test_open_email_followup_is_scoped_to_conversation_and_agent_selects_tool(env,monkeypatch):
    from app import agent
    client,factory,users,*_=env;login(client)
    first=create(client,'soạn thư doanh thu tháng này gửi cho nhân viên');execute(factory,first['id'])
    with factory() as db:cid=db.scalar(select(m.MailCampaign).where(m.MailCampaign.workflow_id==first['id'])).id
    monkeypatch.setattr(settings,'demo_mode',False)
    from app.schemas import Plan,PlanStep
    monkeypatch.setattr(agent,'connected_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool='open_employee_email',label='Mở nháp')]),13))
    from app import business_ai
    def answer(request,context,*a,**kw):
        missing=context['evidence'][0]['data']['mail_status']=='not_found'
        return Plan(steps=[],clarification='Chưa có email trong hội thoại này.' if missing else 'Đã tìm thấy bản nháp; mở email để xem và xác nhận gửi.'),3
    monkeypatch.setattr(business_ai,'connected_plan',answer)
    second=create(client,'Xem người nhận và xác nhận gửi',first['conversation_id']);execute(factory,second['id'])
    with factory() as db:
        w=db.get(m.Workflow,second['id']);assert w.status=='completed',w.error
        assert w.result['campaign_id']==cid and w.tokens==16
        assert db.scalar(select(func.count()).select_from(m.MailCampaign))==1
        assert db.scalar(select(m.Job).where(m.Job.kind=='mail')) is None
    history=client.get('/api/conversations/'+first['conversation_id']).json()
    assert history['workflows'][0]['mail_campaign_id']==cid and not history['workflows'][0]['result']
    separate=create(client,'Mở bản nháp email');execute(factory,separate['id'])
    with factory() as db:
        w=db.get(m.Workflow,separate['id']);assert w.status=='completed' and not w.result.get('campaign_id')
        assert 'Chưa có email' in w.result['summary']
