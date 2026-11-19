import io,zipfile
from datetime import datetime
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from sqlalchemy import select,func
from conftest import login
from app import models as m
from app.finance import dataset,summarize
from app.finance_excel import export_workbook,write,NS,N
from app.audit import verify
TZ=ZoneInfo('Asia/Ho_Chi_Minh')

def fixture_data(factory,id):
    with factory() as db:
        sale=db.scalar(select(m.Sale));sale.date=datetime(2026,10,31,23,59,tzinfo=TZ)
        sale.quantity=2;sale.revenue=200000;sale.unit_cost=None;sale.order_number=None;db.commit()
        return sale.id

def edited(raw,updates):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
        for name in z.namelist():
            b=z.read(name)
            if name in updates:
                root=ET.fromstring(b)
                for address,value in updates[name].items():write(root,address,value)
                b=ET.tostring(root,encoding='utf-8')
            dest.writestr(name,b)
    return out.getvalue()

def test_monthly_missing_data_orders_and_zero_cost(env):
    client,factory,users,id=env;sid=fixture_data(factory,id)
    login(client,'Employee');assert client.get('/api/finance/summary?month=2026-10').status_code==403
    login(client,'Manager');s=client.get('/api/finance/summary?month=2026-10').json()
    assert s['revenue']==200000 and s['sale_lines']==1 and s['order_count'] is None
    assert s['cost_of_goods'] is None and s['operating_profit'] is None and s['missing_cost_lines']==1
    with factory() as db:
        sale=db.get(m.Sale,sid);sale.unit_cost=0;sale.order_number='SO-01'
        db.add(m.Sale(product_id=id,date=datetime(2026,10,1,tzinfo=TZ),quantity=1,revenue=100000,unit_cost=60000,order_number='SO-01'))
        db.add(m.Sale(product_id=id,date=datetime(2026,11,1,tzinfo=TZ),quantity=1,revenue=999999,unit_cost=1,order_number='NEXT'))
        db.add(m.Expense(reference='CP-1',date=datetime(2026,10,31,tzinfo=TZ),category='Vận hành',amount=30000))
        db.add(m.FinancePeriod(month='2026-10',expenses_confirmed=True));db.commit()
    s=client.get('/api/finance/summary?month=2026-10').json()
    assert s['order_count']==1 and s['sale_lines']==2 and s['units_sold']==3
    assert s['cost_of_goods']==60000 and s['operating_profit']==210000 and s['margin']==0.7
    assert client.get('/api/finance/summary?month=0000-10').status_code==422

def test_excel_roundtrip_preview_commit_idempotency_and_db_persistence(env):
    client,factory,users,id=env;sid=fixture_data(factory,id);login(client,'Admin')
    response=client.get('/api/finance/export?month=2026-10');assert response.status_code==200,response.text
    raw=response.content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        assert root.find(".//s:c[@r='B9']/s:f",N) is not None
        assert root.find(".//s:c[@r='B9']/s:v",N).text=='200000'
        assert root.find(".//s:c[@r='B20']/s:v",N).text=='Chua du du lieu'
    raw=edited(raw,{'xl/worksheets/sheet1.xml':{'B5':1},'xl/worksheets/sheet2.xml':{'D6':'SO-001','G6':60000},
                    'xl/worksheets/sheet4.xml':{'A6':'CP-001','B6':46326,'C6':'Vận hành','D6':30000,'E6':'Tiền thuê'}})
    # Use an actual October serial (2026-10-31).
    from app.finance_excel import serial
    raw=edited(raw,{'xl/worksheets/sheet4.xml':{'B6':serial('2026-10-31T00:00:00+07:00')}})
    preview=client.post('/api/finance/imports/preview?month=2026-10',files={'file':('finance.xlsx',raw)})
    assert preview.status_code==200,preview.text
    assert preview.json()['cost_lines']==1 and preview.json()['expense_rows']==1
    with factory() as db:assert db.get(m.Sale,sid).unit_cost is None
    iid=preview.json()['id'];assert client.post(f'/api/finance/imports/{iid}/commit').status_code==200
    assert client.post(f'/api/finance/imports/{iid}/commit').json()['existing']
    result=client.get('/api/finance/summary?month=2026-10').json()
    assert result['operating_profit']==50000 and result['order_count']==1 and result['revenue']==200000
    with factory() as db:
        assert db.get(m.FinanceImport,iid).content==raw
        assert db.scalar(select(func.count()).select_from(m.Expense))==1
        assert db.get(m.Inventory,id).quantity==10 and db.get(m.Sale,sid).quantity==2
        assert verify(db)
    assert client.post('/api/finance/imports/preview?month=2026-10',files={'file':('old.xlsx',raw)}).status_code==422
    login(client,'Manager');assert client.post(f'/api/finance/imports/{iid}/commit').status_code==403

