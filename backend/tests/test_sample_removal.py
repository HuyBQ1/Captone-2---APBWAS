import uuid
from datetime import date
import pytest
from sqlalchemy import select,func
from app import models as m
from app.remove_sample_data import remove,KEY
from app.audit import verify
from conftest import login
from test_agents import create_agent,body

def prepare(client,factory,users):
    login(client)
    with factory() as db:
        p=m.Product(sku='NC-TEST-001',name='Sample only',category='Sample',price=100);db.add(p);db.flush();pid=p.id
        db.add(m.Inventory(product_id=pid,quantity=5,threshold=1));db.add(m.Sale(product_id=pid,date=m.now(),quantity=1,revenue=100))
        fake=m.Document(user_id=users['Manager'],name='Mock policy',scope='all',status='indexed',content='Mô phỏng');real=m.Document(user_id=users['Manager'],name='Real policy',scope='all',status='indexed',content='Công ty tự ban hành.');db.add_all([fake,real]);db.flush()
        fake_id,real_id=fake.id,real.id;db.add(m.DocumentFile(document_id=fake_id,content=b'fake'))
        w=m.Workflow(user_id=users['Manager'],request='Mock knowledge',status='completed',idempotency_key=str(uuid.uuid4()));db.add(w);db.flush();wid=w.id
        f=m.GeneratedFile(user_id=users['Manager'],workspace_id='primary',workflow_id=wid,kind='docx',title='Mock copy',filename='mock.docx',content=b'fake',size=4,sha256='0'*64,request_hash='0'*64,source={'type':'knowledge','document_ids':[fake_id]});db.add(f);db.flush();fid=f.id
        w.result={'summary':'Old mock answer','sources':[{'document_id':fake_id}],'files':[{'id':fid}]}
        db.add(m.Report(workflow_id=wid,user_id=users['Manager'],title='Mock report',data={'total':100}))
        c=m.MailCampaign(user_id=users['Manager'],workspace_id='primary',workflow_id=wid,idempotency_key=str(uuid.uuid4()),subject='Mock mail',body_text='Mock amount',attachment_ids=[fid]);db.add(c)
        db.add(m.UsageRecord(user_id=users['Manager'],workflow_id=wid,tokens=99))
        db.add(m.SystemSetting(key='nova-commerce-business-v1',value={'product_ids':[pid],'document_ids':[fake_id],'report_ids':[]}));db.commit()
    payload=body(['search_internal_documents']);payload['config']['permissions']=['documents.read'];payload['config']['knowledge_ids']=[fake_id,real_id]
    a=create_agent(client,payload);assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    return pid,fake_id,real_id,wid,fid,a['id']

def test_remove_known_samples_keeps_real_data_accounts_models_agents_and_quota(env):
    client,factory,users,real_product=env;pid,did,real_doc,wid,fid,aid=prepare(client,factory,users)
    with factory() as db:
        original=dict(db.get(m.AgentConfig,aid).config);result=remove(db)
        assert result['accounts_and_connections_preserved'] and result['removed']['products']==1
        assert db.get(m.Product,pid) is None and db.get(m.Document,did) is None and db.get(m.GeneratedFile,fid) is None
        assert db.get(m.Product,real_product) and db.get(m.Document,real_doc)
        assert db.scalar(select(func.count()).select_from(m.User))==3
        config=db.get(m.AgentConfig,aid).config;assert config['knowledge_ids']==[real_doc]
        assert {k:v for k,v in config.items() if k!='knowledge_ids'}=={k:v for k,v in original.items() if k!='knowledge_ids'}
        a=db.get(m.Agent,aid);assert a.published_version==2
        versions=list(db.scalars(select(m.AgentVersion).where(m.AgentVersion.agent_id==aid).order_by(m.AgentVersion.number)))
        assert did in versions[0].snapshot['knowledge_ids'] and versions[1].snapshot['knowledge_ids']==[real_doc]
        assert db.scalar(select(m.UsageRecord.tokens).where(m.UsageRecord.workflow_id==wid))==99
        c=db.scalar(select(m.MailCampaign));assert c.status=='cancelled' and c.attachment_ids==[]
        assert db.get(m.Workflow,wid).result['mock_data_removed'] and verify(db)
        assert remove(db)['already_removed'] is True

def test_cleanup_marker_prevents_all_sample_seeders_from_reintroducing_data(env,monkeypatch):
    from app import seed,business_data_pack,seed_finance_sample,seed_product_media,import_word_library
    client,factory,users,*_=env;prepare(client,factory,users)
    with factory() as db:remove(db)
    monkeypatch.setattr(seed,'Session',factory);seed.seed()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.Product))==1
        for callback in [lambda:business_data_pack.import_pack(db,date(2026,11,2)),lambda:seed_finance_sample.populate(db),lambda:import_word_library.publish(db,'/missing')]:
            with pytest.raises(ValueError,match='xóa theo yêu cầu'):callback()
        assert seed_product_media.populate(db)['added']==0

def test_cleanup_refuses_active_workflow_without_mutating_data(env):
    client,factory,users,*_=env;pid,*_=prepare(client,factory,users)
    with factory() as db:
        db.add(m.Workflow(user_id=users['Manager'],request='Running',status='running',idempotency_key=str(uuid.uuid4())));db.commit()
        with pytest.raises(ValueError,match='Còn workflow'):remove(db)
        assert db.get(m.Product,pid) and db.get(m.SystemSetting,KEY) is None

def test_old_tagged_mail_is_redacted_even_after_its_chat_was_deleted(env):
    from app.remove_sample_data import finish_mail_cleanup
    client,factory,users,*_=env;prepare(client,factory,users)
    with factory() as db:
        remove(db)
        c=m.MailCampaign(user_id=users['Manager'],workspace_id='primary',idempotency_key=str(uuid.uuid4()),subject='Báo cáo doanh thu tháng 2026-07',body_text='Hệ thống đang sử dụng dữ liệu mẫu/mô phỏng Nova Commerce.',status='completed');db.add(c);db.commit();cid=c.id
        result=finish_mail_cleanup(db);assert result['additional_mail_copies_redacted']==1
        assert db.get(m.MailCampaign,cid).status=='completed' and 'đã được xóa' in db.get(m.MailCampaign,cid).body_text
        assert finish_mail_cleanup(db)['additional_mail_copies_redacted']==0
