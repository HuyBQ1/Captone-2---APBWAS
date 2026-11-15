# Excel, số đơn và lời lỗ theo tháng

## Cách dùng

Mở **Dữ liệu doanh nghiệp → Excel & lời lỗ**, chọn tháng, rồi **Xuất Excel có công thức**. File gồm TongHop, BanHang, TonKho và ChiPhi.

Trong BanHang, nhập mã đơn ở cột D và giá vốn mỗi đơn vị ở cột G. Mã đơn được chuẩn hóa thành chữ hoa; các dòng cùng mã được tính một đơn. Trong ChiPhi, nhập mã chi phí duy nhất, ngày Excel, danh mục, số tiền VND và ghi chú. Khi đã kiểm tra đủ chi phí của tháng, đặt TongHop!B5 thành 1; nếu chưa đủ để 0.

Lưu Excel, dùng **Nhập Excel tài chính**, kiểm tra bản xem trước rồi **Xác nhận nhập vào database**. Chỉ người có business.manage, sales.read và inventory.read được nhập. Nhập lặp cùng bản xem trước không ghi trùng. Xuất file mới khi database đã thay đổi; bản xem trước hết hạn sau 24 giờ. File gốc, giá trị trước/sau và lịch sử nhập được lưu trong database. Không xóa dòng chi phí đã có. Sửa chi phí bằng cùng mã trong file mới rồi xem trước và xác nhận lại.

Có thể ghi chi phí ngay trên màn hình. Thêm chi phí sẽ mở lại trạng thái kiểm tra đầy đủ của tháng. Ghi nhận bán hàng mới có trường giá vốn tùy chọn; giá vốn được lưu riêng cho từng dòng bán, không tính lại lịch sử theo giá hiện tại. Giao dịch mới do form bán hàng tạo là một đơn một dòng, mã đơn lấy từ mã tham chiếu. File nhập hỗ trợ gộp các dòng cùng mã đơn.

## Ý nghĩa kết quả

- Doanh thu = tổng giá trị bán đã ghi nhận trong tháng, theo múi giờ Việt Nam. Đây không phải số tiền đã thu.
- Giá vốn = tổng số lượng bán × giá vốn mỗi đơn vị của từng dòng. Trống là chưa biết; 0 là đã xác nhận bằng 0.
- Lợi nhuận gộp = doanh thu − giá vốn.
- Lợi nhuận vận hành = lợi nhuận gộp − chi phí đã nhập. Chỉ hiện khi đủ giá vốn và đã xác nhận đủ chi phí. Không thay thế báo cáo lợi nhuận sau thuế hay sổ kế toán pháp định.
- Tổng số đơn chỉ xác định khi mọi dòng có mã đơn. Dữ liệu cũ thiếu mã được báo riêng, không coi số dòng bán là số đơn.
- Tồn kho trong file là số lượng hiện tại tại thời điểm xuất, không phải số cuối tháng hay đơn chưa giao. Không cộng tồn các tháng với nhau.

Dữ liệu cũ chưa có giá vốn, chi phí và mã đơn đáng tin cậy. Migration không tự bịa các giá trị đó. Cần điền từ chứng từ/file thực tế để có kết luận lời/lỗ.

### Bộ tài chính mô phỏng hoàn chỉnh

Theo yêu cầu hoàn thiện dữ liệu doanh nghiệp, có thêm CLI `python -m app.seed_finance_sample`. Chỉ chạy khi SAMPLE_DATA/DEMO_MODE được bật và chỉ xử lý các dòng NCV1 hoặc 8 SKU AP legacy đã nhận diện, trong các tháng 2026 đã kết thúc. Đây là bộ giả định mô phỏng, không chuyển thành chứng từ thực tế.

Bộ này điền các giá vốn và mã đơn còn trống, thêm sáu loại chi phí tháng và xác nhận hoàn chỉnh cho kỳ chỉ có dữ liệu mẫu, chưa có chi phí/xác nhận do người vận hành nhập. Không sửa giá vốn/mã đơn có sẵn, không ghi đè chi phí thủ công, không thay đổi doanh thu, số lượng bán hay tồn kho. Mỗi lần nhập là một transaction có audit và manifest `nova-finance-sample-v1` trong system_settings; chạy lại không ghi trùng. Manifest lưu các ID đã bổ sung và toàn bộ giả định chi phí để truy vết.

