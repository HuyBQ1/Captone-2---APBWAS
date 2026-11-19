import copy
from datetime import datetime,timezone
import pytest,httpx
from sqlalchemy import select,func
from app import shop_connection as shop,models as m
from app.llm_models import protect
from app.config import settings
from app.finance import dataset,summarize
from conftest import login

@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setattr(settings,'llm_encryption_key',__import__('pydantic').SecretStr('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='))
    month=m.now().astimezone(shop.TZ).strftime('%Y-%m')
    date=datetime.strptime(month+'-01','%Y-%m-%d').replace(tzinfo=shop.TZ).astimezone(timezone.utc)
    return {'company':{'name':'Nova Commerce','as_of':m.now().isoformat()},'products':[{'id':12,'sku':'NOVA-12','name':'Nova product','category_id':1,'price':100,'active':True,'description':'New source','image':'https://images.example.test/p.jpg'}],'stocks':{12:{'stock':8}},'categories':{1:'Điện tử'},'sales':[{'id':shop.identity('sale','1'),'reference':'nova-api:1:delivery:0','product_id':shop.identity('product',12),'date':date,'quantity':3,'revenue':300,'unit_cost':60,'order_number':'NOVA-1'},{'id':shop.identity('sale','2'),'reference':'nova-api:2:return:0','product_id':shop.identity('product',12),'date':date,'quantity':-1,'revenue':-100,'unit_cost':60,'order_number':'NOVA-2'}],'reports':{month:{'net_revenue':200,'cogs':120,'gross_profit':80,'recorded_expenses':20,'operating_result':None,'orders_count':5,'period':{'start':date.isoformat()},'completeness':{'complete':False,'expenses_complete':False}}},'order_count':5}

def configured(db):
    db.add(m.SystemSetting(key=shop.KEY,value={'enabled':True,'api_key_ciphertext':protect('nova-test-only-key'),'revision':1}));db.commit()

def test_replacement_is_explicit_and_atomic(env,snapshot,monkeypatch):
    client,factory,users,old_product=env
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:
        configured(db)
        with pytest.raises(ValueError,match='xác nhận'):shop.sync(db,users['Admin'])
        db.rollback()
        assert db.get(m.Product,old_product)
        count=db.scalar(select(func.count()).select_from(m.User))
        result=shop.sync(db,users['Admin'],replace=True)
        assert result['counts']=={'products':1,'orders':5,'sale_events':2}
        assert db.get(m.Product,old_product) is None
        assert db.scalar(select(func.count()).select_from(m.User))==count
        assert __import__('pathlib').Path(result['backup']).is_file()
        month=next(iter(snapshot['reports']));summary=summarize(dataset(db,month))
        assert summary['revenue']==200 and summary['cost_of_goods']==120
        assert summary['operating_profit'] is None and summary['created_order_count']==5
        assert summary['order_count']==2  # Distinct delivery/return orders, not creations.
        assert 'api_key_ciphertext' not in result and 'nova-test-only-key' not in str(result)
        shop.sync(db,users['Admin'])
        assert db.scalar(select(func.count()).select_from(m.Sale))==2
        assert db.scalar(select(func.count()).select_from(m.Expense))==1

def test_bad_upstream_never_erases_old_business_data(env,snapshot,monkeypatch):
    client,factory,users,old=env
    def fail(key):raise ValueError('API key thiếu quyền đọc dữ liệu.')
    monkeypatch.setattr(shop,'fetch_snapshot',fail)
    login(client,'Admin')
    r=client.put('/api/connections/shop',json={'api_key':'nova-test-only-key','replace_existing':True})
    assert r.status_code==422
    with factory() as db:
        assert db.get(m.Product,old)
        assert shop.setting(db) is None

def test_scope_visibility_and_read_only_mirror(env,snapshot,monkeypatch):
    client,factory,users,_=env
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:configured(db);shop.sync(db,users['Admin'],replace=True)
    login(client,'Employee')
    response=client.get('/api/connections/shop');assert response.status_code==200
    assert 'periods' not in response.json() and 'orders' not in response.json()['counts']
    assert client.post('/api/connections/shop/sync').status_code==403
    login(client,'Admin')
    with factory() as db:
        with pytest.raises(__import__('fastapi').HTTPException) as err:shop.block_local_write(db)
        assert err.value.status_code==409

