"""Opt-in PostgreSQL-only verification; each run uses an isolated random schema."""
import os, uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine,text,select,func
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app import db as db_module
from app.models import Role,User,Product,Inventory,Workflow,Approval,SystemSetting,ToolExecution,AuditLog,now
from app.permissions import DEFAULT_PERMISSIONS
from app.usage import DEFAULT_CONFIG
from app.approvals import decide
from app.schemas import Decision
from app.tools import run_tool
from app.audit import verify
from fastapi import HTTPException
from datetime import timedelta
from app.workflows import emit
from app.audit import audit

URL=os.environ.get('PG_TEST_DATABASE_URL','')
pytestmark=pytest.mark.skipif(not URL,reason='PG_TEST_DATABASE_URL chưa có; không dùng SQLite làm bằng chứng concurrency/pgvector.')

def test_concurrent_public_registration_creates_exactly_one_pending_account(pg):
    from app import public_accounts as accounts,models as m
    from starlette.requests import Request
    factory,_=pg
    with factory() as db:db.add(Role(name='Employee',permissions=DEFAULT_PERMISSIONS['Employee']));db.commit()
    def submit(_):
        request=Request({'type':'http','method':'POST','path':'/api/auth/register','headers':[],'client':('203.0.113.10',123),'server':('testserver',80),'scheme':'http'})
        with factory() as db:return accounts.register(accounts.Register(name='New Employee',email='staff@gmail.com',password='PersonalPassword@123'),request,db=db)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2)))
    assert results[0]==results[1]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.User))==1
        u=db.scalar(select(m.User));assert u.registration_pending and not u.active and u.role=='Employee'
        assert db.scalar(select(func.count()).select_from(m.AuthRequestAttempt))==2
        assert verify(db)

def test_concurrent_password_reset_token_is_consumed_once(pg):
    from app import models as m
    from app.enterprise import redeem,Redeem
    from app.auth import hasher
    from fastapi import Response
    import hashlib
    factory,_=pg;raw='test-reset-token-'+uuid.uuid4().hex
    with factory() as db:
        db.add(Role(name='Employee',permissions=DEFAULT_PERMISSIONS['Employee']));db.flush()
        u=User(name='Staff',email='staff@gmail.com',role='Employee',password_hash=hasher.hash('OldPassword@123'));db.add(u);db.flush()
        db.add(m.AccountToken(user_id=u.id,token_hash=hashlib.sha256(raw.encode()).hexdigest(),purpose='password_reset',expires_at=now()+timedelta(hours=1)));db.commit()
    def consume(_):
        with factory() as db:
            try:redeem(Redeem(token=raw,password='NewPassword@123'),Response(),db=db);return 200
            except HTTPException as exc:db.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(consume,range(2)))
    assert sorted(results)==[200,400]
    with factory() as db:
        assert db.scalar(select(m.AccountToken)).used_at is not None
        assert verify(db)

