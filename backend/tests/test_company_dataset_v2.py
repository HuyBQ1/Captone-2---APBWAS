from datetime import datetime
from io import BytesIO
from sqlalchemy import select,delete,func
from app import models as m
from app.company_dataset_v2 import populate,TZ,KEY
from app.remove_sample_data import protected
from app.retrieval import word_text,search
import pytest

def empty_business(db):
    for table in (m.Sale,m.Inventory,m.Product):db.execute(delete(table))
    db.commit()

def test_generated_business_is_consistent_idempotent_and_preserves_settings(env):
    _,factory,users,_=env
    with factory() as db:
        empty_business(db)
        db.add(m.SystemSetting(key='sample-data-removed-v1',value={'removed':True}));db.commit()
        before=protected(db)
        result=populate(db,datetime(2026,11,8,2,tzinfo=TZ))
        assert result['origin']=='generated' and not result['real_transactions']
        assert result['counts']['products']==28 and result['counts']['documents']==6
        assert result['counts']['sales']>1000 and len(result['periods'])==11
        assert result['counts']['orders']<result['counts']['sales']
        assert before==protected(db) and db.get(m.SystemSetting,'sample-data-removed-v1')
        for p in db.scalars(select(m.Product)):
            movements=list(db.scalars(select(m.InventoryMovement).where(m.InventoryMovement.product_id==p.id).order_by(m.InventoryMovement.created_at)))
            current=0
            for movement in movements:
                assert movement.before==current and movement.after>=0
                current=movement.after
            assert current==db.get(m.Inventory,p.id).quantity
            sold=sum(s.quantity for s in db.scalars(select(m.Sale).where(m.Sale.product_id==p.id)))
            assert sold==-sum(x.after-x.before for x in movements if x.after<x.before)
        for month,totals in result['periods'].items():
            assert totals['operating_profit']==totals['revenue']-totals['cost']-totals['expenses']
            assert db.get(m.FinancePeriod,month).expenses_confirmed==(month!='2026-11')
        assert populate(db)['already_imported']
        assert db.scalar(select(func.count()).select_from(m.Product))==28
        user=db.get(m.User,users['Manager'])
        found=search(db,user,'nhân viên được nghỉ phép bao nhiêu ngày')
        assert any('NC-HR-101' in x['name'] for x in found)
        for doc in db.scalars(select(m.Document)):
            raw=db.get(m.DocumentFile,doc.id).content
            assert word_text(BytesIO(raw))==doc.content
            assert doc.status=='indexed' and doc.chunks>0
            assert 'demo' not in doc.content.lower() and 'mô phỏng' not in doc.content.lower()

def test_generated_import_refuses_existing_business_data(env):
    _,factory,*_=env
    with factory() as db:
        with pytest.raises(ValueError,match='trống'):populate(db)
        assert not db.get(m.SystemSetting,KEY)

def test_existing_user_leave_policy_is_preserved_and_not_contradicted(env):
    _,factory,users,_=env
    with factory() as db:
        empty_business(db)
        doc=m.Document(user_id=users['Admin'],name='Nghi Phep.docx',content='Nhân viên được nghỉ phép 5 ngày trong 1 tháng',status='indexed',scope='all')
        db.add(doc);db.commit();doc_id=doc.id
        result=populate(db,datetime(2026,11,8,2,tzinfo=TZ))
        assert result['counts']['documents']==5
        assert db.get(m.Document,doc_id).content=='Nhân viên được nghỉ phép 5 ngày trong 1 tháng'
        assert not db.scalar(select(m.Document.id).where(m.Document.name.contains('NC-HR-101')))
