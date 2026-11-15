"""Build the new operational library; records are authored, not signed documents."""
import json
from pathlib import Path
from docx import Document
from docx.shared import Cm,Pt,RGBColor

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'backend/app/assets/company-library-v2'
OUT.mkdir(parents=True,exist_ok=True)
items=json.loads((ROOT/'backend/app/assets/company-library-v2.json').read_text(encoding='utf-8'))
for item in items:
    doc=Document()
    section=doc.sections[0]
    section.page_height=Cm(29.7);section.page_width=Cm(21)
    section.top_margin=Cm(2);section.bottom_margin=Cm(2);section.left_margin=Cm(2.3);section.right_margin=Cm(2.3)
    style=doc.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(11)
    style.paragraph_format.space_after=Pt(7)
    style.paragraph_format.line_spacing=1.12
    doc.styles['Title'].font.size=Pt(22);doc.styles['Title'].font.color.rgb=RGBColor(0,0,0)
    doc.add_paragraph('NOVA COMMERCE')
    doc.add_paragraph(item['title'],'Title')
    doc.add_paragraph(f"Mã tài liệu {item['code']}    Phiên bản 1.0\nNgày soạn 08/11/2026    Đơn vị phụ trách {item['department']}")
    doc.add_paragraph('Tài liệu thiết lập quy tắc vận hành cho workspace Nova Commerce. Chủ doanh nghiệp cần rà soát nội dung trước khi áp dụng vào hoạt động thực tế. Tài liệu chưa có chữ ký phê duyệt.')
    for title,body in item['sections']:
        doc.add_paragraph(title,'Heading 1');doc.add_paragraph(body)
    section.footer.paragraphs[0].text=f"Nova Commerce | {item['code']} | Tài liệu nội bộ"
    for border in list(doc.styles.element.xpath('.//w:pBdr'))+list(doc.element.xpath('.//w:pBdr')):
        border.getparent().remove(border)
    path=OUT/(item['code']+'.docx');doc.save(path)
print(json.dumps({'documents':len(items),'output':str(OUT)},ensure_ascii=False))
