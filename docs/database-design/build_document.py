"""Rebuild the APBWAS database design from the exported source metadata."""
import json,re
from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).parent
META=json.loads((ROOT/'schema-metadata.json').read_text(encoding='utf-8'))
TABLES={t['name']:t for t in META}
DESCRIPTIONS={
'roles':'Vai trò và danh sách quyền được cấp. users.role tham chiếu roles.name; danh sách quyền nằm trong JSON permissions.',
'permissions':'Danh mục tên quyền. Schema hiện tại không có bảng nối role_permissions và không có khóa ngoại từ roles.permissions tới bảng này.',
'users':'Tài khoản người dùng và vai trò hiện hành. Mật khẩu được băm Argon2; trạng thái active được kiểm tra khi thực hiện nghiệp vụ.',
'auth_sessions':'Phiên đăng nhập có thời hạn. Chỉ lưu SHA256 của token phiên; token gốc nằm trong cookie của trình duyệt.',
'conversations':'Hội thoại thuộc một người dùng; context lưu ngữ cảnh nghiệp vụ cho các lượt yêu cầu tiếp theo.',
'messages':'Tin nhắn trong hội thoại. Xóa hội thoại sẽ xóa các tin nhắn theo khóa ngoại CASCADE, nếu thao tác xóa hội thoại được các quan hệ khác cho phép.',
'workflows':'Yêu cầu nghiệp vụ, kế hoạch Agent, kết quả và tiến độ thực thi. idempotency_key ngăn tạo lặp; checkpoint hỗ trợ tiếp tục từ bước đã lưu.',
'workflow_steps':'Danh sách bước thực thi có vị trí và trạng thái. Mỗi workflow chỉ có một bản ghi cho một position.',
'tool_executions':'Lịch sử gọi công cụ với arguments, output và thời gian thực thi. Lưu dữ liệu có cấu trúc để kiểm tra lại kết quả.',
'workflow_events':'Dòng sự kiện dùng cho SSE và phát lại. sequence tăng trên toàn hệ thống, không phải số thứ tự riêng của mỗi workflow.',
'products':'Danh mục hàng hóa gồm SKU, tên, danh mục và giá bán. Đây là nguồn tra giá của công cụ lookup_products; giá không lấy từ tài liệu nội bộ.',
'inventory':'Tồn kho hiện tại cho từng sản phẩm. product_id vừa là khóa chính vừa là khóa ngoại; version phục vụ khóa lạc quan khi phê duyệt cập nhật.',
'sales':'Bản ghi doanh số gắn với sản phẩm và thời điểm. revenue là giá trị doanh thu đã lưu; báo cáo không suy ngược doanh thu từ giá bán hiện tại.',
'documents':'Thông tin tài liệu tải lên, phạm vi truy cập, nội dung trích xuất và trạng thái lập chỉ mục. Tệp gốc nằm trong kho uploads; database giữ đường dẫn.',
'document_chunks':'Các đoạn văn bản và embedding 384 chiều. model xác định cách tạo vector; truy xuất lọc model và phạm vi tài liệu trước khi trả kết quả.',
'approval_requests':'Yêu cầu phê duyệt của một workflow. arguments chứa tham số đề xuất và phiên bản tồn kho; revision quản lý các lần sửa trước khi duyệt.',
'approval_decisions':'Lịch sử quyết định của người duyệt theo revision. arguments lưu ảnh chụp tham số trước và sau quyết định.',
'reports':'Báo cáo đã tạo từ workflow. workflow_id duy nhất giúp việc tạo báo cáo có thể thực hiện lại mà không nhân đôi báo cáo.',
'audit_logs':'Nhật ký sự kiện nối chuỗi bằng HMAC SHA256. actor, resource và correlation_id là chuỗi định danh, không phải khóa ngoại.',
'usage_records':'Số token được ghi nhận cho người dùng theo workflow. Một workflow có tối đa một bản ghi sử dụng.',
'system_settings':'Cấu hình ứng dụng theo khóa, ví dụ giới hạn sử dụng, bật tắt công cụ và heartbeat của worker. Giá trị lưu dưới dạng JSON.',
'jobs':'Hàng đợi bền vững cho workflow hoặc lập chỉ mục tài liệu. resource là tham chiếu đa hình do ứng dụng phân giải; không có khóa ngoại.'}
FIELDS={
'id':'Định danh bản ghi','created_at':'Thời điểm tạo theo UTC','name':'Tên hiển thị hoặc tên danh mục',
'user_id':'Người dùng liên quan','workflow_id':'Workflow liên quan','conversation_id':'Hội thoại liên quan',
'permissions':'Mảng mã quyền','email':'Email đăng nhập','password_hash':'Mật khẩu đã băm Argon2','role':'Vai trò người dùng hoặc vai trò tin nhắn',
'active':'Cho phép tài khoản hoạt động','token_hash':'SHA256 token phiên','expires_at':'Thời điểm hết hạn',
'title':'Tiêu đề','context':'Ngữ cảnh hội thoại dạng JSON','content':'Nội dung văn bản','request':'Yêu cầu nghiệp vụ gốc',
'status':'Trạng thái xử lý do ứng dụng quản lý','plan':'Danh sách bước và tham số công cụ','result':'Kết quả có cấu trúc',
'error':'Thông báo lỗi nếu có','checkpoint':'Số bước đã hoàn thành','tokens':'Số token ghi nhận','duration_ms':'Thời gian xử lý theo mili giây',
'cancel_requested':'Cờ yêu cầu hủy','idempotency_key':'Khóa chống tạo trùng yêu cầu','deadline':'Hạn xử lý workflow',
'position':'Vị trí bước hoặc đoạn văn bản','tool':'Tên công cụ trong allowlist','output':'Kết quả thực thi JSON','arguments':'Tham số nghiệp vụ JSON',
'sequence':'Thứ tự sự kiện toàn hệ thống','type':'Loại sự kiện hoặc báo cáo','payload':'Dữ liệu sự kiện JSON',
'sku':'Mã hàng hóa duy nhất','category':'Danh mục sản phẩm dạng chuỗi','price':'Giá bán VND không có phần thập phân',
'product_id':'Sản phẩm liên quan','quantity':'Số lượng hàng','threshold':'Ngưỡng cảnh báo tồn kho thấp','version':'Phiên bản tồn kho phục vụ kiểm soát đồng thời',
'date':'Thời điểm ghi nhận doanh số','revenue':'Doanh thu VND không có phần thập phân','scope':'Phạm vi tài liệu all hoặc vai trò',
'path':'Đường dẫn tệp gốc','chunks':'Số đoạn đã lập chỉ mục','document_id':'Tài liệu nguồn','page':'Số trang nguồn nếu xác định được',
'embedding':'Vector 384 chiều','model':'Định danh mô hình hoặc bộ mã hóa embedding','revision':'Phiên bản yêu cầu phê duyệt',
'approved_revision':'Phiên bản đã được duyệt','reason':'Lý do hoặc giải thích','approval_id':'Yêu cầu phê duyệt liên quan',
'decision':'Quyết định approved rejected hoặc revision','data':'Nội dung báo cáo JSON','actor':'ID người dùng hoặc tác nhân hệ thống',
'event':'Mã sự kiện audit','resource':'Định danh tài nguyên nghiệp vụ','correlation_id':'Định danh liên kết chuỗi xử lý',
'previous_hash':'HMAC của bản ghi audit trước','hash':'HMAC của bản ghi audit hiện tại','key':'Khóa cấu hình','value':'Giá trị cấu hình JSON',
'kind':'Loại công việc workflow hoặc document','lease_until':'Hạn giữ quyền xử lý job'}
GROUPS=[('Danh tính và phân quyền',['roles','permissions','users','auth_sessions']),
        ('Hội thoại và thực thi Agent',['conversations','messages','workflows','workflow_steps','tool_executions','workflow_events']),
        ('Dữ liệu hàng hóa',['products','inventory','sales']),('Tài liệu và truy xuất',['documents','document_chunks']),
        ('Phê duyệt và báo cáo',['approval_requests','approval_decisions','reports']),
        ('Vận hành và kiểm toán',['audit_logs','usage_records','system_settings','jobs'])]