def test_excel_stale_preview_and_tampered_sales_are_rejected(env):
    client,factory,users,id=env;fixture_data(factory,id);login(client,'Admin')
    raw=client.get('/api/finance/export?month=2026-10').content
    bad=edited(raw,{'xl/worksheets/sheet2.xml':{'F6':999999}})
    assert client.post('/api/finance/imports/preview?month=2026-10',files={'file':('x.xlsx',bad)}).status_code==422
    assert client.post('/api/finance/imports/preview?month=2026-10',files={'file':('x.xlsx',b'not excel')}).status_code==422
    preview=client.post('/api/finance/imports/preview?month=2026-10',files={'file':('x.xlsx',raw)}).json()
    expense={'reference':'CP-NEW','date':'2026-10-30T00:00:00+07:00','category':'Thuê văn phòng','amount':10000}
    assert client.post('/api/finance/expenses',json=expense).status_code==200
    assert client.post('/api/finance/expenses',json=expense).json()['existing']
    assert client.post(f"/api/finance/imports/{preview['id']}/commit").status_code==409
    s=client.get('/api/finance/summary?month=2026-10').json();assert not s['expenses_confirmed']
    assert client.put('/api/finance/period/2026-10',json={'version':s['period_version'],'confirmed':True}).status_code==200
    assert client.put('/api/finance/period/2026-10',json={'version':s['period_version'],'confirmed':True}).status_code==409

def test_agent_finance_tool_uses_database_and_permission(env):
    client,factory,users,id=env;fixture_data(factory,id)
    from app.agent import make_plan
    from app.tools import run_tool
    plan,_=make_plan('Tính lời lỗ và số đơn tháng 2026-10',{})
    assert plan.steps[0].tool=='query_financial_summary'
    with factory() as db:
        result=run_tool(db,db.get(m.User,users['Manager']),None,{'tool':'query_financial_summary','arguments':{'month':'2026-10'}})
        assert result['revenue']==200000 and 'Chưa đủ dữ liệu' in result['summary']

def test_multirow_workbook_roundtrip_and_formula_rows(env):
    client,factory,users,id=env;fixture_data(factory,id)
    with factory() as db:
        for index in range(45):db.add(m.Sale(product_id=id,date=datetime(2026,10,15,tzinfo=TZ),quantity=1,revenue=10000,unit_cost=1000,order_number='ORDER-'+str(index//2)))
        db.commit()
    login(client,'Admin');raw=client.get('/api/finance/export?month=2026-10').content
    result=client.post('/api/finance/imports/preview?month=2026-10',files={'file':('many.xlsx',raw)})
    assert result.status_code==200,result.text
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
        rows=root.findall('s:sheetData/s:row',N)
        numbers=[int(r.attrib['r']) for r in rows]
        assert numbers==sorted(set(numbers))
        assert root.find(".//s:c[@r='H40']/s:f",N).text=='IF(I40=1,E40*G40,"")'
        assert root.find(".//s:c[@r='J40']/s:f",N).text=='IF(D40="",0,IF(COUNTIFS($D$6:D40,D40)=1,1,0))'
