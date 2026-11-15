"""Bounded, parameterized product reads; the model never supplies SQL or prices."""
import re
from sqlalchemy import select, func, or_
from .models import Product


def product_query(value):
    value=(value or '').strip().strip('?.!')
    value=re.sub(r'^(?:cho (?:tôi|mình) (?:biết|xem)\s+)?(?:giá (?:bán )?(?:của )?|tra cứu (?:sản phẩm |hàng hóa )?)', '', value, flags=re.I)
    value=re.sub(r'\s+(?:có giá|giá bán|giá là|giá bao nhiêu|bao nhiêu tiền|có giá là).*$','',value,flags=re.I)
    value=re.sub(r'\s+(?:là )?bao nhiêu$','',value,flags=re.I)
    return value.strip().strip('"\'“”')


def lookup_products(db,args):
    statement=matching_products(db,args)
    return product_result(db.scalars(statement.order_by(Product.name,Product.id).limit(21)).all())


def matching_products(db,args):
    query=product_query(args.get('query'))
    statement=select(Product).where(Product.active.is_(True))
    if args.get('product_id'):
        statement=statement.where(Product.id==args['product_id'])
    elif query:
        # Prefer an exact SKU/name; partial matches may legitimately be ambiguous.
        exact=or_(func.lower(Product.sku)==query.lower(),func.lower(Product.name)==query.lower())
        if db.scalar(select(Product.id).where(exact).limit(1)):
            return statement.where(exact)
        escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        pattern='%'+escaped+'%'
        statement=statement.where(or_(Product.name.ilike(pattern,escape='\\'),
                                      Product.sku.ilike(pattern,escape='\\'),
                                      Product.category.ilike(pattern,escape='\\')))
    return statement


def inventory_query(value):
    value=(value or '').strip().strip('?.!')
    value=re.sub(r'^(?:(?:kiểm tra|xem|cho (?:tôi|mình) biết|tồn kho|số lượng|của|sản phẩm|sku)\s*)+','',value,flags=re.I)
    value=re.sub(r'\s+(?:còn|tồn kho|có)?\s*(?:lại )?(?:bao nhiêu|mấy).*$','',value,flags=re.I)
    return value.strip()


def product_result(products):
    truncated=len(products)>20
    items=[{'id':p.id,'sku':p.sku,'name':p.name,'category':p.category,'price':int(p.price),'currency':'VND'} for p in products[:20]]
    if not items:
        summary='Không tìm thấy hàng hóa phù hợp trong dữ liệu được phép truy cập. Bạn hãy kiểm tra lại tên hoặc SKU sản phẩm.'
    elif len(items)==1:
        p=items[0]
        price=f"{p['price']:,}".replace(',','.')
        summary=f"{p['name']} (SKU: {p['sku']}) có giá bán **{price} ₫** theo dữ liệu hàng hóa hiện tại."
    else:
        summary=f"Tìm thấy {'hơn 20' if truncated else len(items)} sản phẩm phù hợp. Bạn có thể chỉ rõ tên hoặc SKU để xem giá một sản phẩm.\n\n"
        for p in items:
            price=f"{p['price']:,}".replace(',','.')
            summary+=f"- {p['name']} (SKU: {p['sku']}): **{price} ₫**\n"
        if truncated: summary+='\nChỉ hiển thị 20 sản phẩm đầu tiên; hãy thu hẹp tên hoặc danh mục.'
    return {'products':items,'truncated':truncated,'source':'products • Truy vấn SQL chỉ đọc, có tham số',
            'summary':summary}