def test_upstream_failure_keeps_successful_snapshot(env,snapshot,monkeypatch):
    _,factory,users,_=env
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:
        configured(db);shop.sync(db,users['Admin'],replace=True)
        row=shop.setting(db);row.value={**row.value,'last_attempt':'2000-01-01T00:00:00+00:00'};db.commit()
        def fail(key):raise RuntimeError('must-not-leak-secret')
        monkeypatch.setattr(shop,'fetch_snapshot',fail);shop.sync_if_due(db)
        assert db.scalar(select(func.count()).select_from(m.Sale))==2
        assert 'must-not-leak-secret' not in str(shop.public(db))
        assert shop.public(db)['last_error']

def test_reports_show_synced_sales_without_a_saved_workflow_report(env,snapshot,monkeypatch):
    client,factory,users,_=env
    login(client,'Manager')
    path='/api/reports/nova-sales'
    assert client.get(path).json()=={'synced_at':None,'sync_failed':False,'periods':[]}
    month=next(iter(snapshot['reports']))
    detail_path=f'{path}/{month}'
    assert client.get(detail_path).status_code==404
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:
        configured(db)
        sync=shop.sync(db,users['Admin'],replace=True)
        row=shop.setting(db)
        row.value={**row.value,'last_error':'upstream failure'}
        db.add(m.Sale(product_id=snapshot['sales'][0]['product_id'],
                      date=snapshot['sales'][0]['date'],quantity=1,revenue=500,reference='local-sale'))
        db.commit()
    assert client.get('/api/reports').json()['items']==[]
    response=client.get(path)
    assert response.status_code==200
    assert response.json()=={
        'synced_at':sync['last_sync'],'sync_failed':True,
        'periods':[{'month':month,'revenue':200,'orders_created':5}],
    }
    detail=client.get(detail_path)
    assert detail.status_code==200
    assert detail.json()=={
        'month':month,'synced_at':sync['last_sync'],'sync_failed':True,
        'revenue':200,'orders_created':5,'sales_amount':300,'refund_amount':100,
        'cost_of_goods':120,'expenses':20,'operating_profit':None,
        'products':[{'sku':'NOVA-12','name':'Nova product','category':'Điện tử','sold':3,'returned':1,
                     'sales_amount':300,'refund_amount':100,'revenue':200}],
        'categories':[{'category':'Điện tử','revenue':200}],
    }
    login(client,'Employee')
    assert client.get(path).status_code==403
    assert client.get(detail_path).status_code==403

def test_client_rejects_missing_scope_without_echoing_remote_body(monkeypatch):
    original=httpx.Client
    monkeypatch.setattr(shop.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(403,json={'error':'secret-from-upstream'})),**kw))
    with shop.NovaClient('nova-test-only-key') as api:
        with pytest.raises(ValueError,match='thiếu quyền') as err:api.get('/api/v1/integration/company')
    assert 'secret-from-upstream' not in str(err.value)

def test_fetch_reconciles_delivery_and_return_and_rejects_changed_totals(monkeypatch):
    month=m.now().astimezone(shop.TZ).strftime('%Y-%m');date=month+'-01T00:00:00+07:00'
    data={'products':[{'id':1,'sku':'P1','name':'Product','category_id':2,'price':100}], 'inventory':[{'id':1,'stock':9}], 'orders':[{'id':1,'status':'returned','total':90,'created_at':date,'recognized_at':date,'returned_at':date,'lines':[{'product_id':1,'quantity':1,'price':100,'discount':10,'cost':50}]}]}
    reports={'net_revenue':0,'cogs':0,'gross_profit':0,'recorded_expenses':20,'operating_result':None,'orders_count':1,'period':{'start':date},'currency':'VND','completeness':{'expenses_complete':False}}
    class API:
        def __init__(self,key):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def pages(self,path):return data.get(path,[])
        def get(self,path,**kw):
            if path.endswith('/company'):return {'currency':'VND','timezone':'Asia/Ho_Chi_Minh'}
            if path.endswith('/categories'):return [{'id':2,'name':'Category'}]
            return reports
    monkeypatch.setattr(shop,'NovaClient',API)
    result=shop.fetch_snapshot('not-a-real-key')
    assert sum(s['revenue'] for s in result['sales'])==0
    assert len(result['sales'])==2 and result['sales'][1]['quantity']==-1
    reports['net_revenue']=999
    with pytest.raises(ValueError,match='đối chiếu'):shop.fetch_snapshot('not-a-real-key')