Giả định giá vốn: 62–81% giá bán lịch sử theo danh mục, làm tròn xuống 1.000 VND/đơn vị. Chi phí tháng mô phỏng gồm thuê kho/văn phòng 42 triệu, lương/phụ cấp 190 triệu, phần mềm/hạ tầng 12 triệu, khấu hao 8 triệu, vận chuyển 3% và tiếp thị 4% doanh thu mẫu. Mã đơn gom tối đa ba SKU NC cùng nhóm danh mục/ngày hoặc hai SKU AP/ngày. Các số đơn này là số đơn **mô phỏng**.

Trong AI Workspace, hỏi “tính lời lỗ Doanh thu 07/2026” sẽ nhận kết quả và phép tính từ công cụ. Tháng YYYY-MM, MM/YYYY hoặc “tháng 7 năm 2026” được chuẩn hóa vào ngữ cảnh. Connected Mode gọi Agent LLM để chọn công cụ/đối số trước khi backend đọc và tính; chỉ Demo Mode định tuyến cục bộ. Không tự chèn liên kết Excel vào mọi câu trả lời. Màn hình tài chính, câu trả lời và file xuất của những tháng đã bổ sung đều có nhãn mô phỏng. Hội thoại cũ được giữ nguyên lịch sử; gửi câu hỏi mới để dùng luồng mới.

Kiểm chứng bản hoàn thiện: **103 backend tests đạt**, **18 Playwright tests đạt**, gồm hỏi đúng câu tháng 07/2026 và đối chiếu phép tính ngay trong chat. Database chính được bổ sung 3.552 giá vốn, 3.552 mã đơn theo dòng và 60 chi phí mẫu cho 10 tháng. Hash đối chiếu xác nhận doanh thu/số lượng bán/tồn kho không đổi, audit hợp lệ, chạy import lại không ghi trùng. Tháng 7 trên database chính: 124 đơn mô phỏng, doanh thu 3.709.135.000 VND, giá vốn 2.680.994.000 VND, chi phí 511.639.000 VND, lãi vận hành 516.502.000 VND. Logs: `.test-tmp/finance-complete-backend.log`, `.test-tmp/finance-complete-e2e.log`.

## Trợ lý

Có thể hỏi **“Tính lời lỗ và số đơn hàng tháng 2026-10”**. Công cụ query_financial_summary đọc database và đưa liên kết tải Excel. Connected provider chỉ lập kế hoạch theo allowlist; tính toán thực hiện trong backend, không dùng AI tự đoán số. Không thực hiện cuộc gọi AI bên ngoài trong đợt kiểm thử tính năng này.

## Kỹ thuật và kiểm chứng

Migration 0005 bổ sung sales.unit_cost, sales.order_number, expenses, finance_periods và finance_imports. Các bảng và file Excel nhập nằm trong PostgreSQL, có trong bản sao lưu pg_dump. Không tự backfill mã đơn từ mã dòng NCV1 vì mã dòng không chứng minh đó là mã đơn thực tế.

Mẫu XLSX được tạo bằng Artifact Tool; runtime điền dữ liệu vào OpenXML và giữ công thức, định dạng, ngày dạng số, cached values và chế độ tự tính lại của Excel. Builder tại scripts/build_finance_template.mjs: sao chép vào thư mục tạm có node_modules junction tới bundled runtime rồi chạy bằng bundled Node, từ thư mục gốc dự án. Không cần cài thêm thư viện Excel vào backend.

Giới hạn mỗi file: 5.000 dòng bán, 2.000 SKU, 1.000 dòng chi phí; upload 8 MB, tổng giải nén 40 MB. File vượt giới hạn bị từ chối, không trả báo cáo bị cắt ngầm. Chỉ chấp nhận literal values cho ô dữ liệu nhập, không thực thi macro/công thức/liên kết bên ngoài. Công thức kết quả vẫn giữ trong file Excel. SKU, số lượng bán, doanh thu và tồn kho không nhập ngược từ file tài chính.

Kiểm thử cuối: **100 backend tests đạt trên PostgreSQL**, **17 Playwright tests đạt**, production build thành công. Bao gồm tính lời/lỗ 50.000 từ doanh thu 200.000, giá vốn 120.000, chi phí 30.000; phân biệt thiếu giá vốn với giá vốn 0; tháng theo giờ Việt Nam; đếm nhiều dòng cùng đơn; nhập nhiều dòng; stale file/preview; chống ghi trùng; giữ tồn kho; phân quyền; migration không mất dữ liệu. Logs trong .test-tmp/finance-backend.log và .test-tmp/finance-e2e.log.
