import base64,json
from email import policy
from email.parser import BytesParser
import httpx
from sqlalchemy import select,func
from app import models as m,workflows
from app.schemas import Plan
from conftest import login,create,execute
from test_gmail import google_config,oauth,transport
from test_bulk_mail import contacts,queue,process,draft

def files(client,factory):
    w=create(client,'Tạo Word và Excel báo cáo doanh thu tháng 7 năm 2026');execute(factory,w['id'])
    assert client.get('/api/workflows/'+w['id']).json()['status']=='completed'
    return w

def test_report_mail_reuses_owned_conversation_files_and_followup_keeps_intent(env,monkeypatch):
    client,factory,users,*_=env;login(client);contacts(factory,users)
    w=files(client,factory)
    # Reproduce a clarification persisted by the older version, then continue it.
    with monkeypatch.context() as patch:
        patch.setattr(workflows,'make_plan',lambda *a,**kw:(Plan(steps=[],clarification='Báo cáo nào?'),0))
        first=create(client,'gửi mail về file báo cáo này cho toàn bộ nhân viên',w['conversation_id']);execute(factory,first['id'])
    follow=create(client,'nội dung báo cáo doanh thu tháng 7',w['conversation_id']);execute(factory,follow['id'])
    result=client.get('/api/workflows/'+follow['id']).json();assert result['status']=='completed',result['error']
    assert result['plan'][0]['tool']=='prepare_report_email'
    c=client.get('/api/mail/campaigns/'+result['result']['campaign_id']).json()
    assert c['status']=='draft' and len(c['attachments'])==2 and len(c['recipients'])==3
    assert '2026-07' in c['subject'] and {f['kind'] for f in c['attachments']}=={'docx','xlsx'}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.GeneratedFile))==2
        assert db.scalar(select(func.count()).select_from(m.Job).where(m.Job.kind=='mail_campaign'))==0
        assert all(d.status=='pending' for d in db.scalars(select(m.MailDelivery)))

def test_confirmed_delivery_contains_real_office_attachments_with_original_hashes(env,google_config,monkeypatch):
    import hashlib
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch);contacts(factory,users)
    w=files(client,factory)
    request=create(client,'gửi mail file báo cáo này cho toàn bộ nhân viên',w['conversation_id']);execute(factory,request['id'])
    result=client.get('/api/workflows/'+request['id']).json()
    c=client.get('/api/mail/campaigns/'+result['result']['campaign_id']).json()
    expected={f['filename']:f['sha256'] for f in c['attachments']};sent=[]
    assert queue(client,c).status_code==200
    def handler(request):
        msg=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(json.loads(request.content)['raw']))
        attached=list(msg.iter_attachments());assert len(attached)==2
        for item in attached:assert hashlib.sha256(item.get_payload(decode=True)).hexdigest()==expected[item.get_filename()]
        sent.append(msg['To']);return httpx.Response(200,json={'id':'mock-'+str(len(sent))})
    transport(monkeypatch,handler);process(factory,c['id']);process(factory,c['id'])
    assert len(sent)==3 and client.get('/api/mail/campaigns/'+c['id']).json()['counts']=={'sent':3}

def test_attachment_access_is_rechecked_and_other_owner_cannot_attach(env,google_config,monkeypatch):
    client,factory,users,*_=env;login(client);oauth(client,monkeypatch)
    w=files(client,factory);f=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items'][0]
    c=draft(client,attachment_ids=[f['id']]).json()
    login(client,'Admin');assert draft(client,attachment_ids=[f['id']]).status_code==404
    login(client)
    with factory() as db:
        role=db.get(m.Role,'Manager');role.permissions=[p for p in role.permissions if p!='inventory.read'];db.commit()
    assert queue(client,c).status_code==403
    assert client.get('/api/mail/campaigns/'+c['id']).json()['attachment_error']

def test_missing_report_never_attaches_files_from_another_conversation(env):
    client,factory,*_=env;login(client);files(client,factory)
    w=create(client,'gửi mail file báo cáo tháng 7 cho toàn bộ nhân viên');execute(factory,w['id'])
    r=client.get('/api/workflows/'+w['id']).json()
    assert r['status']=='completed' and 'campaign_id' not in r['result'] and 'Chưa có tệp' in r['result']['summary']
