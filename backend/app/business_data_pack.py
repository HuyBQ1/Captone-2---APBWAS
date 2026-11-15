"""Explicit, repeatable synthetic company data import. Never calls an LLM."""
import argparse,calendar,json
from collections import defaultdict
from datetime import date,datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select,text
from .db import Session
from .models import Product,Inventory,InventoryMovement,Sale,User,Document,DocumentFile,DocumentChunk,Job,Workflow,Report,SystemSetting,now
from .provider import embed,model_id,embedding_provider
from .config import settings
from .audit import audit
from .tools import revenue

PACK='nova-commerce-business-v1'
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
# Fictional, fixed prices in VND; these are not market-price recommendations.
CATALOG=[
 ('EL','Điện tử',[
  ('Màn hình NovaView 24 inch IPS',3290000),('Màn hình NovaView 27 inch QHD',4890000),('Webcam ClearMeet Full HD',690000),
  ('Bộ sạc nhanh PowerDock 65W',590000),('Hub kết nối LinkPro USB-C 7 cổng',790000),('Tai nghe có dây OfficeCall',249000)]),
 ('HM','Gia dụng',[
  ('Ổ cắm an toàn SafePlug 6 vị trí',289000),('Đèn bàn đọc sách Focus LED',389000),('Quạt bàn Breeze 30 cm',549000),
  ('Máy lọc không khí PureRoom S',2490000),('Ấm siêu tốc QuickBoil 1.7L',459000),('Hộp cơm giữ nhiệt LunchBox',329000)]),
 ('FR','Nội thất',[
  ('Bàn làm việc WorkDesk 120 cm',2290000),('Ghế văn phòng Comfort Mesh',1890000),('Tủ hồ sơ Archive 3 ngăn',1590000),
  ('Kệ màn hình DeskRise',349000),('Bàn họp MeetingDesk 180 cm',5690000),('Tủ locker cá nhân 6 ô',3290000)]),
 ('OF','Thiết bị văn phòng',[
  ('Máy in laser PrintOne M120',3290000),('Máy quét tài liệu ScanFlow A4',4490000),('Máy hủy tài liệu SecureCut',2190000),
  ('Máy in nhãn LabelDesk',1290000),('Máy chấm công TimeGate',2690000),('Máy ép plastic OfficeSeal A3',1190000)]),
 ('NW','Thiết bị mạng',[
  ('Router Wi-Fi 6 Connect AX1800',1290000),('Switch mạng Gigabit 8 cổng',690000),('Bộ phát Wi-Fi Mesh TwinPack',2490000),
  ('Cáp mạng Cat6 cuộn 100 m',1190000),('Access Point Ceiling AP1200',1890000),('Bộ lưu điện NetPower 650VA',1190000)]),
 ('ST','Văn phòng phẩm',[
  ('Giấy in OfficePaper A4 80gsm',89000),('Bút bi SmoothWrite hộp 12 cây',69000),('Bìa hồ sơ ArchiveFile hộp 10',129000),
  ('Sổ tay WorkNote A5',49000),('Giấy ghi chú StickyNote bộ 5',39000),('Mực in PrintOne TN120',449000)]),
 ('MT','Thiết bị hội nghị',[
  ('Loa hội nghị MeetSound USB',1490000),('Micro không dây VoiceMeet Duo',2290000),('Camera hội nghị WideMeet 4K',6490000),
  ('Bảng viết WhiteBoard 120 cm',1190000),('Bộ trình chiếu SlideRemote',390000),('Giá treo màn hình ConferenceMount',690000)]),
 ('DS','Thiết bị lưu trữ',[
  ('Ổ SSD ngoài PortableDrive 512GB',1190000),('Ổ SSD ngoài PortableDrive 1TB',1890000),('USB SecureFlash 64GB',199000),
  ('Thẻ nhớ DataCard 128GB',329000),('Ổ cứng BackupDrive 2TB',2190000),('Thiết bị NAS OfficeVault 2 khay',6490000)]),
]