doc=Document();sec=doc.sections[0]
sec.page_width=Inches(8.27);sec.page_height=Inches(11.69)
sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.65)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3']:
    style=doc.styles[name];style.font.name='Calibri';style.font.color.rgb=RGBColor(0,0,0)
doc.styles['Normal'].font.size=Pt(10)
doc.styles['Normal'].paragraph_format.space_after=Pt(6)
doc.styles['Normal'].paragraph_format.line_spacing=1.08
for style in doc.styles:
    for border in list(style.element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
for name,size in [('Title',27),('Heading 1',16),('Heading 2',12),('Heading 3',11)]:
    doc.styles[name].font.size=Pt(size)
    doc.styles[name].paragraph_format.space_before=Pt(12)
    doc.styles[name].paragraph_format.space_after=Pt(7)
doc.core_properties.title='Thiết kế cơ sở dữ liệu APBWAS'
doc.core_properties.subject='Database Design Document'
doc.core_properties.author='APBWAS Project'
md=[]
def p(text):
    doc.add_paragraph(text);md.append(text+'\n')
def h(text,level=1):
    doc.add_heading(text,level);md.append('#'*(level+1)+' '+text+'\n')
def table(headers,rows,widths=None):
    t=doc.add_table(rows=1, cols=len(headers));t.autofit=False
    if widths:
        for c,w in zip(t.columns,widths):c.width=Inches(w)
    for c,v in zip(t.rows[0].cells,headers):c.text=v
    for row in rows:
        for c,v in zip(t.add_row().cells,row):c.text=str(v)
    for i,row in enumerate(t.rows):
        for j,c in enumerate(row.cells):
            if widths:c.width=Inches(widths[j])
            c.vertical_alignment=1
            pr=c._tc.get_or_add_tcPr()
            borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
            pr.append(borders)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E8EEF5' if i==0 else 'FFFFFF');pr.append(shade)
            mar=OxmlElement('w:tcMar')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'75');el.set(qn('w:type'),'dxa');mar.append(el)
            pr.append(mar)
            for paragraph in c.paragraphs:
                paragraph.paragraph_format.space_after=Pt(0)
                paragraph.paragraph_format.line_spacing=1.0
                for run in paragraph.runs:run.font.size=Pt(9);run.bold=(i==0)
        no_split=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(no_split)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    doc.add_paragraph().paragraph_format.space_after=Pt(1)
    md.append('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |')
    md.extend('| '+' | '.join(str(x).replace('|','/') for x in r)+' |' for r in rows);md.append('')

