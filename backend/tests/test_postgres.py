"""Opt-in PostgreSQL-only verification; each run uses an isolated random schema."""
import os, uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine,text,select
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

URL=os.environ.get('PG_TEST_DATABASE_URL','')
pytestmark=pytest.mark.skipif(not URL,reason='PG_TEST_DATABASE_URL chưa có; không dùng SQLite làm bằng chứng concurrency/pgvector.')

@pytest.fixture
def pg(monkeypatch):
    engine=create_engine(URL,pool_pre_ping=True)
    schema='apbwas_test_'+uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        connection.execute(text('CREATE SCHEMA '+schema))
    scoped=create_engine(URL,connect_args={'options':'-csearch_path='+schema+',public'},pool_pre_ping=True)
    Base.metadata.create_all(scoped)
    monkeypatch.setattr(db_module,'read_engine',scoped)
    factory=sessionmaker(scoped,expire_on_commit=False)
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
