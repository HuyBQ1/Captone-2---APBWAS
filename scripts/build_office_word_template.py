from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
doc=Document();section=doc.sections[0]
section.page_width=Cm(21);section.page_height=Cm(29.7)
section.top_margin=section.bottom_margin=Cm(2);section.left_margin=section.right_margin=Cm(2)
normal=doc.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
normal.paragraph_format.line_spacing=1.15;normal.paragraph_format.space_after=Pt(7)
for name,size in [('Title',23),('Heading 1',15),('Heading 2',12)]:
    style=doc.styles[name];style.font.name='Arial';style.font.size=Pt(size);style.font.color.rgb=RGBColor.from_string('000000');style.font.bold=True
    style.paragraph_format.space_before=Pt(15);style.paragraph_format.space_after=Pt(8)
    style.paragraph_format.keep_with_next=True
for element in list(doc.styles.element.xpath('.//w:pBdr'))+list(doc.element.xpath('.//w:pBdr')):
    element.getparent().remove(element)
doc.styles['Title'].font.underline=False
footer=section.footer.paragraphs[0];footer.alignment=2
run=footer.add_run('Trang ');run.font.size=Pt(9)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
doc.core_properties.author='APBWAS';doc.save('backend/app/assets/office-template.docx')
print('Office Word template saved.')
