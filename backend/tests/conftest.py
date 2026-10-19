import os
os.environ['DATABASE_URL']='sqlite://'
os.environ['REDIS_URL']='redis://localhost:6399/0'
os.environ['DEMO_MODE']='true'
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db import Base, get_db
from app.main import app
from app.models import Role, User, Product, Inventory, SystemSetting, Sale, now
from app.auth import hasher
from app.permissions import DEFAULT_PERMISSIONS
from app.usage import DEFAULT_CONFIG
from app import main, usage

class FakeCache:
    def __init__(self): self.values={}
    def incr(self,key): self.values[key]=self.values.get(key,0)+1; return self.values[key]
    def expire(self,*args): pass
    def get(self,key): return self.values.get(key)
    def setex(self,key,ttl,value): self.values[key]=value
    def ping(self): return True

@pytest.fixture
def env(monkeypatch,tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db: yield db
    app.dependency_overrides[get_db]=override
    monkeypatch.setattr(main,'Session',factory)
    fake=FakeCache(); monkeypatch.setattr(main,'cache',fake); monkeypatch.setattr(usage,'cache',fake)
    from app.config import settings
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path/'uploads'))
    users={}
    with factory() as db:
        for role,permissions in DEFAULT_PERMISSIONS.items(): db.add(Role(name=role,permissions=permissions))
        db.add(SystemSetting(key='limits',value=DEFAULT_CONFIG)); db.commit()
        password_hash=hasher.hash('Demo@123456')
        for role in DEFAULT_PERMISSIONS:
            user=User(name=role,email=role.lower()+'@apbwas.demo',role=role,password_hash=password_hash)
            db.add(user); db.flush(); users[role]=user.id
        p=Product(sku='T01',name='Test product',category='Điện tử',price=100000); db.add(p); db.flush()
        db.add(Inventory(product_id=p.id,quantity=10,threshold=20))
        db.add(Sale(product_id=p.id,date=now(),quantity=4,revenue=400000))
        db.commit(); product_id=p.id
    with TestClient(app) as client:
        yield client,factory,users,product_id
    app.dependency_overrides.clear(); engine.dispose()

def login(client,role='Manager'):
    response=client.post('/api/auth/login',json={'email':role.lower()+'@apbwas.demo','password':'Demo@123456'})
    assert response.status_code==200,response.text

def create(client,request,conversation_id=None):
    import uuid
    response=client.post('/api/workflows',json={'request':request,'idempotency_key':str(uuid.uuid4()),'conversation_id':conversation_id})
    assert response.status_code==202,response.text
    return response.json()

def execute(factory,id):
    from app.models import Workflow
    from app.workflows import process
    with factory() as db: process(db,db.get(Workflow,id))