POLICIES=[
 ('ORG-001','Giới thiệu doanh nghiệp và cơ cấu vận hành','all','Ban điều hành',[
  ('Mô hình hoạt động','Nova Commerce là doanh nghiệp thương mại B2B/B2C giả lập, cung cấp thiết bị và vật tư cho văn phòng. Bộ dữ liệu này phục vụ kiểm thử APBWAS, không đại diện doanh nghiệp đã đăng ký.'),
  ('Bộ phận','Kinh doanh tiếp nhận nhu cầu và xác nhận giao dịch. Kho vận kiểm đếm hàng, lập đề xuất bổ sung và bàn giao. Tài chính đối soát số liệu bán hàng. Nhân sự quản lý hồ sơ và onboarding. Quản trị hệ thống cấp tài khoản và phân quyền.'),
  ('Nguyên tắc','Mỗi hàng hóa có SKU duy nhất; mỗi giao dịch có mã tham chiếu riêng. Không dùng tên gọi thay khóa sản phẩm. Các thay đổi phải có người chịu trách nhiệm và audit trail.')]),
 ('SAL-001','Quy trình tiếp nhận và ghi nhận bán hàng','all','Kinh doanh',[
  ('Tiếp nhận','Nhân viên xác định đúng SKU, số lượng, tình trạng kinh doanh và tồn kho khả dụng trước khi xác nhận với khách. Khi tồn không đủ, ghi nhận nhu cầu và chuyển kho vận, không ghi nhận bán vượt tồn.'),
  ('Xác nhận','Người có quyền business.manage và sales.read dùng Ghi nhận bán hàng, xem đơn giá và thành tiền, đánh dấu xác nhận rồi gửi. Giá lấy từ database, không dùng số AI tự suy đoán.'),
  ('Đối soát','Một lần ghi nhận thành công phải có sale, số tồn sau bán, inventory movement và audit. Nếu mất kết nối, gửi lại cùng mã tham chiếu để chống ghi trùng. Ứng dụng chưa quản lý hóa đơn thuế, khách hàng hoặc trạng thái giao vận.')]),
 ('SAL-002','Quy tắc báo giá và thay đổi danh mục','Manager','Kinh doanh',[
  ('Nguồn giá','Giá niêm yết lấy từ products.price, đơn vị VND. Chỉ người có quyền quản lý danh mục được sửa giá; thay đổi kiểm tra product_version.'),
  ('Lịch sử','Doanh thu lịch sử giữ nguyên giá trị đã ghi nhận trong sales.revenue; không tính lại theo giá niêm yết hiện tại. Bộ dữ liệu mẫu không áp dụng chiết khấu hoặc phí vận chuyển.'),
  ('Ngừng kinh doanh','Ngừng kinh doanh thay cho xóa SKU có lịch sử. Không phát sinh sale mới với hàng ngừng kinh doanh. Việc điều chỉnh tồn hàng cũ vẫn cần quy trình phê duyệt.')]),
 ('SAL-003','Xử lý yêu cầu đổi trả và khiếu nại','all','Chăm sóc khách hàng',[
  ('Tiếp nhận','Ghi rõ mã giao dịch, SKU, số lượng, mô tả lỗi và bằng chứng do khách cung cấp. Không ghi thông tin thanh toán nhạy cảm vào chat AI.'),
  ('Phân loại','Phân biệt thiếu hàng, sai SKU, lỗi kỹ thuật và yêu cầu ngoài chính sách. Chuyển quản lý xem xét trước khi cam kết hoàn tiền hoặc đổi hàng.'),
  ('Giới hạn hệ thống','APBWAS hiện chưa có module hoàn tiền/credit note. Không tạo sale âm hoặc sửa doanh thu cũ để giả lập hoàn tiền. Nếu cần điều chỉnh số tồn, thực hiện đề xuất riêng và lưu lý do/bằng chứng.')]),
 ('WH-001','Quy trình nhập kho và kiểm đếm','all','Kho vận',[
  ('Tiếp nhận','Đối chiếu SKU, số lượng, tình trạng bao bì và hồ sơ bàn giao. Tách riêng hàng chưa đạt chất lượng; không gộp vào tồn sẵn bán.'),
  ('Ghi nhận','Trong ứng dụng, điều chỉnh tồn thực tế bằng đề xuất inventory.propose, nêu product_id và số lượng sau kiểm đếm. Người được cấu hình approvals.decide kiểm tra rồi duyệt.'),
  ('Kiểm soát','Không ghi tồn trực tiếp bằng câu lệnh SQL hay yêu cầu AI bỏ qua phê duyệt. Kiểm tra inventory_version; nếu có giao dịch mới, tạo revision với số liệu cập nhật.')]),
 ('WH-002','Ngưỡng tồn kho và kế hoạch bổ sung','Manager','Kho vận',[
  ('Cảnh báo','Hàng sắp hết khi quantity <= threshold; quantity bằng 0 là hết hàng. Ngưỡng từng SKU được cấu hình theo nhóm, không dùng một ngưỡng chung cho mọi sản phẩm.'),
  ('Kế hoạch','Xem doanh số gần đây và số tồn thực tế trước khi lập kế hoạch bổ sung. Ưu tiên SKU hết hàng, sau đó SKU dưới ngưỡng. Không tự kết luận thời gian giao của nhà cung cấp khi chưa có dữ liệu.'),
  ('Dữ liệu mẫu','Bộ NCV1 mô phỏng một lần nhập đầu kỳ mỗi tháng và các đợt bán trong tháng. Tám SKU mới được đặt mức tồn thấp để kiểm thử cảnh báo, bốn trong số đó có số tồn bằng 0.')]),
 ('WH-003','Kiểm kê định kỳ và xử lý chênh lệch','all','Kho vận',[
  ('Chuẩn bị','Chốt danh sách SKU, số lượng hệ thống và mốc thời gian kiểm kê. Ghi nhận các giao dịch diễn ra trong thời gian đếm để tránh so sai mốc.'),
  ('Chênh lệch','Đếm lại độc lập khi có chênh lệch. Kiểm tra lịch sử nhập/xuất và các phê duyệt. Không xóa movement hoặc audit để làm khớp số liệu.'),
  ('Xử lý','Lập đề xuất điều chỉnh với lý do, chứng cứ và số lượng thực tế. Phê duyệt kiểm tra revision, quyền hiện tại và version tồn kho. Hệ thống giữ nguyên số trước/sau trong ledger.')]),
 ('OPS-001','Bàn giao hàng và phối hợp vận hành','all','Vận hành',[
  ('Chuẩn bị','Kho vận đối chiếu hàng đã xác nhận với SKU, số lượng và tình trạng đóng gói. Người bàn giao và người nhận xác nhận danh sách trên hệ thống vận hành phù hợp.'),
  ('Phối hợp','Kinh doanh thông báo kịp thời thay đổi yêu cầu. Kho vận không thay SKU tương đương nếu chưa có xác nhận. Khi thiếu hàng, dừng bàn giao phần thiếu và báo quản lý.'),
  ('Giới hạn','Bộ APBWAS hiện chưa có kết nối hãng vận chuyển hoặc module đơn hàng nhiều dòng. Không coi sale trong database là bằng chứng đã giao hàng.')]),
 ('FIN-001','Hướng dẫn đọc báo cáo doanh thu','Manager','Tài chính',[
  ('Định nghĩa','Doanh thu trong bản mẫu là tổng sales.revenue của các dòng giao dịch trong kỳ, nhóm theo danh mục products.category. Giá trị này không phải lợi nhuận, dòng tiền hoặc hóa đơn thuế.'),
  ('Kỳ báo cáo','Kỳ tháng dùng múi giờ Asia/Ho_Chi_Minh, từ đầu tháng đến trước đầu tháng kế tiếp. Báo cáo là snapshot tại thời điểm tạo; dữ liệu bổ sung sau đó không sửa báo cáo cũ.'),
  ('So sánh','Tháng hiện tại chưa kết thúc phải ghi rõ ngày chốt số liệu. Không xem biến động so với tháng trước đầy đủ là so sánh cùng số ngày. Chưa có dữ liệu chi phí để suy luận nguyên nhân hay lợi nhuận.')]),
 ('FIN-002','Quy trình đối soát số liệu cuối kỳ','Manager','Tài chính',[
  ('Kiểm tra','Đối chiếu tổng dòng doanh thu với tổng theo danh mục. Kiểm tra SKU tồn tại, số lượng dương, mã giao dịch duy nhất và đơn vị VND.'),
  ('Chốt kỳ','Tạo báo cáo mới sau khi hoàn tất nạp/đối soát; lưu thời điểm và phiên bản dữ liệu. Giữ báo cáo trước đó để truy vết thay đổi, không ghi đè snapshot đã phát hành.'),
  ('Ngoại lệ','Các giao dịch legacy có thể không có mã tham chiếu hoặc ledger đầy đủ. Phải phân biệt với NCV1, không tự tạo chứng từ cũ hay bịa người phê duyệt.')]),
 ('HR-001','Hướng dẫn onboarding nhân viên','all','Nhân sự',[
  ('Tài khoản','Admin mời hoặc cấp tài khoản theo vai trò được phê duyệt. Nhân viên tự thiết lập mật khẩu riêng; mật khẩu tạm phải đổi trước khi truy cập nghiệp vụ.'),
  ('Hồ sơ','Cập nhật họ tên, điện thoại, phòng ban và chức danh. Vai trò do quản trị viên cấp, không dùng chức danh tự nhập để suy ra quyền truy cập.'),
  ('Bàn giao','Đọc quy trình bán hàng, kho vận và bảo mật liên quan. Kiểm tra các thiết bị đang đăng nhập; kết thúc phiên không sử dụng. Khi nghỉ việc, Admin khóa tài khoản và thu hồi phiên.')]),
 ('HR-002','Quy trình đăng ký nghỉ và bàn giao công việc','all','Nhân sự',[
  ('Đăng ký','Nhân viên gửi yêu cầu theo quy trình nhân sự của doanh nghiệp, nêu ngày nghỉ, người nhận bàn giao và các đầu việc đang xử lý. Nội dung này chỉ là quy trình mô phỏng, không xác định quyền lợi pháp lý.'),
  ('Bàn giao','Bàn giao các báo cáo, tài liệu và yêu cầu phê duyệt đang chờ; không chuyển mật khẩu cá nhân cho người thay thế. Người quản lý phân công lại qua tài khoản riêng.'),
  ('Theo dõi','APBWAS chưa có module chấm công/nghỉ phép; không coi một câu trả lời AI là phê duyệt nghỉ. Quyền lợi và số ngày nghỉ cần đối chiếu chính sách nhân sự đã được doanh nghiệp ban hành.')]),
 ('IT-001','Quy định bảo mật tài khoản và dữ liệu','all','Công nghệ thông tin',[
  ('Mật khẩu','Không chia sẻ mật khẩu hoặc token khôi phục. Liên kết kích hoạt dùng một lần trong 24 giờ; khôi phục trong một giờ. Khi nghi ngờ lộ mật khẩu, đổi ngay và kiểm tra các phiên đăng nhập.'),
  ('Dữ liệu','Chỉ xem tài liệu đúng phạm vi quyền. Không dán API key, thông tin thẻ hoặc dữ liệu khách hàng nhạy cảm vào chat. Mật khẩu được hash, không có chức năng xem mật khẩu hiện tại.'),
  ('Sự cố','Thông báo Admin khi có phiên lạ hoặc mất thiết bị. Admin khóa tài khoản nếu cần và giữ audit trail. Không tự xóa log để xử lý sự cố.')]),
 ('IT-002','Vận hành tài khoản và ma trận quyền','Admin','Quản trị hệ thống',[
  ('Phân quyền','Admin quản trị tài khoản, cấu hình và danh mục. Manager mặc định đọc doanh thu, quản lý tài liệu, đề xuất/duyệt tồn. Employee chỉ đọc phạm vi được cấp. business.manage là quyền riêng cho vận hành danh mục/bán hàng.'),
  ('Khôi phục','Xác minh người nhận trước khi cấp liên kết mới. Cấp liên kết mới vô hiệu liên kết cũ. Hiện chưa cấu hình SMTP, Admin chuyển liên kết riêng; không thông báo đã gửi email tự động.'),
  ('Kiểm soát','Không tái kích hoạt tài khoản mẫu dùng chung để thay cho tài khoản cá nhân. Khóa/đổi vai trò phải thu hồi phiên. API kiểm tra quyền hiện tại cho mỗi yêu cầu.')]),
 ('IT-003','Sao lưu khôi phục và xử lý sự cố','Admin','Quản trị hệ thống',[
  ('Sao lưu','Dùng scripts/backup.ps1 để tạo PostgreSQL custom archive. File gốc, nội dung, vector và metadata đều nằm trong database. Bảo vệ bản backup vì có dữ liệu nhân sự và kinh doanh.'),
  ('Khôi phục','Restore vào database mới, kiểm tra schema, số bản ghi và audit integrity trước khi đổi cấu hình. Giữ audit signing key riêng; database dump không chứa secret môi trường.'),
  ('Giới hạn','Không dùng docker compose down -v trên stack chính để cập nhật. Lịch sao lưu ngoài máy, HTTPS và kiểm thử tải sản xuất phải được vận hành riêng.')]),
 ('DQ-001','Từ điển dữ liệu và quy tắc chất lượng','all','Quản trị dữ liệu',[
  ('Hàng hóa','SKU là mã duy nhất; product_id là khóa nội bộ. product_version bảo vệ sửa giá/danh mục, inventory_version bảo vệ điều chỉnh số tồn; hai phiên bản không thay thế nhau.'),
  ('Giao dịch','quantity là số lượng nguyên dương của sale; revenue là giá trị VND đã ghi nhận. before/after của movement là số tồn trước/sau giao dịch. Không suy ra số lượng nhập từ doanh thu.'),
  ('Nguồn dữ liệu','NCV1 là bộ dữ liệu tổng hợp do người vận hành nhập. Dòng NCV1 có mã tham chiếu để đối chiếu; dữ liệu legacy được giữ riêng. Không trộn dữ liệu mẫu với doanh nghiệp thật mà bỏ nhãn nguồn.')]),
 ('AI-001','Hướng dẫn dùng trợ lý nghiệp vụ có dẫn nguồn','all','Vận hành',[
  ('Hàng hóa','Hỏi theo tên đầy đủ hoặc SKU để tra giá/tồn. Giá và số lượng phải lấy từ products/inventory, không đoán từ tài liệu hoặc kiến thức chung của mô hình.'),
  ('Tài liệu','Hỏi quy trình/chính sách để tìm nguồn được phép xem. Mở nguồn và kiểm tra phiên bản. Nếu chưa đủ bằng chứng, yêu cầu thêm tài liệu; không tự bổ sung sự kiện.'),
  ('Giới hạn','Agent lập kế hoạch theo allowlist; điều chỉnh tồn cần người duyệt. Lexical retrieval hiện tại không phải mô hình tìm kiếm ngữ nghĩa. Không gửi lệnh yêu cầu bỏ qua quyền hoặc lộ system prompt.')]),
 ('OPS-002','Quy trình quản lý tài sản và thiết bị văn phòng','Manager','Vận hành',[
  ('Phân biệt','Hàng hóa để bán thuộc inventory; thiết bị cấp cho nhân viên là tài sản sử dụng nội bộ, cần sổ theo dõi tài sản riêng. APBWAS chưa có asset register.'),
  ('Bàn giao','Khi cấp thiết bị, ghi nhận người nhận, thời điểm, tình trạng và bằng chứng trong hệ thống quản lý phù hợp. Không tạo sale giả để thay cho bàn giao tài sản.'),
  ('Bảo trì','Lập lịch kiểm tra thiết bị quan trọng, đối chiếu phạm vi bảo hành từ nhà cung cấp. Không tự suy luận thời hạn bảo hành cho SKU chưa có hồ sơ.')]),
]

