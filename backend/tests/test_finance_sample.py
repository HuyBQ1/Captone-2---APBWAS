from datetime import datetime
from sqlalchemy import select,func
import pytest
from app import models as m
from app.finance import TZ,finance_summary
from app.seed_finance_sample import populate,PACK
from app.config import settings
from app.audit import verify

def test_sample_completion_preserves_sales_stock_and_manual_values(env,monkeypatch):
    _,factory,_,pid=env
    with factory() as db:
        product=db.get(m.Product,pid);product.sku='AP-001'
        sale=db.scalar(select(m.Sale));sale.date=datetime(2026,7,12,tzinfo=TZ);sale.quantity=2;sale.revenue=200000
        other=m.Sale(product_id=pid,date=datetime(2026,6,13,tzinfo=TZ),quantity=1,revenue=100000,reference='MANUAL-0001',unit_cost=30000,order_number='REAL-001')
        db.add(other);db.commit();before=(sale.revenue,sale.quantity,db.get(m.Inventory,pid).quantity)
        result=populate(db)
        assert result['synthetic'] and result['counts']=={'costs':1,'order_lines':1,'expenses':6}
        assert sale.unit_cost==76000 and sale.order_number.startswith('AP-SO-20260712')
        assert other.unit_cost==30000 and other.order_number=='REAL-001'
        assert (sale.revenue,sale.quantity,db.get(m.Inventory,pid).quantity)==before
        summary=finance_summary(db,'2026-07')
        assert summary['operating_profit'] is not None and summary['order_count']==1 and summary['synthetic_finance']
        assert 'mô phỏng' in summary['summary'] and 'Phép tính:' in summary['summary'] and 'Tải Excel' not in summary['summary']
        assert populate(db)['already_imported'] and db.scalar(select(func.count()).select_from(m.Expense))==6
        assert verify(db)
    monkeypatch.setattr(settings,'demo_mode',False);monkeypatch.setattr(settings,'sample_data',False)
    with factory() as db:
        with pytest.raises(ValueError,match='SAMPLE_DATA'):populate(db)

def test_operator_finance_is_never_replaced(env):
    _,factory,_,pid=env
    with factory() as db:
        db.get(m.Product,pid).sku='AP-001';sale=db.scalar(select(m.Sale));sale.date=datetime(2026,7,12,tzinfo=TZ);sale.unit_cost=12345;sale.order_number='KEEP-ORDER'
        db.add(m.Expense(reference='KEEP-EXPENSE',date=sale.date,category='Manual',amount=1000));db.commit()
        result=populate(db)
        assert result['counts']=={'costs':0,'order_lines':0,'expenses':0}
        assert sale.unit_cost==12345 and sale.order_number=='KEEP-ORDER'
        assert db.get(m.FinancePeriod,'2026-07') is None

def test_connected_finance_questions_pass_normalized_month_to_agent(monkeypatch):
    from app import agent
    from app.schemas import Plan,PlanStep,ToolArgs
    monkeypatch.setattr(settings,'demo_mode',False)
    calls=[]
    def planner(request,context,*args,**kwargs):
        calls.append(context['month'])
        return Plan(steps=[PlanStep(tool='query_financial_summary',label='Agent chọn tính tài chính',arguments=ToolArgs(month=context['month']))]),13
    monkeypatch.setattr(agent,'connected_plan',planner)
    for question in ['tính lời lỗ doanh thu 07/2026','tháng 7 năm 2026 lãi bao nhiêu','số đơn hàng 2026-07']:
        plan,tokens=agent.make_plan(question,{})
        assert tokens==13 and plan.steps[0].tool=='query_financial_summary' and plan.steps[0].arguments.month=='2026-07'
    assert calls==['2026-07']*3
