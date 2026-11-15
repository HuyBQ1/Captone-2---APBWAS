from datetime import date,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from sqlalchemy import select,func
import pytest
from app import models as m
from app import business_data_pack as pack
from app.config import settings
from app.audit import verify
from app.retrieval import search
from conftest import login

def test_pack_reconciles_sales_inventory_reports_and_original_documents(env):
    client,factory,users,legacy_id=env
    with factory() as db:
        legacy_quantity=db.get(m.Inventory,legacy_id).quantity
        # A pre-existing future-dated record must not enter an as-of snapshot.
        db.add(m.Sale(product_id=legacy_id,date=datetime(2026,11,3,9,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')),quantity=1,revenue=999999999999))
        manifest=pack.import_pack(db,date(2026,11,2))
        assert manifest['counts']['products']==48
        assert manifest['counts']['sales']>3000
        assert manifest['counts']['documents']==26
        assert manifest['counts']['reports']==11
        assert manifest['counts']['low_stock_products']==8
        assert manifest['counts']['out_of_stock_products']==4
        assert db.get(m.Inventory,legacy_id).quantity==legacy_quantity
        imported=db.scalars(select(m.Sale).where(m.Sale.reference.like('NCV1-S-%'))).all()
        assert sum(int(s.revenue) for s in imported)==manifest['imported_sales_revenue_vnd']
        prices={p.id:p.price for p in db.scalars(select(m.Product).where(m.Product.id.in_(manifest['product_ids'])))}
        for sale in imported:
            assert sale.date<=m.now() and sale.quantity>0
            assert sale.revenue==prices[sale.product_id]*sale.quantity
        for pid in manifest['product_ids']:
            movements=db.scalars(select(m.InventoryMovement).where(m.InventoryMovement.product_id==pid).order_by(m.InventoryMovement.created_at)).all()
            quantity=0
            for movement in movements:
                assert movement.before==quantity
                assert movement.after>=0
                quantity=movement.after
            inventory=db.get(m.Inventory,pid)
            assert inventory.quantity==quantity and inventory.version==1+len(movements)
        for did in manifest['document_ids']:
            doc=db.get(m.Document,did);assert doc.status=='indexed' and doc.chunks>0
            assert db.get(m.DocumentFile,did).content==doc.content.encode('utf-8')
        for rid in manifest['report_ids']:
            report=db.get(m.Report,rid)
            assert report.data['total']==sum(r['revenue'] for r in report.data['rows'])
            if report.data['month']=='2026-11':
                assert report.data['partial_period'] is True
                assert report.data['total']<999999999999
        assert verify(db)
        # Re-running an explicit import does not change records or consume AI tokens.
        before={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [m.Product,m.Sale,m.Document,m.Report,m.AuditLog,m.Workflow]}
        assert pack.import_pack(db,date(2026,11,2))['already_imported'] is True
        assert before=={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [m.Product,m.Sale,m.Document,m.Report,m.AuditLog,m.Workflow]}

def test_pack_scope_and_business_sales_search(env):
    client,factory,users,_=env
    with factory() as db:
        pack.import_pack(db,date(2026,11,2))
        employee=db.get(m.User,users['Employee'])
        results=search(db,employee,'quy trình nhập kho kiểm đếm')
        assert results
        assert all(db.get(m.Document,r['document_id']).scope=='all' for r in results)
        private=db.scalar(select(m.Document).where(m.Document.scope=='Admin'))
        private_id=private.id
    login(client,'Manager')
    r=client.get('/api/data/sales?q=NC-EL-001&month=2026-10');assert r.status_code==200
    body=r.json();assert body['total']>=6
    assert all(row['sku']=='NC-EL-001' and row['product_name'] and row['reference'].startswith('NCV1-S-202610') for row in body['items'])
    assert client.get('/api/data/sales?month=2026-13').status_code==422
    assert client.get('/api/data/sales?month=0000-01').status_code==422
    assert client.get('/api/documents/'+private_id).status_code==403
    login(client,'Employee');assert client.get('/api/data/sales?q=NC-EL-001').status_code==403

def test_pack_requires_sample_mode_and_rolls_back_partial_import(env,monkeypatch):
    _,factory,_,_=env
    monkeypatch.setattr(settings,'demo_mode',False);monkeypatch.setattr(settings,'sample_data',False)
    with factory() as db:
        with pytest.raises(ValueError,match='SAMPLE_DATA'):pack.import_pack(db,date(2026,11,2))
    monkeypatch.setattr(settings,'demo_mode',True)
    def unavailable(_):raise RuntimeError('Synthetic test failure while indexing')
    monkeypatch.setattr(pack,'embed',unavailable)
    with factory() as db:
        with pytest.raises(RuntimeError,match='indexing'):pack.import_pack(db,date(2026,11,2))
        db.rollback()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.Product).where(m.Product.sku.like('NC-%')))==0
        assert db.get(m.SystemSetting,pack.PACK) is None