def test_registration_migration_preserves_existing_accounts_and_connections(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app import models as m
    import importlib
    factory,engine=pg
    with factory() as db:
        db.add(Role(name='Admin',permissions=['users.manage','mail.send']));db.flush()
        u=User(email='legacy@gmail.com',name='Legacy',role='Admin',password_hash='retained-hash',active=True);db.add(u);db.flush();id=u.id
        db.add(m.GmailConnection(user_id=id,workspace_id='primary',email=u.email,google_sub='retained-sub',credentials_ciphertext='retained-ciphertext',expires_at=now()+timedelta(hours=1),scopes=['gmail.send']));db.commit()
    with engine.begin() as c:
        c.execute(text('DROP TABLE account_emails'));c.execute(text('DROP TABLE auth_request_attempts'));c.execute(text('ALTER TABLE users DROP COLUMN registration_pending'))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0013_registration_recovery');migration.upgrade();migration.upgrade()
    with factory() as db:
        u=db.get(User,id);assert u.active and not u.registration_pending and u.password_hash=='retained-hash'
        assert db.get(m.GmailConnection,id).credentials_ciphertext=='retained-ciphertext'
        assert db.scalar(select(func.count()).select_from(m.AccountEmail))==0

@pytest.fixture
def pg(monkeypatch):
    engine=create_engine(URL,pool_pre_ping=True)
    schema='apbwas_test_'+uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        connection.execute(text('CREATE SCHEMA '+schema))
    scoped=create_engine(URL,connect_args={'options':'-csearch_path='+schema+',public'},pool_pre_ping=True)
    # Inspection otherwise finds public tables through search_path and skips
    # creation in the isolated schema. Never run a test against public tables.
    Base.metadata.create_all(scoped,checkfirst=False)
    monkeypatch.setattr(db_module,'read_engine',scoped)
    factory=sessionmaker(scoped,expire_on_commit=False)
    from app.models import Workspace
    with factory() as db:db.add(Workspace(id='primary',name='Test workspace'));db.commit()
    try:yield factory,scoped
    finally:
        scoped.dispose()
        with engine.begin() as connection:connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        engine.dispose()

def test_two_simultaneous_approvers_apply_exactly_once(pg):
    factory,engine=pg
    with factory() as db:
        for role,p in DEFAULT_PERMISSIONS.items():db.add(Role(name=role,permissions=p))
        db.add(SystemSetting(key='limits',value=DEFAULT_CONFIG));db.commit()
        users=[User(email=f'pg-{n}@test.example',name='Manager',password_hash='not-used-in-this-test',role='Manager') for n in range(3)]
        db.add_all(users);db.flush()
        p=Product(sku='PG01',name='Postgres test',category='Test',price=1000);db.add(p);db.flush()
        db.add(Inventory(product_id=p.id,quantity=10,version=1))
        wf=Workflow(user_id=users[0].id,request='adjust',idempotency_key=uuid.uuid4().hex,status='waiting_approval',plan=[]);db.add(wf);db.flush()
        approval=Approval(user_id=users[0].id,workflow_id=wf.id,arguments={'product_id':p.id,'before':10,'quantity':50,'version':1},expires_at=now()+timedelta(hours=1))
        db.add(approval);db.commit();ids=[u.id for u in users];aid=approval.id;pid=p.id
    def decision(user_id):
        with factory() as db:
            try:
                decide(db,db.get(User,user_id),aid,Decision(decision='approved',revision=1))
                return 200
            except HTTPException as exc:
                db.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(decision,ids[1:]))
    assert sorted(results)==[200,409]
    with factory() as db:
        assert db.get(Inventory,pid).quantity==50 and db.get(Inventory,pid).version==2
        assert len(list(db.scalars(select(ToolExecution))))==1
        assert verify(db)

def test_read_only_business_transaction_blocks_write(pg):
    factory,engine=pg
    with factory() as db:
        with db_module.read_only_db(db) as reader:
            assert reader.scalar(text('SHOW transaction_read_only'))=='on'
            assert reader.scalar(text('SHOW statement_timeout'))=='2500ms'
            with pytest.raises(Exception):reader.execute(text("INSERT INTO products (id,sku,name,category,price,created_at) VALUES ('x','x','x','x',1,now())"))


def test_concurrent_audit_and_event_writers_do_not_deadlock(pg):
    factory,_=pg
    with factory() as db:
        db.add(Role(name='Manager',permissions=DEFAULT_PERMISSIONS['Manager']));db.commit()
        user=User(email='audit-pg@test.example',name='Test',role='Manager',password_hash='unused');db.add(user);db.flush()
        ids=[]
        for _ in range(8):
            wf=Workflow(user_id=user.id,request='Test audit locking',idempotency_key=uuid.uuid4().hex)
            db.add(wf);db.flush();ids.append(wf.id)
        db.commit()
    def write(item):
        index,wid=item
        with factory() as db:
            db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            wf=db.get(Workflow,wid)
            if index%2:audit(db,'test','before',wid)
            emit(db,wf,'test',{})
            audit(db,'test','after',wid)
            db.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(write,enumerate(ids)))
    with factory() as db:
        assert verify(db)
        from app.models import WorkflowEvent
        assert len(list(db.scalars(select(WorkflowEvent))))==8