def test_orders_are_filtered_by_creation_not_delivery_date(env,snapshot,monkeypatch):
    _,factory,users,_=env
    today=m.now().astimezone(shop.TZ).isoformat()
    snapshot['orders']=[{'order_number':'NOVA-123','status':'pending','date':today,'total':100,'units':1},{'order_number':'NOVA-124','status':'delivered','date':'2020-01-01T00:00:00+07:00','total':200,'units':2}]
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:
        configured(db);shop.sync(db,users['Admin'],replace=True)
        result=shop.order_summary(db,{'query':'today'})
        assert result['created_order_count']==1 and result['rows'][0]['status']=='pending'
        assert shop.order_summary(db,{'query':'delivered'})['created_order_count']==1
        assert shop.order_summary(db,{'query':'NOVA-123'})['rows'][0]['total']==100

def test_generated_policy_is_retired_but_user_document_is_preserved(env,snapshot,monkeypatch):
    _,factory,users,_=env
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    with factory() as db:
        old=m.Document(user_id=users['Admin'],name='Old generated policy',content='old data',status='indexed')
        own=m.Document(user_id=users['Admin'],name='User policy',content='keep me',status='indexed')
        db.add_all([old,own]);db.flush()
        db.add(m.SystemSetting(key='nova-commerce-operational-v2',value={'document_ids':[old.id]}));db.commit()
        configured(db);shop.sync(db,users['Admin'],replace=True)
        db.refresh(old);db.refresh(own)
        assert old.status=='archived' and not old.content
        assert own.status=='indexed' and own.content=='keep me'

def test_unfinished_groups_only_open_statuses(env):
    _,factory,_,_=env
    with factory() as db:
        orders=[{'order_number':'NOVA-'+str(i),'status':s,'date':'2026-11-11T03:00:00+07:00'} for i,s in enumerate(('pending','confirmed','shipping','delivered','cancelled','returned'))]
        db.add(m.SystemSetting(key='nova-shop-orders-v1',value={'orders':orders,'synced_at':'2026-11-11T04:00:00+07:00'}));db.commit()
        result=shop.order_summary(db,{'query':'unfinished'})
        assert result['created_order_count']==3
        assert {o['status'] for o in result['rows']}=={'pending','confirmed','shipping'}


@pytest.mark.parametrize('query',['NOVA-1','#NC00001'])
def test_exact_order_number_does_not_match_longer_ids(env,query):
    _,factory,_,_=env
    with factory() as db:
        orders=[{'order_number':f'NOVA-{i}','status':'pending','date':'2026-11-11T03:00:00+07:00'} for i in (1,10,100)]
        db.add(m.SystemSetting(key='nova-shop-orders-v1',value={'orders':orders,'synced_at':'2026-11-11T04:00:00+07:00'}))
        db.commit()
        assert [row['order_number'] for row in shop.order_summary(db,{'query':query})['rows']]==['NOVA-1']

def test_live_order_query_sees_new_order_and_combines_date_with_status(env,snapshot,monkeypatch):
    _,factory,users,_=env
    monkeypatch.setattr(shop,'fetch_snapshot',lambda key:copy.deepcopy(snapshot))
    today=m.now().astimezone(shop.TZ).date().isoformat()
    class API:
        def __init__(self,key):assert key=='nova-test-only-key'
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def pages(self,path):
            assert path=='orders'
            return [{'id':386,'created_at':today+'T03:50:00+07:00','status':'pending','payment_status':'unpaid','total':1180000,'lines':[{'quantity':2}]}, {'id':385,'created_at':today+'T03:18:00+07:00','status':'delivered','total':7990000,'lines':[{'quantity':1}]}]
    with factory() as db:
        configured(db);shop.sync(db,users['Admin'],replace=True)
        monkeypatch.setattr(shop,'NovaClient',API)
        result=shop.order_summary(db,{'date':today,'order_status':'pending','month':'2026-05'},fresh=True)
        assert result['live_source'] and result['month'] is None
        assert result['created_order_count']==1 and result['rows'][0]['order_number']=='NOVA-386'
        assert result['rows'][0]['total']==1180000
        assert shop.order_summary(db,{'date':today},fresh=True)['created_order_count']==2
