"""Single-company administration; all durable state is stored in PostgreSQL."""
import hashlib,secrets
from datetime import timedelta
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import Field
from sqlalchemy import select,delete,update
from sqlalchemy import func
from .db import get_db
from . import models as m
from .schemas import StrictModel,UserInput
from .auth import current_user,hasher,utc
from .permissions import require
from .audit import audit
from .config import settings

router=APIRouter(prefix='/api')
def record(row):
    from .main import data
    return data(row)

class Invite(StrictModel):
    email: str=Field(pattern=r'^\S+@\S+\.\S+$',max_length=180)
    name: str=Field(min_length=2,max_length=120)
    role: Literal['Admin','Manager','Employee']='Employee'
class Redeem(StrictModel):
    token: str=Field(min_length=30,max_length=128)
    password: str=Field(min_length=10,max_length=128)
class Preferences(StrictModel):
    theme: Literal['light','dark']='light'
    sidebar_collapsed: bool=False
class Company(StrictModel):
    name: str=Field(min_length=2,max_length=120)
    email: str=Field(default='',max_length=180,pattern=r'^(?:\S+@\S+\.\S+)?$')
    phone: str=Field(default='',max_length=30)
    address: str=Field(default='',max_length=300)
    tax_code: str=Field(default='',max_length=30)
class ProductInput(StrictModel):
    sku: str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,29}$')
    name: str=Field(min_length=2,max_length=120)
    category: str=Field(min_length=1,max_length=80)
    price: int=Field(ge=0,le=99999999999999)
    threshold: int=Field(default=20,ge=0,le=100000)
    active: bool=True
    version: int=Field(default=1,ge=1)
    description: str=Field(default='',max_length=2000)
class SaleInput(StrictModel):
    product_id: str
    quantity: int=Field(ge=1,le=100000)
    reference: str=Field(min_length=10,max_length=100,pattern=r'^[A-Za-z0-9][A-Za-z0-9._/-]+$')
    product_version: int=Field(ge=1)
    unit_cost: int | None=Field(default=None,ge=0,le=99999999999999)

def token_link(db,target,purpose):
    db.execute(update(m.AccountToken).where(m.AccountToken.user_id==target.id,m.AccountToken.used_at.is_(None)).values(used_at=m.now()))
    raw=secrets.token_urlsafe(40)
    expiry=m.now()+timedelta(hours=24 if purpose=='activation' else 1)
    db.add(m.AccountToken(user_id=target.id,token_hash=hashlib.sha256(raw.encode()).hexdigest(),purpose=purpose,expires_at=expiry))
    return {'url':settings.frontend_origin.rstrip('/')+'/reset-password#token='+raw,'expires_at':expiry.isoformat(),
            'delivery':'manual','message':'Sao chép và gửi riêng cho người nhận. Liên kết chỉ dùng một lần; thao tác cấp liên kết này chưa gửi email.'}

