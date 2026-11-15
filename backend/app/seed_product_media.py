"""Local vector product illustrations for the fictional Nova Commerce catalog."""
import hashlib,html,json
from sqlalchemy import select,text
from .db import Session
from . import models as m
from .audit import audit

def illustration(name,sku):
    n=name.lower()
    def box(x,y,w,h,fill='#27354b',rx=12):
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'
    def line(x,y,a,b):return f'<path d="M{x} {y}L{a} {b}" stroke="#74849a" stroke-width="7" stroke-linecap="round"/>'
    screen=box(105,76,270,172)+box(115,86,250,150,'url(#screen)',5)+box(227,248,26,39,'#74849a',3)+box(178,283,124,10,'#27354b',5)
    if 'giá treo' in n:body=box(145,75,190,35)+line(240,110,195,172)+line(195,172,270,225)+box(240,220,60,50)
    elif 'kệ màn' in n:body=box(90,165,300,25,'#b6875d',4)+box(110,190,18,85)+box(350,190,18,85)
    elif 'màn hình' in n:body=screen
    elif 'bàn phím' in n:
        body=box(65,135,350,120)
        for y in range(149,225,24):
            for x in range(80,390,28):body+=box(x,y,22,17,'#dee6f0',3)
        body+=box(165,226,150,15,'#8f83e8',3)
    elif 'tai nghe' in n:body='<path d="M150 205V155a90 90 0 0 1 180 0v50" fill="none" stroke="#27354b" stroke-width="24"/>'+box(128,162,48,100,'#6e63c9',22)+box(304,162,48,100,'#6e63c9',22)
    elif 'chuột' in n:body=box(173,75,134,210,'#425574',65)+line(240,78,240,150)+box(232,109,16,39,'#b7bef4',7)
    elif 'đèn' in n:body=box(137,273,190,14)+line(232,270,232,180)+line(232,180,292,106)+'<path d="M270 95Q312 80 336 140L245 140Z" fill="#6d63c8"/><path d="M260 148L220 255H368L325 148" fill="#fff0b8" opacity=".6"/>'
    elif 'ghế' in n:body=box(160,65,160,132,'#4c6970',34)+box(145,204,190,32,'#4c6970',14)+line(240,237,240,280)+line(240,280,160,303)+line(240,280,320,303)+line(145,208,125,170)+line(335,208,355,170)
    elif 'bàn ' in n:body=box(65,137,350,35,'#b6875d',6)+box(88,172,22,132)+box(370,172,22,132)
    elif 'tủ' in n or 'kệ sách' in n:
        body=box(126,56,228,250,'#9c765c',5)
        for y in [65,144,223]:body+=box(136,y,208,72,'#d6c4af',3)+box(229,y+22,23,6,'#475569',2)
        if 'locker' in n:
            for y in [65,144,223]:body+=box(238,y,4,72,'#9c765c',0)
    elif 'quạt' in n:body='<circle cx="240" cy="140" r="85" fill="#d5dfe7" stroke="#52667e" stroke-width="7"/>' + ''.join(f'<ellipse cx="240" cy="110" rx="20" ry="54" fill="#6676b4" transform="rotate({a} 240 140)"/>' for a in [0,120,240])+line(240,225,240,283)+box(174,280,132,15)
    elif 'ấm' in n:body='<path d="M166 115H290L314 275Q240 305 150 275Z" fill="#a9bccb"/><path d="M291 140Q381 130 315 235" fill="none" stroke="#27354b" stroke-width="20"/>'+box(180,97,100,17)
    elif 'bình' in n or 'hộp cơm' in n:body=box(175,85,130,210,'#679a97',30)+box(175,75,130,40,'#27354b',12)+box(197,154,86,50,'#b6d7ce',8)
    elif 'bảng viết' in n:body=box(72,68,336,198,'#9baabd',4)+box(80,76,320,182,'white',1)+line(125,265,110,310)+line(355,265,370,310)+line(120,130,280,130)+line(120,160,340,160)
    elif 'webcam' in n or 'camera' in n:body=box(105,115,270,110)+ '<circle cx="240" cy="170" r="43" fill="#0c1528"/><circle cx="240" cy="170" r="29" fill="#507a9e"/><circle cx="231" cy="160" r="9" fill="#b9e7ff"/>'+box(205,225,70,40)+box(175,264,130,12)
    elif 'micro' in n:body=''.join(box(x,82,44,135,'#27354b',22)+box(x,82,44,51,'#8894a6',22)+line(x+22,220,x+22,280)+box(x-14,280,72,9) for x in [154,284])
    elif 'loa' in n:body=box(105,130,270,105,'#38465c',40)+''.join(f'<circle cx="{x}" cy="182" r="28" fill="#152135" stroke="#6b7e96" stroke-width="3"/>' for x in [165,315])+box(230,162,20,8,'#9b8af2',4)
    elif 'router' in n:body=box(115,171,250,70)+line(145,171,118,70)+line(335,171,362,70)+line(210,171,210,66)+line(270,171,270,66)+box(135,199,52,7,'#70e1bc',3)
    elif 'switch' in n or 'hub' in n or 'ổ cắm' in n:
        body=box(75,137,330,95,'#75859a',10)
        for x in range(98,375,43):body+=box(x,167,28,30,'#202d41',3)+box(x+4,170,20,5,'#e3bc72',0)
    elif 'wi-fi' in n or 'access point' in n:body=box(150,80,180,210,'#e6eaf2',60)+box(213,250,54,5,'#5abfa5',2)
    elif 'cáp' in n:body=''.join(f'<ellipse cx="235" cy="185" rx="{r}" ry="{r*.72}" fill="none" stroke="#4f6c9c" stroke-width="9"/>' for r in [50,68,86,104])+line(335,200,382,260)+box(367,251,25,40,'#a8bacb',4)
    elif 'bút' in n:body=''.join(f'<g transform="rotate(25 {x} 180)">'+box(x,75,16,200,c,5)+f'<path d="M{x} 275L{x+8} 295L{x+16} 275" fill="#334155"/></g>' for x,c in [(150,'#4c6ba2'),(225,'#8470bf'),(300,'#3b8b80')])
    elif 'giấy ghi' in n:body=''.join(box(x,y,120,125,c,2) for x,y,c in [(105,87,'#ffc781'),(165,125,'#b6dbcf'),(230,168,'#e2c2eb')])
    elif 'sổ' in n or 'bìa' in n or 'giấy in' in n:body=box(139,67,208,236,'#dddfe7',4)+box(128,57,208,236,'#fefefe',4)+box(128,57,16,236,'#7262b9',1)+box(167,110,130,16,'#d5cfea',2)+box(167,145,100,9,'#cbd5e1',2)+box(167,169,130,9,'#cbd5e1',2)
    elif 'usb ' in n:body=box(120,141,210,80,'#53667d',22)+box(330,149,55,64,'#b8c6d6',3)+box(345,158,10,12,'#53667d',1)+box(365,158,10,12,'#53667d',1)
    elif 'thẻ nhớ' in n:body='<path d="M160 70H283L325 115V290H160Z" fill="#27354b"/>'+box(175,145,135,90,'#8b73c2',2)+''.join(box(x,80,10,36,'#dcbf7e',1) for x in range(177,274,18))
    elif 'ssd' in n or 'ổ cứng' in n:body=box(149,70,182,226,'#3d516d',22)+box(165,86,150,194,'#536780',12)+box(217,258,46,9,'#1f2937',3)+box(215,123,50,6,'#acb6c5',3)
    elif 'máy in' in n or 'máy quét' in n or 'máy ép' in n:
        body=box(145,50,190,130,'#fff',4)+box(95,135,290,136,'#53667d',16)+box(117,151,246,29,'#a6b5c9',5)+box(150,213,180,89,'#fafbff',2)+box(165,232,147,5,'#c1cad9',1)+box(165,250,130,5,'#c1cad9',1)
    elif 'trình chiếu' in n:body=box(199,63,82,240,'#27354b',30)+'<circle cx="240" cy="125" r="23" fill="#667b99"/>'+box(224,177,32,14,'#8c80d7',5)
    else:body=box(145,65,190,235,'#dbe3ec',18)+box(165,85,150,110,'#465b75',10)+''.join(box(x,225,12,45,'#7c8b9d',3) for x in range(175,308,24))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360"><defs><linearGradient id="screen" x2="1" y2="1"><stop stop-color="#8182cc"/><stop offset="1" stop-color="#1c455c"/></linearGradient></defs><rect width="480" height="360" rx="24" fill="#f3f5fa"/><circle cx="240" cy="180" r="146" fill="#e9edf7"/><ellipse cx="240" cy="314" rx="150" ry="12" fill="#dce2ee"/>{body}<text x="24" y="338" font-family="Arial,sans-serif" font-size="12" fill="#6b7280">NOVA COMMERCE · {html.escape(sku)}</text></svg>').encode()

def populate(db):
    if db.get(m.SystemSetting,'sample-data-removed-v1'):return {'added':0,'sample_data_removed':True}
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730031)'))
    added=0
    for p in db.scalars(select(m.Product).order_by(m.Product.sku)):
        if not p.sku.startswith(('NC-','AP-')):continue
        if not db.get(m.ProductImage,p.id):
            raw=illustration(p.name,p.sku)
            db.add(m.ProductImage(product_id=p.id,content=raw,mime_type='image/svg+xml',sha256=hashlib.sha256(raw).hexdigest(),source='illustration'));added+=1
        if not p.description:
            p.description=f'{p.name} thuộc danh mục {p.category} trong bộ sưu tập Nova Commerce. Mã hàng {p.sku}. Giá niêm yết và tồn kho được cập nhật từ hệ thống; liên hệ bộ phận kinh doanh để xác nhận cấu hình và điều kiện cung cấp.'
            p.version+=1
    if added:audit(db,'system','product.illustrations_added','nova-commerce',{'count':added})
    db.commit()
    return {'added':added,'total_images':len(list(db.scalars(select(m.ProductImage.product_id))))}

if __name__=='__main__':
    with Session() as db:print(json.dumps(populate(db)))