def test_postgres_migrations_vector_index_and_audit_trigger(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            importlib.import_module('migrations.versions.0001_initial').upgrade()
            importlib.import_module('migrations.versions.0002_approval_history').upgrade()
            importlib.import_module('migrations.versions.0003_enterprise').upgrade()
            importlib.import_module('migrations.versions.0004_product_images').upgrade()
            importlib.import_module('migrations.versions.0005_finance').upgrade()
            importlib.import_module('migrations.versions.0006_agents').upgrade()
    with factory() as db:
        index=db.scalar(text("SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() AND indexname='document_chunks_vector_idx'"))
        assert 'hnsw' in index and 'vector_cosine_ops' in index
        row=audit(db,'test','created','fixture');db.commit();aid=row.id
    for statement in ['UPDATE audit_logs SET event=\'tampered\' WHERE id=:id','DELETE FROM audit_logs WHERE id=:id']:
        with engine.connect() as connection:
            with pytest.raises(Exception,match='append-only'):
                connection.execute(text(statement),{'id':aid})
            connection.rollback()


def test_top_five_retrieval_with_ten_thousand_chunks_and_private_scope(pg):
    import time
    from sqlalchemy import insert,func
    from app.models import Document,DocumentChunk
    from app.provider import embed,model_id
    from app.retrieval import search
    factory,engine=pg
    with factory() as db:
        db.add(Role(name='Employee',permissions=DEFAULT_PERMISSIONS['Employee']));db.commit()
        user=User(email='vector-pg@test.example',name='Employee',role='Employee',password_hash='unused');db.add(user);db.flush()
        public=Document(user_id=user.id,name='Public policy',scope='all',status='indexed',content='')
        private=Document(user_id=user.id,name='Private policy',scope='Admin',status='indexed',content='')
        db.add_all([public,private]);db.flush()
        query='chính sách nghỉ phép năm'
        target=embed(query);irrelevant=embed('máy in sản phẩm tồn kho')
        rows=[];wanted=set()
        for i in range(10000):
            cid=str(uuid.uuid4())
            if i<5:wanted.add(cid)
            rows.append({'id':cid,'document_id':private.id if 5<=i<55 else public.id,
                         'content':query if i<55 else 'Không liên quan','position':i,'model':model_id(),
                         'embedding':target if i<55 else irrelevant})
        db.execute(insert(DocumentChunk),rows);db.commit()
        db.execute(text('CREATE INDEX retrieval_benchmark_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops)'))
        db.execute(text('ANALYZE document_chunks'));db.commit()
        assert db.scalar(select(func.count()).select_from(DocumentChunk))==10000
        assert db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.model==model_id()))==10000
        assert db.get(Document,public.id).scope=='all'
        assert db.get(Document,public.id).status=='indexed'
        closest=db.execute(select(DocumentChunk.id,DocumentChunk.embedding.cosine_distance(target)).where(DocumentChunk.document_id==public.id).order_by(DocumentChunk.embedding.cosine_distance(target)+0.0).limit(5)).all()
        assert {r[0] for r in closest}==wanted,closest
        db.execute(text("SET LOCAL statement_timeout='3000ms'"))
        started=time.perf_counter();result=search(db,user,query);elapsed=time.perf_counter()-started
        assert len(result)==5 and {row['chunk_id'] for row in result}==wanted
        assert all(row['document_id']==public.id for row in result)
        assert elapsed<3
        print(f'PGVECTOR_BENCHMARK chunks=10000 top_k=5 latency_ms={elapsed*1000:.2f} private_scope_filtered=true')