def next_month(day):
    return date(day.year+(day.month==12),day.month%12+1,1)

def import_pack(db,as_of):
    if db.get(SystemSetting,'sample-data-removed-v1'):raise ValueError('Dữ liệu mẫu đã được xóa theo yêu cầu; không tự nạp lại.')
    if not (settings.sample_data or settings.demo_mode):raise ValueError('Bộ dữ liệu này chỉ dành cho môi trường được đánh dấu SAMPLE_DATA/DEMO_MODE.')
    if embedding_provider()!='lexical':raise ValueError('Import không gọi dịch vụ AI bên ngoài; cần lexical embeddings để nạp bộ mẫu.')
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730030)'))
    existing=db.get(SystemSetting,PACK)
    if existing:return {**existing.value,'already_imported':True}
    cutoff=min(datetime.combine(as_of,datetime.max.time(),TZ),now().astimezone(TZ))
    if as_of.year!=2026 or as_of>now().astimezone(TZ).date():raise ValueError('Bộ v1 dành cho năm 2026 và không tạo giao dịch tương lai.')
    admin=db.scalar(select(User).where(User.role=='Admin',User.active.is_(True)).order_by(User.created_at.desc()))
    manager=db.scalar(select(User).where(User.role=='Manager',User.active.is_(True)).order_by(User.created_at.desc()))
    if not admin or not manager:raise ValueError('Cần tài khoản Admin và Manager đang hoạt động trước khi nhập.')
    if db.scalar(select(Product.id).where(Product.sku.like('NC-%')).limit(1)):raise ValueError('Có SKU NC-* chưa có manifest; cần đối soát trước, không ghi đè sản phẩm.')
    months=[];cursor=date(2026,1,1)
    while cursor<=as_of:months.append(cursor);cursor=next_month(cursor)
    counters={'products':0,'sales':0,'movements':0,'documents':0,'reports':0,'low_stock_products':0,'out_of_stock_products':0}
    product_ids=[];document_ids=[];report_ids=[];total_revenue=0;sku_index=0
    category_lines=defaultdict(list)
    for code,category,items in CATALOG:
        for number,(name,price) in enumerate(items,1):
            sku_index+=1;sku=f'NC-{code}-{number:03}'
            product=Product(sku=sku,name=name,category=category,price=price,created_at=datetime(2026,1,1,8,tzinfo=TZ))
            db.add(product);db.flush();product_ids.append(product.id)
            threshold=20+(sku_index%4)*5
            closing=(sku_index%4)*3 if sku_index%6==0 else threshold+40+(sku_index%5)*11
            inventory=Inventory(product_id=product.id,quantity=0,threshold=threshold,version=1);db.add(inventory)
            balance=0;event_count=0
            for month in months:
                events=[]
                for day in [2,5,9,13,16,20,24,28]:
                    if day>calendar.monthrange(month.year,month.month)[1]:continue
                    when=datetime(month.year,month.month,day,9,sku_index%60,tzinfo=TZ)
                    if when>cutoff or when.weekday()==6:continue
                    quantity=1+(sku_index*3+month.month+day)%5+min(month.month//3,3)
                    if code=='ST':quantity*=4
                    events.append((when,quantity))
                if not events:continue
                units=sum(q for _,q in events);receipt=units+closing-balance
                if receipt<0:raise ValueError('Kế hoạch tồn kho mẫu không hợp lệ.')
                receipt_time=datetime(month.year,month.month,1,8,tzinfo=TZ)
                db.add(InventoryMovement(product_id=product.id,user_id=admin.id,reference=f'NCV1-R-{month:%Y%m}-{sku}',
                       before=balance,after=balance+receipt,reason='Nhập lịch sử mẫu NCV1: nhập đầu kỳ '+month.strftime('%Y-%m'),created_at=receipt_time))
                counters['movements']+=1;event_count+=1;balance+=receipt
                for when,quantity in events:
                    reference=f'NCV1-S-{when:%Y%m%d}-{sku}'
                    value=price*quantity
                    db.add(Sale(product_id=product.id,date=when,quantity=quantity,revenue=value,reference=reference,created_at=when))
                    db.add(InventoryMovement(product_id=product.id,user_id=admin.id,reference=reference,before=balance,after=balance-quantity,
                           reason='Nhập lịch sử mẫu NCV1: bán hàng '+when.strftime('%d/%m/%Y'),created_at=when))
                    balance-=quantity;total_revenue+=value;event_count+=1;counters['sales']+=1;counters['movements']+=1
            inventory.quantity=balance;inventory.version=1+event_count
            if balance<=threshold:counters['low_stock_products']+=1
            if balance==0:counters['out_of_stock_products']+=1
            counters['products']+=1
            category_lines[category].append(f'- {sku}: {name}; giá niêm yết mẫu {price:,} VND; ngưỡng cảnh báo {threshold} đơn vị.'.replace(',','.'))
    db.flush()

    documents=list(POLICIES)
    for i,(category,lines) in enumerate(category_lines.items(),1):
        documents.append((f'CAT-{i:03}',f'Danh mục và hướng dẫn nhóm {category}','all','Quản trị danh mục',[
            ('Danh mục niêm yết mẫu','\n'.join(lines)),('Sử dụng','Tài liệu là snapshot mô tả bộ NCV1. Giá và tồn kho hiện tại luôn tra bằng business tools; thay đổi sau ngày nhập không tự sửa tài liệu này.'),
            ('Đối soát','Mỗi SKU có lịch sử bán và nhập đầu kỳ. Không kết luận hiệu năng, chất lượng hoặc bảo hành sản phẩm từ bộ dữ liệu mô phỏng này.')]))
    for code,title,scope,department,sections in documents:
        content=f'NOVA COMMERCE — DỮ LIỆU DOANH NGHIỆP MẪU\nTiêu đề: {title}\nMã tài liệu: NC-{code}\nPhiên bản: 1.0\nNgày chốt dữ liệu: {as_of:%d/%m/%Y}\nĐơn vị phụ trách: {department}\nPhạm vi: {scope}\nNguồn: {PACK}; không phải hồ sơ doanh nghiệp thực tế.\n\n'
        content+='\n\n'.join(f'{i}. {heading}\n{body}' for i,(heading,body) in enumerate(sections,1))
        doc=Document(user_id=admin.id,name=f'[NC-{code}] {title}.txt',scope=scope,status='indexed',content=content)
        db.add(doc);db.flush();document_ids.append(doc.id)
        db.add(DocumentFile(document_id=doc.id,content=content.encode('utf-8')))
        position=0
        for offset in range(0,len(content),850):
            chunk=content[offset:offset+1000].strip()
            if chunk:db.add(DocumentChunk(document_id=doc.id,content=chunk,position=position,embedding=embed(chunk),model=model_id()));position+=1
        doc.chunks=position;db.add(Job(resource=doc.id,kind='document',status='done'));counters['documents']+=1
        audit(db,admin,'dataset.document_imported',doc.id,{'code':code,'scope':scope,'dataset':PACK})
    db.flush()
    # SQL snapshots, not invented AI output; no provider call or private chat is created.
    for month in months:
        data=revenue(db,month.strftime('%Y-%m'),cutoff=cutoff)
        partial=month.year==as_of.year and month.month==as_of.month and as_of.day<calendar.monthrange(as_of.year,as_of.month)[1]
        note=f'Snapshot SQL sau nạp {PACK}; chốt đến {as_of:%d/%m/%Y}. '
        if partial:note+='Kỳ hiện tại chưa đủ tháng; kỳ trước là tháng đầy đủ, không phải so sánh cùng số ngày. '
        data={**data,'dataset':PACK,'as_of':as_of.isoformat(),'partial_period':partial,'source':data['source']+' • dữ liệu mẫu NCV1','summary':note+data['summary']}
        workflow=Workflow(user_id=manager.id,request=f'Nhập snapshot doanh thu {month:%Y-%m} từ bộ dữ liệu mẫu NCV1 (SQL, không gọi AI).',
                          idempotency_key=f'NCV1-REPORT-{month:%Y%m}',status='completed',tokens=0,checkpoint=0)
        db.add(workflow);db.flush()
        report=Report(workflow_id=workflow.id,user_id=manager.id,title=f'Nova Commerce · Doanh thu {month:%m/%Y}'+(' · Chưa đủ tháng' if partial else ''),data=data)
        db.add(report);db.flush();report_ids.append(report.id)
        workflow.result={**data,'report_id':report.id};db.add(Job(resource=workflow.id,kind='workflow',status='done'))
        counters['reports']+=1
        audit(db,admin,'dataset.report_imported',report.id,{'month':data['month'],'total':data['total'],'dataset':PACK},workflow.id)
    manifest={'dataset':PACK,'synthetic':True,'as_of':as_of.isoformat(),'from':'2026-01-01','currency':'VND','counts':counters,
              'imported_sales_revenue_vnd':total_revenue,'product_ids':product_ids,'document_ids':document_ids,'report_ids':report_ids,
              'rules':['Existing records preserved.','Sales and stock movements reconciled for NCV1 only.','Reports include existing sales plus NCV1.','No external AI calls.']}
    db.add(SystemSetting(key=PACK,value=manifest));audit(db,admin,'dataset.imported',PACK,{'as_of':as_of.isoformat(),'counts':counters,'sales_revenue_vnd':total_revenue})
    db.commit()
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--as-of',type=date.fromisoformat,default=datetime.now(TZ).date());args=parser.parse_args()
    with Session() as db:print(json.dumps(import_pack(db,args.as_of),ensure_ascii=True,indent=2))
