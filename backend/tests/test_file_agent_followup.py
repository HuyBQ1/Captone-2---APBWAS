import uuid
from sqlalchemy import select
from conftest import login,execute
from test_agents import create_agent,body,start
from app import models as m
from app.upgrade_file_agent import upgrade

def test_published_file_agent_upgrade_keeps_history_and_handles_excel_then_mail(env):
    client,factory,users,*_=env;login(client)
    payload=body(['create_word_file','create_excel_file']);payload['config']['permissions']=['agents.run','sales.read','inventory.read']
    a=create_agent(client,payload);assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    w=start(client,a,'Tạo báo cáo doanh thu tháng 7 năm 2026 bằng Word');execute(factory,w['id'])
    with factory() as db:
        original=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==a['id']));old=dict(original.snapshot)
        result=upgrade(db,db.get(m.User,users['Manager']),a['id']);assert result['version']==2
        assert upgrade(db,db.get(m.User,users['Manager']),a['id'])['changed'] is False
        assert db.get(m.AgentVersion,original.id).snapshot==old
    def follow(request):
        response=client.post('/api/agents/'+a['id']+'/runs',json={'request':request,'version':2,'conversation_id':w['conversation_id'],'idempotency_key':str(uuid.uuid4())});assert response.status_code==202,response.text
        run=response.json();execute(factory,run['id']);r=client.get('/api/workflows/'+run['id']).json();assert r['status']=='completed',r['error'];return r
    excel=follow('cho tôi thêm file exel')
    assert excel['plan'][0]['tool']=='create_excel_file' and excel['plan'][0]['arguments']['source']=='finance' and excel['plan'][0]['arguments']['month']=='2026-07'
    mail=follow('Gửi mail file báo cáo tháng 7 cho toàn bộ nhân viên.')
    c=client.get('/api/mail/campaigns/'+mail['result']['campaign_id']).json()
    assert c['status']=='draft' and {f['kind'] for f in c['attachments']}=={'docx','xlsx'}
    with factory() as db:assert 'prepare_report_email' not in db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==a['id'],m.AgentVersion.number==1)).snapshot['tools']
