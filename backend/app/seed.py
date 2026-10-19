import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .db import Session
from .models import *
from .auth import hasher
from .permissions import DEFAULT_PERMISSIONS
from .config import settings
from .audit import audit
from .usage import DEFAULT_CONFIG
from .retrieval import index_document
from .workflows import process

def seed():
    with Session() as db:
        for name,values in DEFAULT_PERMISSIONS.items():
            if not db.get(Role,name): db.add(Role(name=name,permissions=values))
        for name in set(p for values in DEFAULT_PERMISSIONS.values() for p in values):
            if not db.get(Permission,name): db.add(Permission(name=name))
        if not db.get(SystemSetting,'limits'): db.add(SystemSetting(key='limits',value=DEFAULT_CONFIG))
        db.commit()
        if not settings.demo_mode:
            print('Connected Mode: roles seeded; create first admin via bootstrap_admin.py with an explicit password.')
            return
        for role,name in [('Admin','Dương Gia Huy'),('Manager','Nguyễn Minh Anh'),('Employee','Trần Quang Huy')]:
            email=role.lower()+'@apbwas.demo'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password_hash=hasher.hash(settings.demo_password)))
        db.commit()
        admin=db.scalar(select(User).where(User.role=='Admin'))
        manager=db.scalar(select(User).where(User.role=='Manager'))
        employee=db.scalar(select(User).where(User.role=='Employee'))
        products=[('AP-001','Tai nghe không dây Nova','Điện tử',890000,12),('AP-002','Bàn phím cơ Orbit','Điện tử',1450000,65),
                  ('AP-003','Đèn bàn Halo','Gia dụng',450000,8),('AP-004','Ghế làm việc Ergo','Nội thất',2900000,34),
                  ('AP-005','Bình giữ nhiệt Daily','Gia dụng',320000,110),('AP-006','Bàn làm việc Studio','Nội thất',3450000,7),
                  ('AP-007','Chuột không dây Air','Điện tử',650000,84),('AP-008','Kệ sách Modular','Nội thất',1250000,52)]
        today=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
        for index,(sku,name,category,price,quantity) in enumerate(products):
            p=db.scalar(select(Product).where(Product.sku==sku))
            if p: continue
            p=Product(sku=sku,name=name,category=category,price=price); db.add(p); db.flush()
            db.add(Inventory(product_id=p.id,quantity=quantity,threshold=20))
            for ago in range(6):
                number=today.year*12+today.month-1-ago
                year,month=number//12,number%12+1
                for day in [2,7,12]:
                    units=8+(index*7+ago*3+day)%35
                    if ago==0: units+=5
                    db.add(Sale(product_id=p.id,date=datetime(year,month,day,12,tzinfo=today.tzinfo),quantity=units,revenue=units*price))
        db.commit()
        for name,scope,content in [
            ('Chính sách nghỉ phép 2026.txt','all','CHÍNH SÁCH NGHỈ PHÉP — DỮ LIỆU GIẢ LẬP\nNhân viên có 12 ngày nghỉ phép hưởng lương mỗi năm. Đăng ký trước ít nhất 3 ngày làm việc. Quản lý trực tiếp phê duyệt trên hệ thống. Nghỉ khẩn cấp cần thông báo quản lý trong ngày. Ngày phép chưa dùng được chuyển tối đa 5 ngày sang quý I năm sau.'),
            ('Quy trình quản lý tồn kho.txt','all','QUY TRÌNH TỒN KHO — DỮ LIỆU GIẢ LẬP\nNgưỡng cảnh báo mặc định là 20 đơn vị. Mọi thay đổi số lượng tồn kho phải được Manager hoặc Admin phê duyệt. Kiểm tra lại phiên bản dữ liệu trước khi cập nhật.'),
            ('Hướng dẫn báo cáo kinh doanh.txt','Manager','TÀI LIỆU GIẢ LẬP — Báo cáo doanh thu lấy số liệu từ đơn hàng và nhóm theo danh mục. Số tiền tính bằng VND. Không kết luận nguyên nhân biến động khi chưa có dữ liệu chứng minh.')]:
            if not db.scalar(select(Document).where(Document.name==name)):
                doc=Document(user_id=admin.id,name=name,scope=scope,content=content); db.add(doc); db.commit()
                index_document(db,doc); db.add(Job(resource=doc.id,kind='document',status='done')); db.commit()
                audit(db,admin,'document.indexed',doc.id,{'chunks':doc.chunks}); db.commit()
        def workflow(key,request,user,days=0):
            if db.scalar(select(Workflow).where(Workflow.idempotency_key==key)): return
            wf=Workflow(user_id=user.id,request=request,idempotency_key=key,created_at=now()-timedelta(days=days))
            db.add(wf); db.commit()
            audit(db,user,'workflow.requested',wf.id,{'request':request}); db.commit()
            process(db,wf)
        for offset in range(9):
            workflow('seed-revenue-'+str(offset),'Phân tích doanh thu tháng này và so sánh với tháng trước.',manager,offset)
        workflow('seed-policy','Tóm tắt chính sách nghỉ phép và dẫn nguồn.',employee,1)
        workflow('seed-inventory','Kiểm tra sản phẩm sắp hết hàng.',employee)
        first=db.scalar(select(Product).where(Product.sku=='AP-001'))
        workflow('seed-approval',f'Đề xuất điều chỉnh tồn kho product_id={first.id} quantity=50',manager)
        workflow('seed-denied','Phân tích doanh thu tháng này.',employee,2)
        print('Demo seed complete. Password supplied by DEMO_PASSWORD; default Demo@123456.')

if __name__=='__main__': seed()