doc.add_paragraph('Thiết kế cơ sở dữ liệu APBWAS','Title')
doc.add_paragraph('Database Design Document','Subtitle')
p('AI Powered Business Workflow Automation System')
p('Phiên bản tài liệu 1.0  |  Ngày 31 tháng 10 năm 2026')
p('Tài liệu mô tả cấu trúc lưu trữ và cách bảo đảm toàn vẹn dữ liệu của APBWAS để nhóm phát triển, kiểm thử và người đánh giá đồ án sử dụng khi triển khai, rà soát hoặc mở rộng hệ thống.')
p('Thiết kế triển khai gồm 22 bảng ứng dụng, 143 cột và 21 khóa ngoại. PostgreSQL 16 lưu dữ liệu nghiệp vụ; pgvector hỗ trợ truy xuất tài liệu. Redis hỗ trợ cache và giới hạn sử dụng, còn hàng đợi bền vững nằm trong bảng jobs.')
h('1 Phạm vi và cơ sở thiết kế')
p('Phạm vi bao gồm danh tính, phân quyền, hội thoại, workflow Agent, hàng hóa, doanh số, tài liệu, phê duyệt, báo cáo, audit và vận hành. Mô tả bám theo mã nguồn hiện tại, bao gồm các thay đổi chưa commit tại thời điểm lập tài liệu; không phải biên bản kiểm tra schema của một database đang chạy.')
table(['Thành phần','Thiết kế hiện tại'],[
('Database chính','PostgreSQL 16 với extension vector'),('ORM và migration','SQLAlchemy 2 và Alembic revisions 0001, 0002'),
('Định danh','UUID v4 lưu trong VARCHAR(36); audit_logs dùng INTEGER tự tăng'),('Thời gian','TIMESTAMP WITH TIME ZONE; ứng dụng chuẩn hóa về UTC'),
('Số tiền','NUMERIC(15,0), đơn vị VND theo nghiệp vụ'),('Dữ liệu linh hoạt','JSON, không phải JSONB trong mapping hiện tại'),
('Môi trường kiểm thử','SQLite; embedding dùng JSON thay cho VECTOR(384)')],[1.65,5.25])
p('Nguồn đối chiếu: backend/app/models.py; backend/app/db.py; backend/migrations/versions/0001_initial.py và 0002_approval_history.py; cùng mã xử lý approvals.py, workflows.py, audit.py, worker.py, permissions.py và retrieval.py. Commit nền là 768d4a0; bản mô tả schema tính cả working tree hiện tại.')
h('2 Quy ước đọc tài liệu')
p('PK là khóa chính; FK là khóa ngoại; UQ là duy nhất. Cột Null ghi Có khi cho phép NULL. Các giá trị mặc định ghi trong từ điển là mặc định ORM ở phía ứng dụng, không tự động trở thành DEFAULT trong PostgreSQL. Ngoại lệ liên quan migration 0002 được nêu riêng ở phần triển khai.')
p('Quan hệ một tới nhiều cho phép phía con có không hoặc nhiều bản ghi. FK không NULL bắt buộc mỗi bản ghi con trỏ tới một bản ghi cha, nhưng không bắt buộc bản ghi cha phải có con. Các tham chiếu nằm trong JSON không có bảo đảm khóa ngoại.')

