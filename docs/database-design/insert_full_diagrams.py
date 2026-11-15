"""Patch version 1.0 in place at the package level to create version 1.1."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from PIL import Image
import copy,re,json,hashlib

ROOT=Path(__file__).parent
SRC=ROOT/'C2SE.06_DatabaseDesign_APBWAS_ver1.0.docx'
OUT=ROOT/'C2SE.06_DatabaseDesign_APBWAS_ver1.1.docx'
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
q=lambda n:'{'+ns['w']+'}'+n
with ZipFile(SRC) as z:parts={n:z.read(n) for n in z.namelist()}
base_hashes={n:hashlib.sha256(b).hexdigest() for n,b in parts.items()}
root=E.fromstring(parts['word/document.xml']);body=root.find('w:body',ns)
rels=E.fromstring(parts['word/_rels/document.xml.rels'])
relmap={r.get('Id'):r.get('Target') for r in rels}
def text(el):return ''.join(el.xpath('.//w:t/text()',namespaces=ns))
def replace(p,value):
    runs=p.findall('w:r',ns);rpr=copy.deepcopy(runs[0].find('w:rPr',ns)) if runs and runs[0].find('w:rPr',ns) is not None else None
    for x in list(p):
        if x.tag!=q('pPr'):p.remove(x)
    r=E.SubElement(p,q('r'))
    if rpr is not None:r.append(rpr)
    E.SubElement(r,q('t')).text=value
def size(p,path,width=6.15,maxheight=7.15):
    iw,ih=Image.open(path).size
    width=min(width,maxheight*iw/ih);cx=int(width*914400);cy=int(cx*ih/iw)
    for el in p.xpath('.//*[local-name()="extent" or local-name()="ext"]'):
        if el.get('cx') is not None:el.set('cx',str(cx));el.set('cy',str(cy))

paragraphs=body.findall('w:p',ns)
# Word may rename media files while updating fields; locate by the actual section.
section_index=next(i for i,p in enumerate(paragraphs) if text(p)=='2.2. Entity Relationship Diagram')
concept=next(p for p in paragraphs[section_index+1:] if p.xpath('.//a:blip',namespaces=ns))
blip=concept.find('.//a:blip',ns);target='word/'+relmap[blip.get('{'+ns['r']+'}embed')]
chen=ROOT/'diagrams/APBWAS_Entity_Relationship_Diagram.png';parts[target]=chen.read_bytes();size(concept,chen,maxheight=7.15)
intro=next(p for p in paragraphs if text(p).startswith('The conceptual view below'))
replace(intro,'The complete Chen ERD shows all 22 entities, 143 attributes and 21 declared foreign-key relationships. Rectangles are entities, ellipses are attributes, underlined attributes are primary keys, and diamonds are relationships. Independent entities remain unconnected. Use the companion SVG for detailed zoom.')

oldheading=next(p for p in paragraphs if text(p)=='2.3. Table Relationship Diagram')
newheading=copy.deepcopy(oldheading)
newintro=copy.deepcopy(intro)
replace(newintro,'This overview shows all 22 tables and all 21 foreign-key links. Table colors distinguish data domains; PK, FK and UQ identify keys, and ? marks nullable columns. Crow foot symbols show cardinality. The following detail views and relationship matrix provide readable field-level information.')
physical=ROOT/'diagrams/APBWAS_Table_Relationship_Diagram.png'
picture=copy.deepcopy(concept);newrid='rIdAPBWASFullRelationship'
picture.find('.//a:blip',ns).set('{'+ns['r']+'}embed',newrid)
for x in picture.xpath('.//*[local-name()="docPr"]'):x.set('id','901');x.set('name','APBWAS complete table relationship diagram')
size(picture,physical,maxheight=7.15)
newmedia='word/media/APBWAS-Full-Table-Relationship.png';parts[newmedia]=physical.read_bytes()
newrel=E.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
newrel.set('Id',newrid);newrel.set('Type',ns['r']+'/image');newrel.set('Target','media/APBWAS-Full-Table-Relationship.png')
caption_template=next(p for p in paragraphs if text(p)=='Figure 1. Entity Relationship Diagram')
newcaption=copy.deepcopy(caption_template);replace(newcaption,'Figure 2. Table Relationship Diagram')
insert_at=body.index(oldheading)
for el in [newheading,newintro,picture,newcaption]:body.insert(insert_at,el);insert_at+=1
replace(oldheading,'2.3.1. Detailed Table Views')
pr=oldheading.find('w:pPr',ns);style=pr.find('w:pStyle',ns)
style.set(q('val'),'Heading3')
for run in oldheading.findall('w:r',ns):
    rp=run.find('w:rPr',ns)
    if rp is None:rp=E.SubElement(run,q('rPr'))
    for name,value in [('color','000000'),('sz','26'),('b','1')]:
        el=rp.find('w:'+name,ns)
        if el is None:el=E.SubElement(rp,q(name))
        el.set(q('val'),value)
for p in paragraphs:
    value=text(p)
    if re.match(r'^Figure [2-5]\. Table Structure Diagram Part',value):
        number=int(re.match(r'^Figure (\d+)',value).group(1));replace(p,value.replace(f'Figure {number}.',f'Figure {number+1}.',1))
    if value=='Version 1.0':replace(p,'Version 1.1')
    if value=='Date: October 31st, 2026':replace(p,'Date: November 1st, 2026')

tables=body.findall('w:tbl',ns)
metadata=tables[2];cells=metadata.findall('w:tr',ns)[3].findall('w:tc',ns)
replace(cells[1].find('w:p',ns),'November 1st, 2026')
replace(cells[3].find('w:p',ns),OUT.name)
history=tables[3];row=copy.deepcopy(history.findall('w:tr',ns)[-1])
values=['1.1','November 1st, 2026','Add complete Chen ERD and Table Relationship Diagram','C2SE.06 Project Team']
for cell,value in zip(row.findall('w:tc',ns),values):replace(cell.find('w:p',ns),value)
history.append(row)
parts['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
parts['word/_rels/document.xml.rels']=E.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
    for n,data in parts.items():z.writestr(n,data)
allowed={'word/document.xml','word/_rels/document.xml.rels',target,newmedia}
assert all(hashlib.sha256(parts[n]).hexdigest()==h for n,h in base_hashes.items() if n not in allowed)
(ROOT/'diagrams/document-patch-check.json').write_text(json.dumps({'source':str(SRC),'output':str(OUT),'preserved_existing_parts':len(base_hashes)-3,'full_chen_entities':22,'full_chen_attributes':143,'full_table_relationships':21},indent=2),encoding='utf-8')
print('Saved',OUT)
