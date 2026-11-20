"""Read-only, local previews of the stored artifact, never current DB data."""
import io,math,posixpath,re,zipfile
from datetime import datetime,timedelta
from xml.etree import ElementTree as ET
from fastapi import HTTPException
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N={'s':NS};R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

def archive(raw):
    try:
        z=zipfile.ZipFile(io.BytesIO(raw))
        if len(z.infolist())>1000 or sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError()
        return z
    except (zipfile.BadZipFile,ValueError):raise HTTPException(422,'Tệp vượt giới hạn xem trước hoặc không phải Office hợp lệ.') from None

def xml(z,name):
    raw=z.read(name)
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError()
    return ET.fromstring(raw)

def column_index(value):
    index=0
    for c in value:index=index*26+ord(c)-64
    return index

def column_name(index):
    label=''
    while index:index,r=divmod(index-1,26);label=chr(65+r)+label
    return label

def display(value,fmt='',numfmt=0):
    if value is None:return ''
    if isinstance(value,bool):return 'TRUE' if value else 'FALSE'
    if not isinstance(value,(int,float)):return str(value)
    if not math.isfinite(value):return str(value)
    bare=re.sub(r'"[^"]*"|\[[^\]]*\]','',fmt.lower())
    if 14<=numfmt<=22 or re.search(r'yy|dd',bare):
        try:return (datetime(1899,12,30)+timedelta(days=value)).strftime('%d/%m/%Y %H:%M' if 'h' in bare else '%d/%m/%Y')
        except (ValueError,OverflowError):return str(value)
    if '%' in bare:
        decimals=re.search(r'\.([0#]+)%',bare);digits=min(8,len(decimals[1])) if decimals else 0
        return f'{value*100:,.{digits}f}'.translate(str.maketrans(',.','.,'))+'%'
    text=f'{value:,.0f}' if float(value).is_integer() else f'{value:,.8f}'.rstrip('0').rstrip('.')
    return text.translate(str.maketrans(',.','.,'))

def excel(raw,sheet_index=0,page=1,size=50):
    try:
        with archive(raw) as z:
            wb=xml(z,'xl/workbook.xml');rels={r.attrib['Id']:r.attrib['Target'] for r in xml(z,'xl/_rels/workbook.xml.rels') if r.attrib.get('TargetMode')!='External'}
            sheets=list(wb.findall('s:sheets/s:sheet',N))
            if not 0<=sheet_index<len(sheets):raise HTTPException(422,'Trang tính không tồn tại.')
            target=rels[sheets[sheet_index].attrib[R]]
            path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not path.startswith('xl/worksheets/'):raise ValueError()
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(si.itertext()) for si in xml(z,'xl/sharedStrings.xml').findall('s:si',N)]
            formats={}
            if 'xl/styles.xml' in z.namelist():
                styles=xml(z,'xl/styles.xml');codes={int(n.attrib['numFmtId']):n.attrib['formatCode'] for n in styles.findall('s:numFmts/s:numFmt',N)}
                formats={i:(int(n.attrib.get('numFmtId',0)),codes.get(int(n.attrib.get('numFmtId',0)),'')) for i,n in enumerate(styles.findall('s:cellXfs/s:xf',N))}
            root=xml(z,path);data={};max_row=0;max_col=0
            for cell in root.findall('s:sheetData/s:row/s:c',N):
                address=cell.attrib.get('r','');match=re.fullmatch(r'([A-Z]+)([1-9]\d*)',address)
                if not match:continue
                col,row=column_index(match[1]),int(match[2])
                if row>20000 or col>50:continue
                v=cell.find('s:v',N);inline=cell.find('s:is',N);f=cell.find('s:f',N);t=cell.attrib.get('t','n')
                raw_value=v.text if v is not None else None
                if t=='inlineStr':value=''.join(inline.itertext()) if inline is not None else ''
                elif t=='s':value=strings[int(raw_value)] if raw_value is not None else ''
                elif t=='b':value=raw_value=='1'
                elif t in ('str','e'):value=raw_value or ''
                elif raw_value is None:value=None
                else:
                    try:
                        value=float(raw_value)
                        value=raw_value if not math.isfinite(value) else int(value) if value.is_integer() else value
                    except (ValueError,OverflowError):value=raw_value
                if value in (None,'') and f is None:continue
                max_row=max(max_row,row);max_col=max(max_col,col)
                if (page-1)*size<row<=page*size:
                    numfmt,fmt=formats.get(int(cell.attrib.get('s','0')),(0,''))
                    data[(row,col)]={'value':value,'display':display(value,fmt,numfmt),'formula':'='+f.text if f is not None and f.text else None,'missing_cache':f is not None and (v is None or v.text is None and t!='str')}
            max_row=max(1,max_row);max_col=max(1,max_col);pages=max(1,math.ceil(max_row/size))
            if page>pages:raise HTTPException(422,'Trang xem trước không tồn tại.')
            return {'kind':'xlsx','sheets':[{'index':i,'name':s.attrib['name']} for i,s in enumerate(sheets)],'sheet_index':sheet_index,'page':page,'pages':pages,'page_size':size,'total_rows':max_row,'columns':[column_name(c) for c in range(1,max_col+1)],
                    'rows':[{'number':r,'cells':[data.get((r,c),{'value':None,'display':'','formula':None,'missing_cache':False}) for c in range(1,max_col+1)]} for r in range((page-1)*size+1,min(page*size,max_row)+1)]}
    except HTTPException:raise
    except (KeyError,ValueError,IndexError,TypeError,ET.ParseError,zipfile.BadZipFile):raise HTTPException(422,'Không đọc được bảng tính để xem trước. Bạn vẫn có thể tải file gốc.') from None

def word(raw):
    try:
        with archive(raw):pass
        doc=Document(io.BytesIO(raw));blocks=[];truncated=False
        for element in doc.element.body.iterchildren():
            if len(blocks)>=300:truncated=True;break
            if element.tag.endswith('}p'):
                p=Paragraph(element,doc)
                if not p.text.strip():continue
                style=p.style.name if p.style else ''
                blocks.append({'type':'paragraph','style':style,'text':p.text})
            elif element.tag.endswith('}tbl'):
                table=Table(element,doc)
                blocks.append({'type':'table','rows':[[c.text for c in r.cells[:8]] for r in table.rows[:201]],'truncated':len(table.rows)>201})
        return {'kind':'docx','blocks':blocks,'truncated':truncated}
    except HTTPException:raise
    except (KeyError,ValueError,TypeError,zipfile.BadZipFile):raise HTTPException(422,'Không đọc được tài liệu để xem trước. Bạn vẫn có thể tải file gốc.') from None
