import io
from PIL import Image
from sqlalchemy import select
from conftest import login
from app import models as m
from app.seed_product_media import populate

def photo():
    out=io.BytesIO();Image.new('RGB',(100,75),'navy').save(out,format='PNG');return out.getvalue()

def test_images_require_permissions_and_normalize_uploads(env):
    client,factory,users,id=env
    assert client.get(f'/api/business/products/{id}/image').status_code==401
    login(client,'Employee')
    assert client.put(f'/api/business/products/{id}/image',files={'file':('a.png',photo(),'image/png')}).status_code==403
    login(client,'Admin')
    assert client.put(f'/api/business/products/{id}/image',files={'file':('x.svg',b'<svg onload="alert(1)"/>','image/svg+xml')}).status_code==422
    assert client.put(f'/api/business/products/{id}/image',files={'file':('x.png',b'x'*(5*1024*1024+1),'image/png')}).status_code==413
    result=client.put(f'/api/business/products/{id}/image',files={'file':('a.png',photo(),'image/png')})
    assert result.status_code==200,result.text
    metadata=result.json();assert metadata['image_source']=='uploaded'
    login(client,'Employee')
    response=client.get(metadata['image_url']);assert response.status_code==200
    assert response.headers['content-type']=='image/webp'
    assert Image.open(io.BytesIO(response.content)).size==(100,75)
    assert client.get(metadata['image_url'],headers={'If-None-Match':response.headers['etag']}).status_code==304
    listing=client.get('/api/data/products').json()['items'][0]
    assert listing['image_url']==metadata['image_url']
    with factory() as db:
        assert db.get(m.ProductImage,id).content==response.content
        db.get(m.Role,'Employee').permissions=[];db.commit()
    assert client.get(metadata['image_url'],headers={'If-None-Match':response.headers['etag']}).status_code==403

def test_catalog_population_preserves_uploaded_images_and_is_repeatable(env):
    client,factory,users,id=env
    with factory() as db:
        product=db.get(m.Product,id);product.sku='AP-001';product.name='Tai nghe không dây Nova';db.commit()
        assert populate(db)['added']==1
        image=db.get(m.ProductImage,id)
        assert image.source=='illustration' and b'<svg' in image.content
        assert db.get(m.Product,id).description
        version=product.version
        assert populate(db)['added']==0
        assert product.version==version
    login(client,'Admin')
    assert client.put(f'/api/business/products/{id}/image',files={'file':('a.png',photo(),'image/png')}).status_code==200
    with factory() as db:
        assert populate(db)['added']==0
        assert db.get(m.ProductImage,id).source=='uploaded'
