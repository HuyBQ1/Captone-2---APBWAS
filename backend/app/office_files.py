"""Create and store real DOCX/XLSX artifacts using bounded, typed tool data."""
import copy,hashlib,io,json,math,re,unicodedata,zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from lxml import etree as LXML
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,HTTPException,Response,Query
from sqlalchemy import select
from sqlalchemy.orm import defer
from docx import Document as WordDocument
from docx.shared import Pt,Cm,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from . import models as m
from .db import get_db,read_only_db
from .auth import current_user
from .permissions import require
from .audit import audit
from .config import settings
from .office_math import cached_formulas

router=APIRouter(prefix='/api/files')
ASSETS=Path(__file__).parent/'assets'
MIMES={'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N={'s':NS};ET.register_namespace('',NS)

def clean(value):return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str('' if value is None else value))

def permission(db,user,wf,name):
    require(db,user,name)
    if wf.agent_id and name not in wf.agent_snapshot.get('permissions',[]):raise HTTPException(403,'Agent thiếu quyền đọc nguồn để tạo tệp: '+name)

def source_data(db,user,wf,args,kind):
    source=args.get('source') or 'custom';required=['agents.run'];docs=[]
    if source in ('finance','inventory','products') and user.workspace_id!='primary':raise HTTPException(403,'Workspace chưa cấu hình nguồn dữ liệu kinh doanh.')
    needed={'finance':['sales.read','inventory.read'],'inventory':['inventory.read'],'products':['inventory.read'],'knowledge':['documents.read'],'custom':[]}[source]
    for name in needed:permission(db,user,wf,name)
    required+=needed
    table=None;finance=None;body=args.get('body_text') or '';title=args.get('title') or ''
    if source=='finance':
        from .finance import dataset,finance_summary
        with read_only_db(db) as reader:
            finance=dataset(reader,args.get('month') or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m'))
            summary=finance_summary(reader,finance['month'])
        title=title or f"Báo cáo tài chính tháng {finance['month'][5:]} năm {finance['month'][:4]}"
        body='\n'.join(summary['summary'].splitlines()[1:])
    elif source in ('inventory','products'):
        query=select(m.Product,m.Inventory).join(m.Inventory,m.Inventory.product_id==m.Product.id)
        if args.get('query'):
            value=args['query'].strip();query=query.where(m.Product.name.icontains(value,autoescape=True)|m.Product.sku.icontains(value,autoescape=True))
        if args.get('low_stock'):query=query.where(m.Inventory.quantity<=m.Inventory.threshold)
        limit=200 if kind=='docx' else 2000
        with read_only_db(db) as reader:
            found=reader.execute(query.order_by(m.Product.sku).limit(limit+1)).all()
            if len(found)>limit:raise ValueError(f'Quá {limit} sản phẩm cho một tệp. Hãy thu hẹp tên hoặc SKU.')
            rows=[[p.sku,p.name,p.category,i.quantity,i.threshold,int(p.price)] for p,i in found]
        columns=['SKU','Sản phẩm','Danh mục','Tồn hiện tại','Ngưỡng cảnh báo','Giá bán VND']
        table=(columns,rows,[]);title=title or ('Báo cáo tồn kho hiện tại' if source=='inventory' else 'Danh mục sản phẩm')
        body=f'Danh sách gồm {len(rows)} sản phẩm từ database. Tồn kho là số hiện tại, không phải tồn cuối tháng. Giá là giá niêm yết, chưa phải doanh thu.'
        if settings.sample_data or settings.demo_mode:body+='\nDữ liệu mẫu hoặc mô phỏng Nova Commerce.'
    elif source=='knowledge':
        if kind!='docx':raise ValueError('Chọn Word để tạo tài liệu từ kho tri thức.')
        from .retrieval import search
        ids=wf.agent_snapshot.get('knowledge_ids',[]) if wf.agent_id else None
        if ids is None:
            from .retrieval import allowed_scopes
            ids=list(db.scalars(select(m.Document.id).where(m.Document.workspace_id==user.workspace_id,m.Document.scope.in_(allowed_scopes(user)),m.Document.status=='indexed')))
        snippets=search(db,user,args.get('query') or wf.request,document_ids=ids) if ids is not None else search(db,user,args.get('query') or wf.request)
        if not snippets:raise ValueError('Chưa tìm thấy tài liệu được phép truy cập để tạo Word. Hãy cung cấp nội dung hoặc từ khóa cụ thể.')
        docs=list({s['document_id'] for s in snippets});title=title or 'Tổng hợp trích dẫn tài liệu nội bộ'
        body='Tài liệu tổng hợp các đoạn nguồn liên quan, không thay thế văn bản gốc.\n\n'+'\n\n'.join(f"## Nguồn {s.get('name',s.get('document_name','Tài liệu nội bộ'))}\n{s['content']}\nMã nguồn: {s['document_id']}" for s in snippets)
    else:
        title=title or ('Tài liệu theo yêu cầu' if kind=='docx' else 'Bảng tính theo yêu cầu')
        if kind=='docx' and not body.strip():raise ValueError('Cần nội dung tài liệu Word. Hãy nêu chủ đề hoặc nội dung cần soạn.')
        if kind=='docx' and args.get('columns'):table=(args['columns'],args.get('rows') or [],[])
        if kind=='xlsx':table=(args.get('columns') or [],args.get('rows') or [],args.get('formulas') or [])
    return title[:180],body,table,finance,{'type':source,'required_permissions':required,'document_ids':docs,'month':finance['month'] if finance else None,'as_of':m.now().isoformat(),**({'metrics':summary} if finance else {})}

def word(title,body,table,company,source):
    doc=WordDocument(ASSETS/'office-template.docx')
    for p in list(doc.paragraphs):
        if not p.text:p._element.getparent().remove(p._element)
    doc.add_paragraph(clean(title),'Title')
    for element in list(doc.styles.element.xpath('.//w:pBdr'))+list(doc.element.xpath('.//w:pBdr')):element.getparent().remove(element)
    doc.add_paragraph(clean(company)+' · '+m.now().astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M'))
    if source['type']=='custom':doc.add_paragraph('Bản dự thảo theo yêu cầu. Kiểm tra nội dung trước khi ban hành.','Subtitle')
    def paragraph(text,style=None):
        p=doc.add_paragraph(style=style)
        for i,part in enumerate(re.split(r'\*\*(.*?)\*\*',clean(text))):p.add_run(part).bold=bool(i%2)
    for line in body.splitlines():
        if not line.strip():continue
        heading=re.match(r'^#{1,6}\s+(.+)',line)
        if heading:doc.add_paragraph(clean(heading[1]),'Heading 1')
        elif re.match(r'^[-*]\s+',line):paragraph(line[2:],'List Bullet')
        elif re.match(r'^\d+[.)]\s+',line):paragraph(re.sub(r'^\d+[.)]\s+','',line),'List Number')
        else:paragraph(line)
    if table:
        columns,rows,_=table
        if len(columns)>8:raise ValueError('Word hỗ trợ tối đa 8 cột. Chọn Excel cho bảng rộng hơn.')
        if not columns or any(len(row)!=len(columns) for row in rows):raise ValueError('Cần bảng Word có số ô mỗi dòng khớp với số cột.')
        if sum(len(str(v)) for row in rows for v in row)>100000:raise ValueError('Bảng Word quá nhiều nội dung. Hãy chia nhỏ hoặc dùng Excel.')
        if len(rows)>200:raise ValueError('Bảng Word tối đa 200 dòng. Chọn Excel cho dữ liệu lớn hơn.')
        doc.add_heading('Bảng dữ liệu',level=1)
        t=doc.add_table(rows=1,cols=len(columns));t.style='Table Grid'
        t.autofit=False
        widths=[2,5,2.8,2,2.2,3] if len(columns)==6 else [17/len(columns)]*len(columns)
        for col,width in zip(t.columns,widths):col.width=Cm(width)
        for cell,label in zip(t.rows[0].cells,columns):
            cell.text=clean(label)
            for run in cell.paragraphs[0].runs:run.bold=True;run.font.size=Pt(9)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E9EDF3');cell._tc.get_or_add_tcPr().append(shade)
        repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in rows:
            cells=t.add_row().cells
            for cell,value in zip(cells,row):
                cell.text=clean(value) if value is not None else ''
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(3)
                    for run in p.runs:run.font.size=Pt(8)
            no_split=OxmlElement('w:cantSplit');t.rows[-1]._tr.get_or_add_trPr().append(no_split)
        for row in t.rows:
            for cell,width in zip(row.cells,widths):cell.width=Cm(width)
    doc.add_paragraph('Nguồn: '+('website Nova Commerce, bản đồng bộ trong APBWAS' if source.get('metrics',{}).get('source')=='Nova Commerce API' else {'custom':'nội dung được soạn theo yêu cầu của người dùng','finance':'giao dịch bán hàng, giá vốn, chi phí và tồn kho trong APBWAS','inventory':'products và inventory trong APBWAS','products':'products và inventory trong APBWAS','knowledge':'các đoạn tài liệu được phép truy cập'}[source['type']]))
    doc.core_properties.title=clean(title);out=io.BytesIO();doc.save(out)
    # Word can read style borders from stylesWithEffects even when the visible
    # Title style was cleaned. Keep both style representations consistent.
    cleaned=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as src,zipfile.ZipFile(cleaned,'w',zipfile.ZIP_DEFLATED) as target:
        for name in src.namelist():
            data=src.read(name)
            if name in ('word/document.xml','word/styles.xml','word/stylesWithEffects.xml'):
                root=LXML.fromstring(data)
                for border in root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr'):border.getparent().remove(border)
                data=LXML.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
            target.writestr(name,data)
    return cleaned.getvalue()

def workbook(title,table,source):
    from .finance_excel import write
    columns,rows,formulas=table
    if not columns or len(columns)>20 or not rows or len(rows)>2000:raise ValueError('Excel cần 1–20 cột và 1–2.000 dòng dữ liệu (bảng AI tùy chỉnh tối đa 1.000 dòng).')
    if any(not isinstance(c,str) or not c.strip() or len(c)>180 for c in columns):raise ValueError('Cần tên cột hợp lệ, tối đa 180 ký tự.')
    if any(len(row)!=len(columns) for row in rows):raise ValueError('Số ô mỗi dòng phải bằng số cột.')
    if sum(len(str(v)) for row in rows for v in row)>1_000_000:raise ValueError('Nội dung bảng quá lớn. Cần chia nhỏ dữ liệu.')
    for row in rows:
        for value in row:
            if isinstance(value,(int,float)) and (not math.isfinite(value) or abs(value)>1e100):raise ValueError('Bảng tính chỉ nhận số hữu hạn trong giới hạn.')
            if isinstance(value,str) and len(value)>10000:raise ValueError('Mỗi ô tối đa 10.000 ký tự.')
    cached=cached_formulas(columns,rows,formulas)
    with zipfile.ZipFile(ASSETS/'office-template.xlsx') as z:parts={name:z.read(name) for name in z.namelist()}
    root=ET.fromstring(parts['xl/worksheets/sheet1.xml']);sheet=root.find('s:sheetData',N)
    styles=ET.fromstring(parts['xl/styles.xml']);fonts=styles.find('s:fonts',N);xfs=styles.find('s:cellXfs',N);integer_styles={}
    header=copy.deepcopy(sheet.find("s:row[@r='1']",N));sample=copy.deepcopy(sheet.find("s:row[@r='2']",N))
    sheet.clear()
    def row_xml(template,r,values):
        row=copy.deepcopy(template);row.set('r',str(r))
        for cell in list(row):
            c=re.match('[A-Z]+',cell.attrib['r'])[0]
            if ord(c[0])-65>=len(columns):row.remove(cell);continue
            cell.set('r',c+str(r))
            for child in list(cell):cell.remove(child)
        sheet.append(row)
        for c,value in enumerate(values):
            address=f'{chr(65+c)}{r}';write(root,address,clean(value) if isinstance(value,str) else value)
            node=root.find(f"s:sheetData/s:row/s:c[@r='{address}']",N)
            if isinstance(value,bool):node.set('t','b')
            elif isinstance(value,(int,float)) and float(value).is_integer():
                old=int(node.attrib.get('s','0'))
                if old not in integer_styles:
                    style=copy.deepcopy(xfs[old]);style.set('numFmtId','3');integer_styles[old]=len(xfs);xfs.append(style)
                node.set('s',str(integer_styles[old]))
    row_xml(header,1,columns)
    for r,values in enumerate(rows,2):row_xml(sample,r,values)
    formula_styles={}
    for cell,value in cached.items():
        node=root.find(f"s:sheetData/s:row/s:c[@r='{cell}']",N)
        old=int(node.attrib.get('s','0'));style_key=(old,float(value['value']).is_integer())
        if style_key not in formula_styles:
            style=copy.deepcopy(xfs[old]);font=copy.deepcopy(fonts[int(style.attrib.get('fontId','0'))]);color=font.find('s:color',N)
            if color is None:color=ET.SubElement(font,f'{{{NS}}}color')
            color.attrib.clear();color.set('rgb','FF182B42');style.set('fontId',str(len(fonts)));fonts.append(font)
            if style_key[1]:style.set('numFmtId','3')
            formula_styles[style_key]=len(xfs);xfs.append(style)
        node.set('s',str(formula_styles[style_key]))
        for child in list(node):node.remove(child)
        node.attrib.pop('t',None);ET.SubElement(node,f'{{{NS}}}f').text=value['formula'];ET.SubElement(node,f'{{{NS}}}v').text=str(value['value'])
    fonts.set('count',str(len(fonts)));xfs.set('count',str(len(xfs)));parts['xl/styles.xml']=ET.tostring(styles,encoding='utf-8',xml_declaration=True)
    last=chr(64+len(columns))+str(len(rows)+1)
    dimension=root.find('s:dimension',N)
    if dimension is not None:dimension.set('ref','A1:'+chr(64+len(columns))+str(len(rows)+4))
    auto=root.find('s:autoFilter',N)
    if auto is None:
        auto=ET.Element(f'{{{NS}}}autoFilter');root.insert(list(root).index(sheet)+1,auto)
    auto.set('ref','A1:'+last)
    # Provenance stays with the data rather than introducing a thin extra tab.
    label={'custom':'nội dung theo yêu cầu','inventory':'tồn kho từ APBWAS','products':'danh mục hàng hóa từ APBWAS'}.get(source['type'],source['type'])
    stamp=datetime.fromisoformat(source['as_of']).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')
    write(root,f'A{len(rows)+4}','Nguồn: '+label+' · '+stamp)
    parts['xl/worksheets/sheet1.xml']=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    wb=ET.fromstring(parts['xl/workbook.xml']);calc=wb.find('s:calcPr',N)
    if calc is None:calc=ET.SubElement(wb,f'{{{NS}}}calcPr')
    calc.set('calcMode','auto');calc.set('fullCalcOnLoad','1');parts['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in parts.items():z.writestr(name,raw)
    return out.getvalue()

def metadata(a):return {'id':a.id,'title':a.title,'filename':a.filename,'kind':a.kind,'size':a.size,'sha256':a.sha256,'created_at':a.created_at.isoformat(),'download_url':f'/api/files/{a.id}/download','workflow_id':a.workflow_id}

def create_file(db,user,wf,args,kind):
    require(db,user,'agents.run')
    digest=hashlib.sha256(json.dumps(args,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    existing=db.scalar(select(m.GeneratedFile).options(defer(m.GeneratedFile.content)).where(m.GeneratedFile.workflow_id==wf.id,m.GeneratedFile.kind==kind))
    if existing:
        if existing.request_hash!=digest:raise ValueError('Mỗi yêu cầu tạo tối đa một Word và một Excel. Tách các tệp cùng định dạng thành yêu cầu riêng.')
        a=existing
    else:
        title,body,table,finance,source=source_data(db,user,wf,args,kind)
        company=db.get(m.SystemSetting,'company');label=company.value.get('name','Doanh nghiệp') if company else 'Doanh nghiệp'
        if kind=='docx':raw=word(title,body,table,label,source)
        elif finance:
            from .finance_excel import export_workbook
            raw=export_workbook(finance)
        else:raw=workbook(title,table,source)
        if len(raw)>8*1024*1024:raise ValueError('Tệp quá 8 MB. Hãy chia nhỏ nội dung.')
        name=''.join(c for c in unicodedata.normalize('NFD',title.replace('đ','d').replace('Đ','D')) if not unicodedata.combining(c))
        name=re.sub(r'[^a-zA-Z0-9]+','-',name).strip('-')[:110] or 'APBWAS'
        a=m.GeneratedFile(user_id=user.id,workspace_id=user.workspace_id,workflow_id=wf.id,kind=kind,title=title,filename=name+'.'+kind,content=raw,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),request_hash=digest,source=source)
        db.add(a);db.flush();audit(db,user,'file.generated',a.id,{'kind':kind,'source':source['type'],'bytes':len(raw),'sha256':a.sha256},wf.id)
    old=[f for f in (wf.result or {}).get('files',[]) if f['id']!=a.id]
    files=old+[metadata(a)]
    return {'files':files,'month':a.source.get('month'),'summary':'Đã tạo '+', '.join(f['filename'] for f in files)+'. Bấm nút tải Word hoặc Excel bên dưới. Tệp đã được lưu để tải lại trong hội thoại.'}

def check_access(db,user,a):
    require(db,user,'agents.run')
    if a.source.get('superseded_source'):raise HTTPException(410,'Tệp thuộc nguồn dữ liệu cũ đã được thay thế. Hãy tạo báo cáo mới từ website Nova Commerce.')
    for p in a.source.get('required_permissions',[]):require(db,user,p)
    if a.source.get('document_ids'):
        from .retrieval import allowed_scopes
        for id in a.source['document_ids']:
            doc=db.get(m.Document,id)
            if not doc or doc.workspace_id!=user.workspace_id or doc.scope not in allowed_scopes(user):raise HTTPException(403,'Quyền đọc tài liệu nguồn đã thay đổi.')

@router.get('')
def listing(conversation_id:str='',user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'agents.run')
    query=select(m.GeneratedFile).options(defer(m.GeneratedFile.content)).where(m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id)
    if conversation_id:query=query.join(m.Workflow,m.Workflow.id==m.GeneratedFile.workflow_id).where(m.Workflow.conversation_id==conversation_id)
    rows=[]
    for a in db.scalars(query.order_by(m.GeneratedFile.created_at.desc()).limit(50)):
        try:check_access(db,user,a)
        except HTTPException:continue
        rows.append(metadata(a))
    return {'items':rows}

@router.get('/{id}/download')
def download(id:str,user=Depends(current_user),db=Depends(get_db)):
    a=db.scalar(select(m.GeneratedFile).where(m.GeneratedFile.id==id,m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id))
    if not a:raise HTTPException(404,'Không tìm thấy tệp của bạn.')
    check_access(db,user,a);audit(db,user,'file.downloaded',a.id,{'sha256':a.sha256});db.commit()
    return Response(a.content,media_type=MIMES[a.kind],headers={'Content-Disposition':f'attachment; filename="{a.filename}"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.get('/{id}/preview')
def preview(id:str,response:Response,sheet:int=Query(default=0,ge=0),page:int=Query(default=1,ge=1),page_size:int=Query(default=50,ge=10,le=100),user=Depends(current_user),db=Depends(get_db)):
    a=db.scalar(select(m.GeneratedFile).where(m.GeneratedFile.id==id,m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id))
    if not a:raise HTTPException(404,'Không tìm thấy tệp của bạn.')
    check_access(db,user,a)
    from .office_preview import excel,word
    result=excel(a.content,sheet,page,page_size) if a.kind=='xlsx' else word(a.content)
    response.headers['Cache-Control']='private, no-store'
    return {**metadata(a),**result}