# Full ERD source includes every FK and every table, including disconnected ones.
mermaid=['erDiagram']
for t in META:
    mermaid.append('    '+t['name']+' {')
    for c in t['columns']:
        typ=re.sub(r'[^A-Za-z0-9_]','_',c['type']).strip('_')
        marker=' PK' if c['pk'] else ' FK' if c['fks'] else ' UK' if c['unique'] else ''
        mermaid.append(f"        {typ} {c['name']}{marker}")
    mermaid.append('    }')
for t in META:
    for c in t['columns']:
        for fk in c['fks']:
            parent=fk['target'].split('.')[0]
            unique=c['unique'] or c['pk']
            left='|o' if c['nullable'] else '||'
            right='o|' if unique else 'o{'
            mermaid.append(f'    {parent} {left}--{right} {t["name"]} : "{c["name"]}"')
(ROOT/'erd.mmd').write_text('\n'.join(mermaid),encoding='utf-8')

def diagram(filename,nodes,edges):
    img=Image.new('RGB',(1500,850),'white');draw=ImageDraw.Draw(img)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    for a,b,label in edges:
        x,y=nodes[a];u,v=nodes[b]
        if y==v:
            start=(x+235,y+45);end=(u,y+45)
            label_at=((start[0]+end[0])//2-30,y+14)
        else:
            start=(x+117,y+90);end=(u+117,v)
            label_at=(end[0]+8,end[1]-26)
        mid=(start[1]+end[1])//2
        draw.line([start,(start[0],mid),(end[0],mid),end],fill='#64748B',width=3)
        draw.ellipse((end[0]-5,end[1]-5,end[0]+5,end[1]+5),fill='#334155')
        draw.text(label_at,label,font=small,fill='#334155')
    for name,(x,y) in nodes.items():
        draw.rounded_rectangle((x,y,x+235,y+90),radius=8,fill='#EDF2F7',outline='#64748B',width=2)
        label=re.sub(r'__[ab]$','',name)
        box=draw.textbbox((0,0),label,font=font)
        draw.text((x+(235-box[2])/2,y+32),label,font=font,fill='black')
    img.save(ROOT/filename)

diagrams=[('erd-identity.png',{'roles':(70,55),'users':(70,230),'auth_sessions':(650,230),'conversations':(70,440),'messages':(650,440),'workflows':(70,650)},
 [('roles','users','1 : N'),('users','auth_sessions','1 : N'),('users','conversations','1 : N'),('conversations','messages','1 : N'),('conversations','workflows','1 : N')]),
 ('erd-workflow.png',{'workflows__a':(610,40),'workflow_steps':(50,230),'tool_executions':(610,230),'workflow_events':(1170,230),'workflows__b':(610,440),'approval_requests':(50,650),'reports':(610,650),'usage_records':(1170,650)},
 [('workflows__a','workflow_steps','1 : N'),('workflows__a','tool_executions','1 : N'),('workflows__a','workflow_events','1 : N'),('workflows__b','approval_requests','1 : 0..1'),('workflows__b','reports','1 : 0..1'),('workflows__b','usage_records','1 : 0..1')]),
 ('erd-business.png',{'products':(70,60),'inventory':(70,290),'sales':(640,290),'documents':(70,580),'document_chunks':(640,580),'approval_requests':(1040,60),'approval_decisions':(1040,290)},
 [('products','inventory','1 : 0..1'),('products','sales','1 : N'),('documents','document_chunks','1 : N'),('approval_requests','approval_decisions','1 : N')])]
doc.add_page_break();h('3 Sơ đồ quan hệ dữ liệu')
p('Sơ đồ được tách theo miền để dễ đọc. Các đường nối trong hình là quan hệ FK; con số thể hiện số lượng bản ghi phía con. Bảng đối chiếu ở mục 4 và tệp erd.mmd chứa toàn bộ 21 FK, gồm các liên kết người dùng được lược khỏi hình miền workflow và dữ liệu nghiệp vụ.')
for i,(filename,nodes,edges) in enumerate(diagrams):
    if i:doc.add_page_break()
    h(['3 1 Danh tính và hội thoại','3 2 Workflow và kết quả thực thi','3 3 Hàng hóa tài liệu và phê duyệt'][i],2)
    diagram(filename,nodes,edges);doc.add_picture(str(ROOT/filename),width=Inches(6.9))
    md.append(f'![ERD {i+1}]({filename})\n')
    if i==0:p('workflows.user_id cũng tham chiếu users.id. workflows.conversation_id cho phép NULL. permissions là danh mục độc lập; quyền gán cho vai trò được lưu trong roles.permissions.')
    if i==1:p('Hai nút workflows trong hình cùng biểu diễn một bảng, được lặp lại để tách rõ hai nhóm quan hệ. approval_requests, reports và usage_records đều có workflow_id duy nhất; workflow có thể chưa có bản ghi tương ứng.')
    if i==2:p('Các bảng audit_logs, system_settings và jobs không có FK. inventory.product_id là PK nên không có nhiều bản ghi tồn kho cho cùng sản phẩm. Không có bảng kho riêng trong thiết kế hiện tại.')

doc.add_page_break();h('4 Danh mục quan hệ khóa ngoại')
relations=[]
for t in META:
    for c in t['columns']:
        for fk in c['fks']:
            relations.append((t['name']+'.'+c['name'],fk['target'],'Có' if c['nullable'] else 'Không',fk['ondelete'] or 'NO ACTION'))
table(['Cột tham chiếu','Cột đích','Null','ON DELETE'],relations,[2.6,2.55,.55,1.2])
p('NO ACTION là hành vi mặc định khi không khai báo ON DELETE. Không suy diễn xóa dây chuyền ngoài hai FK messages.conversation_id và document_chunks.document_id. Workflow hoặc các quan hệ khác còn tham chiếu có thể chặn xóa bản ghi cha.')

h('5 Từ điển dữ liệu')
p('Từ điển liệt kê đầy đủ 143 cột của 22 bảng ứng dụng. Bảng alembic_version là bảng hạ tầng của Alembic, không được tính vào số bảng ứng dụng.')
for g,(title,names) in enumerate(GROUPS,1):
    h(f'5 {g} {title}',2)
    for name in names:
        t=TABLES[name];h(name,3);p(DESCRIPTIONS[name])
        rows=[]
        for c in t['columns']:
            notes=FIELDS.get(c['name'],c['name'])
            flags=[]
            if c['pk']:flags.append('PK')
            if c['unique']:flags.append('UQ')
            if c['fks']:flags.append('FK '+c['fks'][0]['target'])
            if flags:notes+='; '+', '.join(flags)
            default=c['default']
            if default is not None:
                if default=='do ứng dụng tạo':default='{}' if c['type']=='JSON' and c['name'] not in ('plan','permissions') else '[]' if c['name'] in ('plan','permissions') else default
                notes+='; mặc định '+("chuỗi rỗng" if default=='' else default)
            if name=='audit_logs' and c['name']=='id':notes+='; tự tăng'
            typ=c['type'].replace('TIMESTAMP WITH TIME ZONE','TIMESTAMPTZ')
            rows.append((c['name'],typ,'Có' if c['nullable'] else 'Không',notes))
        table(['Cột','Kiểu PostgreSQL','Null','Ý nghĩa và ràng buộc'],rows,[1.4,1.45,.5,3.55])
        if t['constraints']:p('Ràng buộc bổ sung: '+'; '.join(t['constraints'])+'.')

h('6 Chỉ mục và tối ưu truy vấn')
p('Các PK và UNIQUE tạo chỉ mục hỗ trợ tương ứng trong PostgreSQL. Các chỉ mục đơn được mapping khai báo như sau; tên cột không có trong danh sách không được coi là đã có index chỉ vì là khóa ngoại.')
indexes=[]
for t in META:
    if t['indexes']:
        parts=[]
        for statement in t['indexes']:
            parts.append(statement[statement.find('('):].strip()+(' UNIQUE' if 'CREATE UNIQUE' in statement else ''))
        indexes.append((t['name'],'; '.join(parts)))
table(['Bảng','Chỉ mục tường minh theo cột'],indexes,[2.1,4.8])
p('Migration 0001 tạo thêm document_chunks_vector_idx bằng HNSW trên embedding với vector_cosine_ops. Truy xuất tài liệu lọc trạng thái, scope và model, sau đó lấy tối đa 5 kết quả theo cosine distance. Hiệu quả thực tế cần đo bằng EXPLAIN ANALYZE trên bộ dữ liệu triển khai.')
p('Đề xuất khi dữ liệu tăng: đánh giá index ghép sales(product_id, date), workflows(user_id, created_at) và jobs(status, created_at). Tìm tên hàng bằng ILIKE có ký tự đại diện đầu chuỗi cần cân nhắc pg_trgm. Đây là đề xuất mở rộng, chưa phải chỉ mục có sẵn trong schema.')

h('7 Quy tắc nghiệp vụ và giao dịch')
h('7 1 Tra cứu dữ liệu hàng hóa',2)
p('Công cụ lookup_products đọc products bằng tên, SKU, danh mục hoặc product_id, ưu tiên tên hoặc SKU khớp chính xác. Kết quả có tối đa 20 sản phẩm và giá lấy trực tiếp từ products.price. Nếu nhiều kết quả phù hợp, câu trả lời liệt kê lựa chọn để người dùng xác định sản phẩm. Dữ liệu tồn kho lấy từ inventory, còn doanh thu lấy từ sales.')
p('Agent không cung cấp câu SQL tự do. Với PostgreSQL, truy vấn đọc được thực hiện trong transaction READ ONLY với statement_timeout 2500 ms. AGENT_DATABASE_URL có thể cấu hình kết nối đọc riêng; khi không cấu hình, hệ thống dùng cùng engine nhưng vẫn thiết lập transaction chỉ đọc.')
h('7 2 Phê duyệt điều chỉnh tồn kho',2)
p('Bước đề xuất lưu product_id, quantity, before và version trong approval_requests.arguments mà chưa thay đổi tồn kho. Người duyệt phải có quyền phù hợp; yêu cầu còn pending, đúng revision và chưa hết hạn.')
p('Khi phê duyệt, ứng dụng khóa yêu cầu phê duyệt và workflow bằng SELECT FOR UPDATE, sau đó cập nhật inventory với điều kiện version trùng giá trị đề xuất. Câu UPDATE tăng version thêm một. Nếu số dòng cập nhật khác một, thao tác bị từ chối do xung đột. Tồn kho, trạng thái phê duyệt, quyết định, audit và sự kiện được commit trong cùng giao dịch xử lý quyết định.')
h('7 3 Khôi phục workflow và xử lý job',2)
p('workflows.idempotency_key, các UNIQUE(workflow_id, position), checkpoint và workflow_id duy nhất ở bảng báo cáo hỗ trợ chống nhân đôi và tiếp tục xử lý. Đây là cơ chế idempotency cho các thao tác đã triển khai, không phải bảo đảm exactly once cho mọi công cụ hoặc dịch vụ ngoài hệ thống.')
p('Worker lấy job bằng FOR UPDATE SKIP LOCKED; lease_until cho phép nhận lại job running khi quá hạn giữ quyền. jobs.resource duy nhất ngăn tạo nhiều job cho cùng chuỗi định danh tài nguyên. Worker cập nhật heartbeat trong system_settings và tự chuyển các yêu cầu phê duyệt quá hạn sang expired.')
h('7 4 Audit và thứ tự sự kiện',2)
p('Audit dùng khóa advisory theo transaction để tuần tự hóa chuỗi HMAC. previous_hash nối tới bản ghi trước; hàm kiểm tra tính lại chuỗi từ đầu. Trigger PostgreSQL chặn UPDATE và DELETE từng dòng trên audit_logs. Trigger này không chặn TRUNCATE và không thay thế phân quyền database hay bảo vệ khóa HMAC.')
p('workflow_events.sequence là giá trị duy nhất toàn hệ thống. Ứng dụng cấp số từ MAX(sequence) cộng một dưới khóa advisory trong PostgreSQL, hỗ trợ client nối lại stream từ sự kiện đã nhận. Đây không phải cột identity tự tăng của PostgreSQL.')

h('8 Toàn vẹn dữ liệu và bảo mật')
p('Ràng buộc DB hiện có gồm PK, FK, UNIQUE và CHECK inventory.quantity >= 0. Các cột trạng thái, loại quyết định, scope và mã công cụ là VARCHAR, không phải PostgreSQL ENUM; giá trị hợp lệ chủ yếu được kiểm tra trong schema API và mã nghiệp vụ.')
p('Không có CHECK database cho products.price >= 0, sales.quantity >= 0, sales.revenue >= 0, inventory.threshold >= 0 hoặc inventory.version >= 1. Nếu mở thêm đường ghi dữ liệu hoặc tích hợp nhập dữ liệu, cần bổ sung validation và cân nhắc migration thêm CHECK trước khi đưa vào vận hành.')
p('roles.permissions lưu mảng quyền JSON để ứng dụng kiểm tra RBAC; chưa có khóa ngoại kiểm chứng từng mã quyền. documents.scope được lọc ở ứng dụng. Thiết kế hiện tại chưa triển khai PostgreSQL row level security; quyền truy cập dữ liệu phụ thuộc vào backend và quyền tài khoản database.')
p('Không lưu API key của nhà cung cấp AI trong bảng nghiệp vụ. Biến môi trường chứa bí mật phải được quản lý ngoài Git. auth_sessions chỉ lưu token hash; audit che các khóa payload nhạy cảm trước khi băm và ghi log. Lịch sử yêu cầu, kết quả công cụ và tài liệu có thể chứa dữ liệu nghiệp vụ, vì vậy cần hạn chế truy cập và có chính sách lưu giữ phù hợp.')

h('9 Migration sao lưu và khôi phục')
p('Revision 0001 tạo extension vector, bảng và index từ metadata, thêm HNSW index và trigger audit. Revision 0002 bổ sung approval_decisions.arguments nếu cột chưa tồn tại; nhánh thêm cột đặt server default JSON rỗng. Cài đặt mới lấy metadata hiện tại có thể đã có cột nên bỏ qua nhánh này; server default của cột có thể khác giữa database nâng cấp và cài mới.')
p('Lệnh triển khai chuẩn là alembic upgrade head từ thư mục backend. Vì 0001 tham chiếu metadata hiện tại, cần viết migration mới tường minh cho mọi thay đổi tiếp theo; chỉ sửa models.py không cập nhật một database đã áp dụng revision 0001. schema-reference.sql đi kèm là bản tham khảo cấu trúc, không thay thế lịch sử migration và không nên chạy chồng vào database hiện có.')
p('Khuyến nghị vận hành: sao lưu PostgreSQL bằng pg_dump, sao lưu riêng uploads và khóa audit ngoài database; mã hóa bản sao và kiểm soát quyền truy cập. Khôi phục sang môi trường tách biệt, chạy kiểm tra FK, đối chiếu số bản ghi, xác minh chuỗi audit và thử tra giá, tạo workflow, lập chỉ mục cùng luồng phê duyệt. Lịch sao lưu, thời hạn giữ và mục tiêu RPO RTO cần do nhóm vận hành chốt; mã nguồn hiện tại chưa cung cấp lịch sao lưu tự động.')

h('10 Chuẩn hóa và hướng mở rộng')
p('Các thực thể người dùng, sản phẩm, tồn kho, doanh số, workflow và quyết định phê duyệt được tách theo trách nhiệm và kết nối bằng khóa ngoại. JSON được dùng có chủ đích cho cấu trúc linh hoạt như kế hoạch, tham số, kết quả và quyền; nội dung bên trong JSON không được database kiểm tra quan hệ như các cột FK.')
p('Danh mục sản phẩm hiện là chuỗi products.category; chưa có bảng category, kho, đơn hàng hay chi tiết đơn hàng. sales là bản ghi doanh số phục vụ báo cáo, không phải mô hình kế toán hoặc đơn hàng hoàn chỉnh. Khi cần quản lý nhiều kho, cần thêm warehouses và khóa ghép tồn kho theo kho và sản phẩm bằng migration phù hợp.')
p('Ưu tiên mở rộng gồm chuẩn hóa role_permissions khi cần ràng buộc quyền chặt hơn, bổ sung CHECK cho đường ghi tài chính, tách snapshot và dữ liệu JSON lớn nếu truy vấn thường xuyên, đánh giá chỉ mục ghép bằng số liệu và thiết lập chính sách lưu giữ cho session, event, audit và tệp tải lên.')

# Footer page number for a long technical document.
footer=sec.footer.paragraphs[0];footer.alignment=2
r=footer.add_run('APBWAS  |  ');r.font.size=Pt(8)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
doc.save(ROOT/'APBWAS_Database_Design.docx')
(ROOT/'APBWAS_Database_Design.md').write_text('# Thiết kế cơ sở dữ liệu APBWAS\n\n'+'\n'.join(md),encoding='utf-8')
print('Saved',ROOT/'APBWAS_Database_Design.docx')