@router.post('/admin/invitations')
def invite(body:Invite,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    target=m.User(email=body.email.strip().lower(),name=body.name.strip(),role=body.role,workspace_id=user.workspace_id,must_change_password=True,password_hash=hasher.hash(secrets.token_urlsafe(40)))
    db.add(target);db.flush()
    link=token_link(db,target,'activation')
    audit(db,user,'account.invited',target.id,{'email':target.email,'role':target.role});db.commit()
    return {**link,'user':record(target)}

@router.post('/admin/users/{id}/recovery')
def recovery(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'users.manage')
    target=db.scalar(select(m.User).where(m.User.id==id).with_for_update())
    if not target or not target.active:raise HTTPException(404,'Không tìm thấy tài khoản đang hoạt động.')
    link=token_link(db,target,'password_reset')
    audit(db,user,'account.recovery_issued',target.id);db.commit()
    return link

@router.post('/auth/redeem')
def redeem(body:Redeem,response:Response,db=Depends(get_db)):
    digest=hashlib.sha256(body.token.encode()).hexdigest()
    ticket=db.scalar(select(m.AccountToken).where(m.AccountToken.token_hash==digest))
    if not ticket or ticket.purpose not in ('activation','password_reset'):raise HTTPException(400,'Liên kết không hợp lệ hoặc đã hết hạn.')
    target=db.scalar(select(m.User).where(m.User.id==ticket.user_id).with_for_update())
    if not target or not target.active:raise HTTPException(400,'Liên kết không hợp lệ hoặc đã hết hạn.')
    consumed=db.execute(update(m.AccountToken).where(m.AccountToken.id==ticket.id,m.AccountToken.used_at.is_(None),m.AccountToken.expires_at>m.now()).values(used_at=m.now()))
    if consumed.rowcount!=1:raise HTTPException(400,'Liên kết không hợp lệ hoặc đã hết hạn.')
    target.password_hash=hasher.hash(body.password);target.must_change_password=False
    db.execute(delete(m.AuthSession).where(m.AuthSession.user_id==target.id))
    db.execute(update(m.AccountToken).where(m.AccountToken.user_id==target.id,m.AccountToken.used_at.is_(None)).values(used_at=m.now()))
    response.delete_cookie('apbwas_session',path='/')
    audit(db,target,'account.password_activated',target.id);db.commit()
    return {'ok':True}

@router.get('/auth/sessions')
def sessions(request:Request,user=Depends(current_user),db=Depends(get_db)):
    digest=hashlib.sha256(request.cookies.get('apbwas_session','').encode()).hexdigest()
    return {'items':[{**record(s),'current':s.token_hash==digest} for s in db.scalars(select(m.AuthSession).where(m.AuthSession.user_id==user.id,m.AuthSession.expires_at>m.now()).order_by(m.AuthSession.created_at.desc()))]}

@router.delete('/auth/sessions/{id}')
def revoke(id:str,user=Depends(current_user),db=Depends(get_db)):
    session=db.get(m.AuthSession,id)
    if not session or session.user_id!=user.id:raise HTTPException(404,'Không tìm thấy phiên đăng nhập.')
    db.delete(session);audit(db,user,'session.revoked',id);db.commit()
    return {'ok':True}

@router.put('/auth/preferences')
def preferences(body:Preferences,user=Depends(current_user),db=Depends(get_db)):
    user.preferences=body.model_dump();db.commit()
    return user.preferences

@router.get('/company')
def company(user=Depends(current_user),db=Depends(get_db)):
    row=db.get(m.SystemSetting,'company')
    return {key:row.value.get(key,'') for key in Company.model_fields} if row else {'name':'Nova Commerce','email':'','phone':'','address':'','tax_code':''}

@router.put('/company')
def company_edit(body:Company,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    row=db.get(m.SystemSetting,'company')
    if not row:row=m.SystemSetting(key='company',value={});db.add(row)
    row.value={**row.value,**body.model_dump()};audit(db,user,'company.updated','company',body.model_dump());db.commit()
    return body.model_dump()

@router.post('/business/products')
def product_create(body:ProductInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'business.manage')
    from .shop_connection import block_local_write
    block_local_write(db)
    product=m.Product(**body.model_dump(exclude={'threshold','version'}));db.add(product);db.flush()
    db.add(m.Inventory(product_id=product.id,quantity=0,threshold=body.threshold))
    audit(db,user,'product.created',product.id,{'sku':product.sku});db.commit()
    return record(product)

@router.put('/business/products/{id}')
def product_update(id:str,body:ProductInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'business.manage')
    from .shop_connection import block_local_write
    block_local_write(db)
    product=db.scalar(select(m.Product).where(m.Product.id==id).with_for_update())
    if not product:raise HTTPException(404,'Không tìm thấy sản phẩm.')
    if product.version!=body.version:raise HTTPException(409,'Sản phẩm vừa thay đổi. Tải lại trước khi lưu.')
    for key,value in body.model_dump(exclude={'threshold','version'}).items():setattr(product,key,value)
    product.version+=1
    inventory=db.get(m.Inventory,id);inventory.threshold=body.threshold
    audit(db,user,'product.updated',id,{'sku':product.sku,'active':product.active});db.commit()
    return record(product)

@router.post('/business/sales')
def sale_create(body:SaleInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'business.manage')
    from .shop_connection import block_local_write
    block_local_write(db)
    require(db,user,'sales.read')
    product=db.scalar(select(m.Product).where(m.Product.id==body.product_id).with_for_update())
    existing=db.scalar(select(m.Sale).where(m.Sale.reference==body.reference))
    if existing:
        if existing.product_id!=body.product_id or existing.quantity!=body.quantity or existing.unit_cost!=body.unit_cost:raise HTTPException(409,'Mã giao dịch đã dùng với nội dung khác.')
        return record(existing)
    if not product or not product.active:raise HTTPException(409,'Sản phẩm không tồn tại hoặc đã ngừng kinh doanh.')
    if product.version!=body.product_version:raise HTTPException(409,'Giá/sản phẩm vừa thay đổi. Tải lại trước khi ghi nhận.')
    inventory=db.scalar(select(m.Inventory).where(m.Inventory.product_id==product.id).with_for_update())
    if not inventory or inventory.quantity<body.quantity:raise HTTPException(409,'Không đủ tồn kho để ghi nhận giao dịch.')
    before=inventory.quantity;inventory.quantity-=body.quantity;inventory.version+=1
    sale=m.Sale(product_id=product.id,date=m.now(),quantity=body.quantity,revenue=Decimal(product.price)*body.quantity,reference=body.reference,unit_cost=body.unit_cost,order_number=body.reference.upper())
    db.add(sale);db.flush()
    db.add(m.InventoryMovement(product_id=product.id,user_id=user.id,reference=body.reference,before=before,after=inventory.quantity,reason='Giao dịch bán hàng '+sale.id))
    audit(db,user,'sale.posted',sale.id,{'product_id':product.id,'quantity':body.quantity,'revenue':str(sale.revenue),'before':before,'after':inventory.quantity});db.commit()
    return record(sale)

@router.get('/business/movements')
def movements(user=Depends(current_user),db=Depends(get_db),page_number:int=1):
    require(db,user,'inventory.read')
    page_number=max(1,page_number)
    rows=db.execute(select(m.InventoryMovement,m.Product.name,m.Product.sku).join(m.Product,m.Product.id==m.InventoryMovement.product_id)
                    .order_by(m.InventoryMovement.created_at.desc()).offset((page_number-1)*10).limit(10)).all()
    return {'items':[{**record(movement),'product_name':name,'sku':sku} for movement,name,sku in rows],
            'total':db.scalar(select(func.count()).select_from(m.InventoryMovement)),'page':page_number,'size':10}

@router.get('/notifications')
def notifications(user=Depends(current_user),db=Depends(get_db),page_number:int=1):
    from .main import page
    return {**page(db,select(m.Notification).where(m.Notification.user_id==user.id).order_by(m.Notification.created_at.desc()),page_number),
            'unread':db.scalar(select(func.count()).select_from(m.Notification).where(m.Notification.user_id==user.id,m.Notification.read_at.is_(None)))}

@router.post('/notifications/{id}/read')
def notification_read(id:str,user=Depends(current_user),db=Depends(get_db)):
    item=db.get(m.Notification,id)
    if not item or item.user_id!=user.id:raise HTTPException(404,'Không tìm thấy thông báo.')
    item.read_at=m.now();db.commit()
    return {'ok':True}

@router.get('/documents/{id}/download')
def download(id:str,user=Depends(current_user),db=Depends(get_db)):
    from .main import document
    from urllib.parse import quote
    from pathlib import Path
    item=document(id,user,db);blob=db.get(m.DocumentFile,id)
    if not blob:raise HTTPException(404,'Tài liệu này chỉ có nội dung văn bản, không có file gốc.')
    mime={'.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.pdf':'application/pdf','.txt':'text/plain'}
    return Response(blob.content,media_type=mime.get(Path(item['name']).suffix.lower(),'application/octet-stream'),
                    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(item['name'],safe='')})