def test_enterprise_upgrade_keeps_legacy_data_and_is_repeatable(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as c:
        for table in ['account_emails','notifications','account_tokens','document_files','inventory_movements']:c.execute(text('DROP TABLE '+table))
        for table,columns in {'users':['phone','department','job_title','preferences','must_change_password','last_login_at'],
                              'auth_sessions':['device','ip_address'],'products':['active','version'],'sales':['reference']}.items():
            for column in columns:c.execute(text('ALTER TABLE '+table+' DROP COLUMN '+column))
        c.execute(text("INSERT INTO roles (name,permissions) VALUES ('Admin','[]')"))
        c.execute(text("INSERT INTO users (id,created_at,email,name,password_hash,role,active) VALUES ('legacy',now(),'legacy@example.test','Legacy user','hash','Admin',true)"))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0003_enterprise');migration.upgrade();migration.upgrade()
    with factory() as db:
        u=db.get(User,'legacy');assert u.email=='legacy@example.test' and u.phone=='' and u.preferences=={}
        assert u.must_change_password is False
        assert 'business.manage' in db.get(Role,'Admin').permissions
        assert set(['notifications','document_files','account_tokens','inventory_movements']).issubset(__import__('sqlalchemy').inspect(engine).get_table_names(schema=db.scalar(text('SELECT current_schema()'))))

def test_product_media_upgrade_preserves_catalog(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE product_images'))
        connection.execute(text('ALTER TABLE products DROP COLUMN description'))
        connection.execute(text("INSERT INTO products (id,created_at,sku,name,category,price,active,version) VALUES ('legacy-product',now(),'KEEP-01','Legacy product','Office',123000,true,7)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration=importlib.import_module('migrations.versions.0004_product_images')
            migration.upgrade();migration.upgrade()
    with factory() as db:
        p=db.get(Product,'legacy-product')
        assert p.sku=='KEEP-01' and p.price==123000 and p.version==7 and p.description==''
        from app.models import ProductImage
        assert list(db.scalars(select(ProductImage)))==[]

def test_finance_migration_preserves_unknown_costs_and_legacy_sales(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as c:
        for name in ['finance_imports','finance_periods','expenses']:c.execute(text('DROP TABLE '+name))
        c.execute(text('ALTER TABLE sales DROP COLUMN unit_cost'))
        c.execute(text('ALTER TABLE sales DROP COLUMN order_number'))
        c.execute(text("INSERT INTO products (id,created_at,sku,name,category,price,active,version,description) VALUES ('finance-legacy-p',now(),'FIN-OLD','Old product','Office',123000,true,1,'')"))
        c.execute(text("INSERT INTO sales (id,created_at,product_id,date,quantity,revenue) VALUES ('finance-legacy-s',now(),'finance-legacy-p',now(),2,246000)"))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0005_finance');migration.upgrade();migration.upgrade()
    from app.models import Sale,Expense
    with factory() as db:
        sale=db.get(Sale,'finance-legacy-s')
        assert sale.quantity==2 and sale.revenue==246000 and sale.unit_cost is None and sale.order_number is None
        assert list(db.scalars(select(Expense)))==[]

def test_concurrent_sales_cannot_oversell_or_double_post(pg):
    from app.enterprise import sale_create,SaleInput
    from app.models import Sale,InventoryMovement
    factory,_=pg
    with factory() as db:
        db.add(Role(name='Admin',permissions=DEFAULT_PERMISSIONS['Admin']));db.commit()
        user=User(email='seller@example.test',name='Admin',role='Admin',password_hash='unused');db.add(user);db.flush()
        product=Product(sku='SALE-PG',name='Stock test',category='Test',price=1000);db.add(product);db.flush()
        db.add(Inventory(product_id=product.id,quantity=10));db.commit();uid=user.id;pid=product.id
    def submit(reference):
        with factory() as db:
            try:return sale_create(SaleInput(product_id=pid,quantity=6,reference=reference,product_version=1),db.get(User,uid),db)['id']
            except HTTPException as e:db.rollback();return e.status_code
    same=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[same,same]))
    assert results[0]==results[1] and isinstance(results[0],str)
    assert submit(str(uuid.uuid4()))==409
    with factory() as db:
        assert db.get(Inventory,pid).quantity==4
        assert db.scalar(select(__import__('sqlalchemy').func.count()).select_from(Sale))==1
        assert db.scalar(select(__import__('sqlalchemy').func.count()).select_from(InventoryMovement))==1

def test_account_link_concurrent_use_changes_password_once(pg):
    from app.enterprise import token_link,redeem,Redeem
    from fastapi import Response
    from urllib.parse import urlsplit,parse_qs
    factory,_=pg
    with factory() as db:
        db.add(Role(name='Employee',permissions=DEFAULT_PERMISSIONS['Employee']));db.commit()
        u=User(email='recover@example.test',name='Recover',role='Employee',password_hash='unused');db.add(u);db.flush()
        link=token_link(db,u,'password_reset');db.commit();token=parse_qs(urlsplit(link['url']).fragment)['token'][0]
    def apply(_):
        with factory() as db:
            try:redeem(Redeem(token=token,password='UniquePassword@123'),Response(),db);return 200
            except HTTPException as e:db.rollback();return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(apply,[1,2]))
    assert sorted(statuses)==[200,400]


def test_agent_versions_immutable_and_publish_concurrency(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    from app import models as m
    from app.agent_management import create,AgentInput,Config,publish,Revision
    factory,engine=pg
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            importlib.import_module('migrations.versions.0006_agents').upgrade()
    with factory() as db:
        db.add(Role(name='Manager',permissions=DEFAULT_PERMISSIONS['Manager']));db.commit()
        user=User(email='agent-pg@test.example',name='Manager',role='Manager',password_hash='unused');db.add(user);db.commit();uid=user.id
        a=create(AgentInput(name='Immutable Agent',config=Config(model=__import__('app.config',fromlist=['settings']).settings.ai_model,tools=['get_inventory_status'],permissions=['inventory.read'])),user,db);aid=a['id']
    def publish_once(_):
        with factory() as db:return publish(aid,Revision(revision=1),db.get(User,uid),db)['published_version']
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(publish_once,[1,2]))==[1,1]
    with factory() as db:
        version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==aid));vid=version.id
        assert len(list(db.scalars(select(m.AgentVersion))))==1
    for statement in ["UPDATE agent_versions SET number=9 WHERE id=:id","DELETE FROM agent_versions WHERE id=:id"]:
        with engine.connect() as c:
            with pytest.raises(Exception,match='immutable'):c.execute(text(statement),{'id':vid})
            c.rollback()


