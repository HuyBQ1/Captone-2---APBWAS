import uuid
from sqlalchemy import select,func
from conftest import login,create,execute
from app import models as m,usage
from app.audit import verify

def report(client,factory):
    w=create(client,'Tạo Word và Excel báo cáo tài chính tháng 7 năm 2026');execute(factory,w['id'])
    with factory() as db:
        assert db.get(m.Workflow,w['id']).status=='completed'
        db.scalar(select(m.Job).where(m.Job.resource==w['id'])).status='done';db.commit()
    return w

def test_delete_removes_messages_blobs_and_cache_but_keeps_usage_and_audit(env):
    client,factory,users,*_=env;login(client)
    w=report(client,factory);f=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items']
    usage.cache.setex('memory:'+w['conversation_id'],1800,'{"month":"2026-07"}')
    with factory() as db:
        db.scalar(select(m.UsageRecord).where(m.UsageRecord.workflow_id==w['id'])).tokens=137;db.commit()
    response=client.delete('/api/conversations/'+w['conversation_id']);assert response.status_code==200,response.text
    assert response.json()['files_deleted']==2 and response.json()['file_bytes_deleted']>0
    assert usage.cache.get('memory:'+w['conversation_id']) is None
    assert client.get('/api/conversations/'+w['conversation_id']).status_code==404
    assert all(client.get(file['download_url']).status_code==404 for file in f)
    with factory() as db:
        assert not db.scalar(select(func.count()).select_from(m.Message).where(m.Message.conversation_id==w['conversation_id']))
        assert not db.scalar(select(func.count()).select_from(m.ToolExecution).where(m.ToolExecution.workflow_id==w['id']))
        saved=db.get(m.Workflow,w['id']);assert saved.conversation_id is None and saved.result=={'conversation_deleted':True}
        assert db.scalar(select(m.UsageRecord.tokens).where(m.UsageRecord.workflow_id==w['id']))==137
        assert verify(db)
    assert client.post('/api/workflows/'+w['id']+'/retry').status_code==409
    assert client.delete('/api/conversations/'+w['conversation_id']).status_code==404

def test_other_owner_including_admin_cannot_delete_chat(env):
    client,factory,*_=env;login(client);w=report(client,factory)
    login(client,'Admin');assert client.delete('/api/conversations/'+w['conversation_id']).status_code==404
    login(client);assert client.get('/api/conversations/'+w['conversation_id']).status_code==200

def test_active_workflow_or_unfinished_job_blocks_deletion(env):
    client,factory,*_=env;login(client);w=create(client,'Kiểm tra tồn kho')
    assert client.delete('/api/conversations/'+w['conversation_id']).status_code==409
    execute(factory,w['id'])
    assert client.delete('/api/conversations/'+w['conversation_id']).status_code==409
    assert client.get('/api/conversations/'+w['conversation_id']).status_code==200

def test_email_attachment_and_saved_business_report_survive_chat_deletion(env):
    client,factory,*_=env;login(client);w=report(client,factory)
    files=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items']
    c=client.post('/api/mail/campaigns',json={'subject':'Báo cáo tháng 7','body_text':'Xem báo cáo đính kèm.','attachment_ids':[files[0]['id']],'idempotency_key':str(uuid.uuid4())}).json()
    with factory() as db:
        saved=m.Report(user_id=db.get(m.Workflow,w['id']).user_id,workflow_id=w['id'],title='Báo cáo đã lưu',data={'total':123});db.add(saved);db.commit();rid=saved.id
    response=client.delete('/api/conversations/'+w['conversation_id']);assert response.status_code==200,response.text
    assert response.json()['email_files_retained']==1 and response.json()['files_deleted']==1
    assert client.get(files[0]['download_url']).status_code==200
    assert client.get('/api/mail/campaigns/'+c['id']).json()['attachments'][0]['id']==files[0]['id']
    assert client.get('/api/reports/'+rid).json()['data']['total']==123

def test_deleting_one_chat_does_not_touch_other_conversations(env):
    client,factory,*_=env;login(client);one=report(client,factory);two=report(client,factory)
    assert client.delete('/api/conversations/'+one['conversation_id']).status_code==200
    assert client.get('/api/conversations/'+two['conversation_id']).status_code==200
    assert len(client.get('/api/files?conversation_id='+two['conversation_id']).json()['items'])==2
