"""Fill an Artifact Tool-authored XLSX template and parse its literal input cells."""
import io,zipfile,hashlib,json,re,copy
from pathlib import Path
from datetime import datetime,timedelta
from xml.etree import ElementTree as ET
from fastapi import HTTPException
from . import models as m

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N={'s':NS};ET.register_namespace('',NS)
SALES_LIMIT=5000;EXPENSE_LIMIT=1000;STOCK_LIMIT=2000

def baseline(data):
    body={k:data[k] for k in ('month','sales','expenses','expenses_confirmed','period_version')}
    return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def serial(value):
    return (datetime.fromisoformat(value).replace(tzinfo=None)-datetime(1899,12,30)).total_seconds()/86400

def write(root,address,value,cache=False):
    number=int(re.search(r'\d+',address).group())
    data=root.find('s:sheetData',N)
    row=data.find(f"s:row[@r='{number}']",N)
    if row is None:row=ET.SubElement(data,f'{{{NS}}}row',{'r':str(number)})
    cell=row.find(f"s:c[@r='{address}']",N)
    if cell is None:cell=ET.SubElement(row,f'{{{NS}}}c',{'r':address})
    for child in list(cell):
        if not cache or child.tag!=f'{{{NS}}}f':cell.remove(child)
    cell.attrib.pop('t',None)
    if value is None:return
    if isinstance(value,str):
        if cache:cell.set('t','str');ET.SubElement(cell,f'{{{NS}}}v').text=value
        else:
            cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,f'{{{NS}}}is'),f'{{{NS}}}t').text=value
    else:ET.SubElement(cell,f'{{{NS}}}v').text=str(int(value) if isinstance(value,bool) else value)

def seed_row(root,number):
    if number==6:return
    data=root.find('s:sheetData',N);template=data.find("s:row[@r='6']",N)
    existing=data.find(f"s:row[@r='{number}']",N)
    if existing is not None:data.remove(existing)
    row=copy.deepcopy(template);row.set('r',str(number))
    for cell in row:
        cell.set('r',re.sub(r'6$',str(number),cell.attrib['r']))
        formula=cell.find('s:f',N)
        if formula is not None:formula.text=re.sub(r'(?<!\$)6\b',str(number),formula.text)
        else:
            for child in list(cell):cell.remove(child)
            cell.attrib.pop('t',None)
    index=next((i for i,child in enumerate(data) if int(child.attrib['r'])>number),len(data))
    data.insert(index,row)

