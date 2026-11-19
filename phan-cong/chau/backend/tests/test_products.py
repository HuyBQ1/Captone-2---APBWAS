import pytest
from fastapi import HTTPException
from app.models import Product, User, Role, SystemSetting, Workflow
from app.tools import run_tool
from app.products import lookup_products
from conftest import login, create, execute


def test_product_price_workflow_uses_database(env):
    client,factory,users,product_id=env
    with factory() as db:
        product=db.get(Product,product_id)
        product.name='Tai nghe không dây Nova'
        product.price=893456
        db.commit()
    login(client)
    wf=create(client,'Tai nghe không dây Nova có giá là bao nhiêu')
    execute(factory,wf['id'])
    response=client.get('/api/workflows/'+wf['id']).json()
    assert response['status']=='completed', response
    assert response['plan'][0]['tool']=='lookup_products'
    assert response['result']['products'][0]['price']==893456
    assert '893.456 ₫' in response['result']['summary']
    with factory() as db:
        db.get(Product,product_id).price=125000
        db.commit()
        assert lookup_products(db,{'query':'T01'})['products'][0]['price']==125000


@pytest.mark.parametrize('query',['t01','Test product','product'])
def test_lookup_by_sku_name_or_partial(env,query):
    _,factory,_,product_id=env
    with factory() as db:
        assert lookup_products(db,{'query':query})['products'][0]['id']==product_id


@pytest.mark.parametrize('query',['missing product',"' OR 1=1 --",'%', '_'])
def test_missing_or_sql_wildcards_cannot_match_everything(env,query):
    _,factory,_,_=env
    with factory() as db:
        result=lookup_products(db,{'query':query})
        assert result['products']==[]
        assert 'Không tìm thấy' in result['summary']


def test_ambiguous_lookup_is_bounded_and_never_picks_one(env):
    _,factory,_,_=env
    with factory() as db:
        for i in range(24):
            db.add(Product(sku=f'N-{i}',name=f'Nova {i:02}',category='Audio',price=1000+i))
        db.commit()
        result=lookup_products(db,{'query':'Nova'})
        assert len(result['products'])==20 and result['truncated']
        assert 'chỉ rõ tên hoặc SKU' in result['summary']
        assert all(p['name'].startswith('Nova') for p in result['products'])


def test_read_permission_and_admin_toggle_are_enforced(env):
    _,factory,users,_=env
    step={'tool':'lookup_products','arguments':{'query':'T01'}}
    with factory() as db:
        employee=db.get(User,users['Employee'])
        assert run_tool(db,employee,None,step)['products']
        role=db.get(Role,'Employee')
        role.permissions=['documents.read']
        db.commit()
        with pytest.raises(HTTPException) as error: run_tool(db,employee,None,step)
        assert error.value.status_code==403
        db.add(SystemSetting(key='tools',value={'lookup_products':False}));db.commit()
        with pytest.raises(ValueError,match='tắt'): run_tool(db,db.get(User,users['Manager']),None,step)