def test_agent_migration_upgrades_legacy_and_unused_downgrade(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    from app import models as m
    factory,engine=pg
    with engine.begin() as c:
        for table in ['generated_files','llm_providers','mail_deliveries','mail_campaigns','gmail_send_attempts','gmail_oauth_states','gmail_connections']:c.execute(text('DROP TABLE '+table))
        for name in ['agent_version_id','agent_id','agent_snapshot','agent_draft_revision']:c.execute(text('ALTER TABLE workflows DROP COLUMN '+name))
        for table in ['agent_knowledge','agent_tools','agent_configs','agent_draft_revisions','agent_versions','agents']:c.execute(text('DROP TABLE '+table))
        for table in ['users','documents']:c.execute(text('ALTER TABLE '+table+' DROP COLUMN workspace_id'))
        c.execute(text('DROP TABLE workspaces'))
        c.execute(text("INSERT INTO roles (name,permissions) VALUES ('Admin','[\"inventory.read\"]')"))
        c.execute(text("INSERT INTO users (id,created_at,email,name,password_hash,role,active,must_change_password,preferences,phone,department,job_title) VALUES ('agent-legacy',now(),'agent-legacy@test.example','Legacy','hash','Admin',true,false,'{}','','','')"))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0006_agents');migration.upgrade();migration.upgrade()
            assert c.execute(text("SELECT workspace_id FROM users WHERE id='agent-legacy'")).scalar()=='primary'
            migration.downgrade();migration.upgrade()
    with factory() as db:
        assert db.get(User,'agent-legacy').email=='agent-legacy@test.example'
        assert 'agents.manage' in db.get(Role,'Admin').permissions
        assert db.get(m.Workspace,'primary')


def test_gmail_migration_preserves_users_and_is_repeatable(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    from app import models as m
    factory,engine=pg
    with engine.begin() as c:
        for table in ['generated_files','llm_providers','mail_deliveries','mail_campaigns','gmail_send_attempts','gmail_oauth_states','gmail_connections']:c.execute(text('DROP TABLE '+table))
        c.execute(text("INSERT INTO roles (name,permissions) VALUES ('Manager','[\"sales.read\"]')"))
        c.execute(text("INSERT INTO users (id,created_at,email,name,password_hash,role,active,must_change_password,preferences,phone,department,job_title) VALUES ('gmail-legacy',now(),'legacy-mail@test.example','Legacy','hash','Manager',true,false,'{}','','','')"))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0007_gmail');migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()
    with factory() as db:
        assert db.get(User,'gmail-legacy').email=='legacy-mail@test.example'
        assert db.get(Role,'Manager').permissions==['sales.read','mail.send']
        assert list(db.scalars(select(m.GmailConnection)))==[]


def test_bulk_mail_migration_preserves_legacy_users_and_guards_history(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as c:
        c.execute(text('DROP TABLE mail_deliveries'));c.execute(text('DROP TABLE mail_campaigns'));c.execute(text('ALTER TABLE users DROP COLUMN delivery_email'))
        c.execute(text("INSERT INTO roles (name,permissions) VALUES ('Manager','[]')"))
        c.execute(text("INSERT INTO users (id,created_at,email,name,password_hash,role,active,must_change_password,preferences,phone,department,job_title,workspace_id) VALUES ('bulk-legacy',now(),'legacy@mail.example','Legacy','hash','Manager',true,false,'{}','','','','primary')"))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0008_bulk_mail');migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()
    with factory() as db:
        u=db.get(User,'bulk-legacy');assert u.email=='legacy@mail.example' and u.delivery_email is None
        u.delivery_email='real@gmail.com';db.commit()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError,match='Mail data exists'):migration.downgrade()


def test_bulk_mail_concurrent_confirmations_reserve_quota_once(pg,monkeypatch):
    from app import models as m
    from app.mail_campaigns import Draft,Send,create_draft,send
    from app.config import settings
    factory,engine=pg
    with factory() as db:
        db.add(Role(name='Manager',permissions=DEFAULT_PERMISSIONS['Manager']));db.commit()
        u=User(name='Manager',email='bulk-pg@gmail.com',role='Manager',password_hash='unused');db.add(u);db.commit();uid=u.id
        db.add(m.GmailConnection(user_id=uid,workspace_id='primary',email='sender@gmail.com',google_sub='mock-google',credentials_ciphertext='unused',expires_at=now()+timedelta(hours=1),scopes=[]));db.commit()
        c=create_draft(db,u,Draft(subject='Concurrent',body_text='Test only',idempotency_key=str(uuid.uuid4())));db.commit();cid=c.id
    monkeypatch.setattr(settings,'mail_bulk_daily_limit',1)
    def confirm(_):
        with factory() as db:return send(cid,Send(confirmed=True,revision=1),db.get(User,uid),db)['status']
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(confirm,[1,2]))==['queued','queued']
    with factory() as db:
        assert len(list(db.scalars(select(m.Job).where(m.Job.resource==cid))))==1
        u=db.get(User,uid);other=create_draft(db,u,Draft(subject='Another',body_text='Test only',idempotency_key=str(uuid.uuid4())));db.commit()
        with pytest.raises(HTTPException) as error:send(other.id,Send(confirmed=True,revision=1),u,db)
        assert error.value.status_code==429


def test_llm_migration_is_additive_repeatable_and_guards_saved_connections(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    from app import models as m
    factory,engine=pg
    with engine.begin() as c:
        c.execute(text('DROP TABLE llm_providers'));c.execute(text('ALTER TABLE workflows DROP COLUMN model_ref'))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0009_llm_providers');migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()
        assert 'model_ref' in {i['name'] for i in __import__('sqlalchemy').inspect(c).get_columns('workflows')}
    with factory() as db:
        db.add(m.LLMProvider(workspace_id='primary',name='Test connection',base_url='https://example.com/v1',api_key_ciphertext='test-ciphertext',model_ids=['test-model'],allowed_roles=['Admin']));db.commit()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError,match='LLM configuration'):migration.downgrade()


def test_generated_files_migration_repeatable_and_preserves_history(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    from app import models as m
    factory,engine=pg
    with engine.begin() as c:
        c.execute(text('DROP TABLE generated_files'))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0010_generated_files');migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()
    with factory() as db:
        db.add(Role(name='Manager',permissions=DEFAULT_PERMISSIONS['Manager']));db.commit()
        u=User(email='files@test.example',name='File owner',role='Manager',password_hash='unused');db.add(u);db.flush()
        w=Workflow(user_id=u.id,request='Test file',idempotency_key=str(uuid.uuid4()));db.add(w);db.flush()
        db.add(m.GeneratedFile(user_id=u.id,workspace_id='primary',workflow_id=w.id,kind='docx',title='Saved',filename='saved.docx',size=4,content=b'test',sha256='0'*64,request_hash='0'*64,source={}));db.commit()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError,match='Generated files exist'):migration.downgrade()

def test_mail_attachment_migration_repeatable(pg):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib
    factory,engine=pg
    with engine.begin() as c:
        c.execute(text('ALTER TABLE mail_campaigns DROP COLUMN attachment_ids'))
        with Operations.context(MigrationContext.configure(c)):
            migration=importlib.import_module('migrations.versions.0011_mail_attachments')
            migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()

def test_chat_deletion_preserves_foreign_keys_usage_and_event_sequence(pg,monkeypatch):
    from app import models as m,usage
    from app.conversations import remove
    from conftest import FakeCache
    factory,engine=pg;monkeypatch.setattr(usage,'cache',FakeCache())
    with factory() as db:
        db.add(Role(name='Manager',permissions=DEFAULT_PERMISSIONS['Manager']));db.flush()
        u=User(email='delete@test.example',name='Owner',role='Manager',password_hash='unused');db.add(u);db.flush()
        c=m.Conversation(user_id=u.id,title='Disposable');db.add(c);db.flush()
        w=Workflow(user_id=u.id,conversation_id=c.id,request='Old text',status='completed',idempotency_key=str(uuid.uuid4()));db.add(w);db.flush()
        db.add(m.Message(conversation_id=c.id,role='user',content='Remove me'));db.add(m.UsageRecord(user_id=u.id,workflow_id=w.id,tokens=321))
        db.add(m.GeneratedFile(user_id=u.id,workspace_id='primary',workflow_id=w.id,kind='docx',title='Blob',filename='blob.docx',size=4,content=b'test',sha256='0'*64,request_hash='0'*64,source={}))
        emit(db,w,'completed',{'private':'Remove payload'});db.commit()
        before=db.scalar(select(func.max(m.WorkflowEvent.sequence)));id=c.id
        result=remove(db,u,id);assert result['files_deleted']==1
        assert db.get(m.Conversation,id) is None and db.scalar(select(m.UsageRecord.tokens))==321
        emit(db,w,'retained.receipt',{});db.commit()
        assert db.scalar(select(func.max(m.WorkflowEvent.sequence)))>before
        assert verify(db)

def test_sample_cleanup_preserves_postgres_foreign_keys_sent_history_and_agent_settings(pg,monkeypatch):
    from app import models as m,usage
    from app.remove_sample_data import remove
    from app.agent_management import Config
    from conftest import FakeCache
    factory,engine=pg;monkeypatch.setattr(usage,'cache',FakeCache())
    with factory() as db:
        db.add(Role(name='Admin',permissions=DEFAULT_PERMISSIONS['Admin']));db.flush()
        u=User(email='operator@test.example',name='Operator',role='Admin',password_hash='keep-hash');db.add(u);db.flush()
        p=Product(sku='NC-TEST-001',name='Mock',category='Mock',price=100);real=Product(sku='REAL-1',name='Real',category='Real',price=200);db.add_all([p,real]);db.flush();pid,rid=p.id,real.id
        db.add(Inventory(product_id=pid,quantity=2,threshold=1));db.add(m.Sale(product_id=pid,date=now(),quantity=1,revenue=100));db.add(m.InventoryMovement(product_id=pid,user_id=u.id,reference='fake-move',before=3,after=2,reason='Mock'))
        d=m.Document(user_id=u.id,name='Mock document',status='indexed',scope='all',content='Mock');db.add(d);db.flush();did=d.id
        db.add(m.DocumentFile(document_id=did,content=b'fake'));db.add(m.DocumentChunk(document_id=did,content='Mock',position=0,embedding=[0.0]*384,model='demo-hash-v1-384'))
        a=m.Agent(owner_id=u.id,workspace_id='primary',name='Keep Agent',visibility='workspace',status='published',published_version=1);db.add(a);db.flush()
        config=Config(model='test-model',tools=['search_internal_documents'],permissions=['documents.read'],knowledge_ids=[did]).model_dump();snap={'name':a.name,'description':'','avatar':'book','visibility':'workspace',**config}
        db.add(m.AgentConfig(agent_id=a.id,revision=1,config=config));db.add(m.AgentDraftRevision(agent_id=a.id,revision=1,snapshot=snap,created_by=u.id));db.add(m.AgentVersion(agent_id=a.id,number=1,draft_revision=1,snapshot=snap,created_by=u.id));db.add(m.AgentKnowledge(agent_id=a.id,document_id=did))
        w=Workflow(user_id=u.id,request='Mock report',status='completed',idempotency_key=str(uuid.uuid4()));db.add(w);db.flush()
        f=m.GeneratedFile(user_id=u.id,workspace_id='primary',workflow_id=w.id,kind='docx',title='Mock',filename='mock.docx',content=b'fake',size=4,sha256='0'*64,request_hash='0'*64,source={'type':'knowledge','document_ids':[did]});db.add(f);db.flush()
        w.result={'files':[{'id':f.id}],'summary':'Old result'}
        db.add(m.Report(workflow_id=w.id,user_id=u.id,title='Mock report',data={}))
        approval=m.Approval(workflow_id=w.id,user_id=u.id,status='approved',arguments={'product_id':pid},expires_at=now());db.add(approval);db.flush();db.add(m.ApprovalDecision(approval_id=approval.id,user_id=u.id,revision=1,decision='approved',reason='',arguments={}))
        c=m.MailCampaign(user_id=u.id,workspace_id='primary',workflow_id=w.id,idempotency_key=str(uuid.uuid4()),subject='Old report',body_text='Mock',attachment_ids=[f.id],status='completed');db.add(c);db.flush();cid=c.id
        db.add(m.MailDelivery(campaign_id=cid,employee_id=u.id,recipient='operator@test.example',recipient_name=u.name,status='sent',remote_id='keep-remote-id'))
        db.add(m.UsageRecord(user_id=u.id,workflow_id=w.id,tokens=123));db.add(m.SystemSetting(key='nova-commerce-business-v1',value={'product_ids':[pid],'document_ids':[did],'report_ids':[]}));db.commit()
        result=remove(db);assert result['accounts_and_connections_preserved']
        assert db.get(Product,pid) is None and db.get(Product,rid) is not None
        assert db.get(m.Document,did) is None and db.get(m.Agent,a.id).published_version==2
        assert db.get(m.AgentConfig,a.id).config['knowledge_ids']==[]
        assert db.get(m.AgentConfig,a.id).config['model']=='test-model'
        assert db.get(m.MailCampaign,cid).status=='completed' and db.get(m.MailCampaign,cid).attachment_ids==[]
        assert db.scalar(select(m.MailDelivery.remote_id))=='keep-remote-id'
        assert db.scalar(select(m.UsageRecord.tokens))==123 and verify(db)