def export_workbook(data):
    from .finance import summarize
    if len(data['sales'])>SALES_LIMIT or len(data['expenses'])>EXPENSE_LIMIT or len(data['inventory'])>STOCK_LIMIT:
        raise HTTPException(422,'Kỳ vượt giới hạn file: 5.000 dòng bán, 1.000 chi phí hoặc 2.000 SKU. Cần chia kỳ trước khi xuất.')
    template=Path(__file__).parent/'assets/finance-template.xlsx'
    with zipfile.ZipFile(template) as z:parts={name:z.read(name) for name in z.namelist()}
    sheets=[ET.fromstring(parts[f'xl/worksheets/sheet{i}.xml']) for i in range(1,5)]
    summary,sales,stock,expenses=sheets
    write(summary,'B3',data['month']);write(summary,'B4',data['as_of']);write(summary,'B5',int(data['expenses_confirmed']));write(summary,'B7',baseline(data))
    if data.get('source')=='Nova Commerce API':
        write(summary,'D3','Nguồn website Nova Commerce; đồng bộ '+str(data.get('synced_at','')))
        write(summary,'D14','Số đơn có phát sinh giao/hoàn trong kỳ. Đơn tạo mới: '+str(data.get('created_order_count','chưa có dữ liệu')))
        write(summary,'D19','Chi phí tổng hợp theo tháng từ API; xem chi tiết tại website bán hàng.')
    if data.get('synthetic_finance'):write(summary,'D3','DỮ LIỆU TÀI CHÍNH MÔ PHỎNG NOVA COMMERCE')
    seen=set()
    for r,s in enumerate(data['sales'],6):
        seed_row(sales,r)
        vals=[s['id'],serial(s['date']),s['sku'],s['order_number'],s['quantity'],s['revenue'],s['unit_cost']]
        for col,value in zip('ABCDEFG',vals):write(sales,f'{col}{r}',value)
        known=s['unit_cost'] is not None
        write(sales,f'H{r}',s['quantity']*s['unit_cost'] if known else '',True)
        write(sales,f'I{r}',int(known),True)
        first=bool(s['order_number'] and s['order_number'] not in seen);seen.add(s['order_number'])
        write(sales,f'J{r}',int(first),True)
    for r,s in enumerate(data['inventory'],6):
        seed_row(stock,r)
        for col,key in zip('ABCDEF',['sku','name','category','quantity','threshold','price']):write(stock,f'{col}{r}',s[key])
        write(stock,f'G{r}',int(s['quantity']<=s['threshold']),True)
        write(stock,f'H{r}',int(s['quantity']==0),True)
    for r,e in enumerate(data['expenses'],6):
        seed_row(expenses,r)
        for col,value in zip('ABCDE',[e['reference'],serial(e['date']),e['category'],e['amount'],e['note']]):write(expenses,f'{col}{r}',value)
    result=summarize(data)
    values={9:result['revenue'],10:result['sale_lines'],11:result['units_sold'],12:result['known_orders'],
            13:result['unassigned_order_lines'],14:result['order_count'],15:result['known_cost'],16:result['missing_cost_lines'],
            17:result['cost_of_goods'],18:result['gross_profit'],19:result['expenses'],20:result['operating_profit'],
            21:result['margin'],23:result['stock_units'],24:result['low_stock'],25:result['out_of_stock']}
    for row,value in values.items():write(summary,f'B{row}','Chua du du lieu' if value is None else value,True)
    for i,sheet in enumerate(sheets,1):parts[f'xl/worksheets/sheet{i}.xml']=ET.tostring(sheet,encoding='utf-8',xml_declaration=True)
    workbook=ET.fromstring(parts['xl/workbook.xml'])
    calc=workbook.find('s:calcPr',N)
    if calc is None:calc=ET.SubElement(workbook,f'{{{NS}}}calcPr')
    calc.set('calcMode','auto');calc.set('fullCalcOnLoad','1')
    parts['xl/workbook.xml']=ET.tostring(workbook,encoding='utf-8',xml_declaration=True)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in parts.items():z.writestr(name,raw)
    return out.getvalue()

