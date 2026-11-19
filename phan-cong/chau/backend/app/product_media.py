"""Authenticated images. Original uploads are decoded and re-encoded, never served verbatim."""
import hashlib,io,warnings
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Request,Response
from PIL import Image,ImageOps,UnidentifiedImageError
from sqlalchemy import select
from .db import get_db
from .auth import current_user
from .permissions import require
from .audit import audit
from . import models as m

router=APIRouter(prefix='/api/business/products')

def image_metadata(db,ids):
    result={id:{'image_url':f'/api/business/products/{id}/image?v={digest}',
                'image_source':source} for id,digest,source in db.execute(
        select(m.ProductImage.product_id,m.ProductImage.sha256,m.ProductImage.source).where(m.ProductImage.product_id.in_(ids)))}
    from .shop_connection import setting
    from urllib.parse import urlsplit
    row=setting(db)
    for id,url in (row.value.get('images',{}) if row else {}).items():
        if id not in ids or not isinstance(url,str):continue
        p=urlsplit(url)
        if p.scheme=='https' and p.hostname and not p.username and not p.password:
            result[id]={'image_url':url,'image_source':'Nova Commerce API'}
    return result

@router.get('/{id}/image')
def image(id:str,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'inventory.read')
    item=db.get(m.ProductImage,id)
    if not item:raise HTTPException(404,'Sản phẩm chưa có ảnh.')
    headers={'Cache-Control':'private, no-cache','ETag':'"'+item.sha256+'"',
             'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"}
    if request.headers.get('if-none-match')==headers['ETag']:return Response(status_code=304,headers=headers)
    return Response(item.content,media_type=item.mime_type,headers=headers)

@router.put('/{id}/image')
async def upload(id:str,file:UploadFile=File(...),user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'business.manage')
    from .shop_connection import block_local_write
    block_local_write(db)
    if not db.get(m.Product,id):raise HTTPException(404,'Không tìm thấy sản phẩm.')
    content=await file.read(5*1024*1024+1)
    if len(content)>5*1024*1024:raise HTTPException(413,'Ảnh tối đa 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as original:
                if original.format not in ('JPEG','PNG','WEBP') or original.width*original.height>16000000:
                    raise ValueError()
                picture=ImageOps.exif_transpose(original).convert('RGB')
                picture.thumbnail((1400,1400))
                output=io.BytesIO();picture.save(output,format='WEBP',quality=88)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError):
        raise HTTPException(422,'Chọn ảnh JPG, PNG hoặc WebP hợp lệ, tối đa 16 megapixel.')
    raw=output.getvalue();item=db.get(m.ProductImage,id)
    if not item:item=m.ProductImage(product_id=id);db.add(item)
    item.content=raw;item.mime_type='image/webp';item.source='uploaded'
    item.sha256=hashlib.sha256(raw).hexdigest();item.updated_at=m.now()
    audit(db,user,'product.image_updated',id,{'sha256':item.sha256});db.commit()
    return image_metadata(db,[id])[id]