def parse_inputs(raw,data):
    from .finance import TZ,dates
    def fail(message):raise HTTPException(422,message)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            if len(names)>1000 or len(set(names))!=len(names) or sum(i.file_size for i in z.infolist())>40*1024*1024 or any(i.flag_bits&1 for i in z.infolist()):fail('File Excel vượt giới hạn cấu trúc hoặc bị mã hóa.')
            if any('vbaProject' in n or 'externalLinks/' in n for n in names):fail('Không nhận macro hoặc liên kết dữ liệu ngoài.')
            def xml(name):
                b=z.read(name)
                if b'<!DOCTYPE' in b or b'<!ENTITY' in b:fail('XML không hợp lệ.')
                return ET.fromstring(b)
            strings=[''.join(t.itertext()) for t in xml('xl/sharedStrings.xml').findall('s:si',N)] if 'xl/sharedStrings.xml' in names else []
            wb=xml('xl/workbook.xml');rels=xml('xl/_rels/workbook.xml.rels')
            targets={r.attrib['Id']:r.attrib['Target'] for r in rels}
            def sheet(name):
                entry=next(s for s in wb.find('s:sheets',N) if s.attrib['name']==name)
                target=targets[entry.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                if '..' in target:fail('Đường dẫn sheet không hợp lệ.')
                root=xml(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
                cells={}
                for c in root.findall('.//s:sheetData/s:row/s:c',N):
                    address=c.attrib['r']
                    if not re.fullmatch(r'[A-Z]{1,3}[1-9]\d{0,6}',address) or address in cells:fail('Địa chỉ ô Excel không hợp lệ hoặc bị trùng.')
                    v=c.find('s:v',N);value=v.text if v is not None else ''
                    if c.attrib.get('t')=='s':value=strings[int(value)]
                    elif c.attrib.get('t')=='inlineStr':value=''.join(c.find('s:is',N).itertext())
                    cells[address]=(value,c.find('s:f',N) is not None)
                return cells
            summary,sales,expenses=sheet('TongHop'),sheet('BanHang'),sheet('ChiPhi')
    except HTTPException:raise
    except (zipfile.BadZipFile,KeyError,ValueError,IndexError,StopIteration,ET.ParseError,AttributeError,NotImplementedError,RuntimeError):fail('File không đúng mẫu Excel Nova Commerce. Hãy xuất file từ hệ thống trước.')
    def value(cells,addr):
        v,f=cells.get(addr,('',False))
        if f:fail(f'Ô {addr} là công thức. Dùng Paste Values cho ô dữ liệu nhập.')
        return v or ''
    def integer(v,label,optional=False):
        if v=='' and optional:return None
        if not re.fullmatch(r'\d+(?:\.0+)?',str(v)) or float(v)>99999999999999:fail(f'{label} cần số nguyên không âm hợp lệ.')
        return int(float(v))
    if value(summary,'B3')!=data['month']:fail('Tháng trong file không khớp kỳ đang nhập.')
    if value(summary,'B7')!=baseline(data):fail('File đã cũ so với database. Xuất file mới trước khi nhập lại.')
    confirmed=integer(value(summary,'B5'),'Xác nhận chi phí')
    if confirmed not in (0,1):fail('Xác nhận chi phí chỉ nhận 0 hoặc 1.')
    expected={s['id']:s for s in data['sales']};seen=set();changes=[]
    for row in range(6,SALES_LIMIT+6):
        id=value(sales,f'A{row}')
        if not id:
            if value(sales,f'D{row}') or value(sales,f'G{row}'):fail('Chỉ nhập mã đơn/giá vốn cho dòng có Sale ID.')
            continue
        if id not in expected or id in seen:fail('Dòng bán không thuộc kỳ hoặc bị trùng ID. Xuất lại file mới.')
        seen.add(id);s=expected[id]
        if value(sales,f'C{row}')!=s['sku'] or integer(value(sales,f'E{row}'),'Số lượng')!=s['quantity'] or integer(value(sales,f'F{row}'),'Doanh thu')!=s['revenue']:
            fail('Không được sửa SKU, số lượng hoặc doanh thu trong file tài chính.')
        order=value(sales,f'D{row}').strip().upper()
        if order and not re.fullmatch(r'[\w./-]{1,100}',order):fail('Mã đơn tối đa 100 ký tự chữ, số, dấu gạch, chấm hoặc /.')
        cost=integer(value(sales,f'G{row}'),'Giá vốn đơn vị',True)
        if cost!=s['unit_cost'] or (order or None)!=s['order_number']:
            changes.append({'id':id,'unit_cost':cost,'order_number':order or None,'before_unit_cost':s['unit_cost'],'before_order_number':s['order_number']})
    if seen!=set(expected):fail('File thiếu dòng bán hoặc số liệu đã thay đổi. Xuất lại file mới.')
    refs=set();expense_rows=[];start,end=dates(data['month'])
    for row in range(6,EXPENSE_LIMIT+6):
        ref=value(expenses,f'A{row}').strip()
        if not ref:
            if any(value(expenses,f'{c}{row}') for c in 'BCDE'):fail('Dòng chi phí thiếu mã tham chiếu.')
            continue
        if ref in refs or len(ref)>100:fail('Mã chi phí trùng hoặc quá dài.')
        refs.add(ref)
        date_value=value(expenses,f'B{row}')
        try:
            when=(datetime(1899,12,30)+timedelta(days=float(date_value))).replace(tzinfo=TZ)
        except (ValueError,OverflowError):fail('Ngày chi phí cần là ô ngày Excel hợp lệ.')
        if not start<=when<end or when>m.now():fail('Ngày chi phí không thuộc kỳ hoặc nằm trong tương lai.')
        category=value(expenses,f'C{row}').strip();note=value(expenses,f'E{row}')
        if not 2<=len(category)<=100 or len(note)>500:fail('Danh mục hoặc ghi chú chi phí không hợp lệ.')
        expense_rows.append({'reference':ref,'date':when.isoformat(),'category':category,'amount':integer(value(expenses,f'D{row}'),'Số tiền'),'note':note})
    # Deleting a spreadsheet row never deletes an accounting record.
    if not {e['reference'] for e in data['expenses']}.issubset(refs):fail('File thiếu chi phí hiện có. Không xóa dòng chi phí; xuất lại file mới để đối soát.')
    for cells,limit in [(sales,SALES_LIMIT),(expenses,EXPENSE_LIMIT)]:
        for addr,(v,f) in cells.items():
            if int(re.search(r'\d+',addr).group())>=limit+6 and v and not f:fail('Dữ liệu vượt vùng nhập được hỗ trợ.')
    return {'baseline':baseline(data),'sales':changes,'expenses':expense_rows,'before_expenses':data['expenses'],
            'confirmed':bool(confirmed),'before_confirmed':data['expenses_confirmed']}
