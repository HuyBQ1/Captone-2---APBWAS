# Bộ dữ liệu doanh nghiệp Nova Commerce — NCV1

Đã nạp vào database chính ngày **02/11/2026 (Asia/Ho_Chi_Minh)**. Đây là dữ liệu tổng hợp có đánh dấu mẫu, không phải thông tin của một doanh nghiệp thực tế. Không gọi dịch vụ AI bên ngoài để tạo nội dung hoặc số liệu.

## Dữ liệu đã bổ sung

| Loại | Bổ sung | Tổng trong database sau nhập |
|---|---:|---:|
| Sản phẩm | 48 | 56 |
| Giao dịch bán hàng | 3.408 | 3.552 |
| Biến động tồn kho | 3.888 | 3.888 |
| Tài liệu nội bộ | 26 | 29 |
| Báo cáo doanh thu | 11 | 21 |

Các tổng trên ghi nhận ngay sau nhập; số lượng có thể thay đổi khi người dùng thao tác. Xem `novacommerce-data-manifest.json` để đối chiếu số liệu của riêng bộ NCV1.

Tám nhóm hàng: **Điện tử, Gia dụng, Nội thất, Thiết bị văn phòng, Thiết bị mạng, Văn phòng phẩm, Thiết bị hội nghị, Thiết bị lưu trữ**. Mỗi nhóm thêm sáu SKU có tên, giá VND, ngưỡng cảnh báo và lịch sử bán/nhập. SKU mới theo dạng `NC-EL-001`, `NC-NW-001`... Các sản phẩm AP-* có sẵn được giữ nguyên.

Doanh thu của riêng các dòng bán mới là **25.862.032.000 VND**. Đây là số liệu mẫu từ phép nhân đơn giá cố định × số lượng; không phải lợi nhuận, giá thị trường hoặc số liệu tài chính đã kiểm toán.

## Đối soát và thời gian

- Mỗi sale có reference duy nhất và movement xuất kho cùng reference; số xuất bằng quantity của sale.
- Mỗi SKU mới có nhập đầu kỳ, lịch sử xuất, before/after liên tục và số cuối khớp inventory. Không có tồn âm.
- Tám SKU mới ở mức cảnh báo, gồm bốn SKU hết hàng, để kiểm thử công cụ kiểm tra và quy trình bổ sung.
- Các giao dịch đã nạp nằm từ tháng 01 đến tháng 10/2026. Tại thời điểm nạp là rạng sáng 02/11, chưa đến giờ giao dịch ngày 02/11 trong mô hình mẫu; không tạo doanh số tương lai chỉ để làm đầy biểu đồ tháng mới.
- Báo cáo 11/2026 được ghi rõ **chưa đủ tháng** và có mốc chốt. Mở báo cáo **10/2026** để xem kỳ gần nhất đã đủ tháng. So sánh với tháng trước đầy đủ không phải so sánh cùng số ngày.
- Báo cáo mới tổng hợp bằng SQL từ cả dữ liệu cũ và NCV1. Báo cáo cũ là snapshot và không bị ghi đè.
- Inventory ledger mới chỉ đối soát các SKU NCV1; không bịa thêm chứng từ hoặc lịch sử cho AP-* legacy.

Kiểm tra trực tiếp sau nhập: **0 sale tương lai, 0 sai lệch sale/movement, 0 đứt chuỗi before/after**, 26 file gốc trong DB, audit HMAC hợp lệ.

## Kho tri thức

18 quy trình/chính sách: cơ cấu vận hành; tiếp nhận bán hàng; báo giá/danh mục; đổi trả; nhập kho; bổ sung hàng; kiểm kê; bàn giao hàng; đọc báo cáo; đối soát kỳ; onboarding; nghỉ/bàn giao công việc; bảo mật; quản trị quyền; backup/restore; từ điển dữ liệu; dùng AI có dẫn nguồn; quản lý thiết bị nội bộ.

Thêm tám tài liệu danh mục theo nhóm hàng. Mỗi tài liệu có mã `NC-*`, phiên bản 1.0, đơn vị phụ trách, ngày chốt và nhãn nguồn. File TXT gốc, nội dung và các vector lexical đều lưu trong PostgreSQL. Giá/tồn hiện tại phải đọc business tools; tài liệu danh mục là snapshot.

Trong 26 tài liệu mới: 19 scope `all`, 5 scope `Manager`, 2 scope `Admin`. Manager thấy 24 tài liệu mới và ba tài liệu cũ; Admin thấy toàn bộ. Không bỏ bộ lọc quyền để làm đầy danh sách.

## Dùng trên giao diện

1. **Báo cáo:** mở các báo cáo mang tên Nova Commerce; xem bảng/biểu đồ tám nhóm và tải CSV/PDF. Báo cáo 10/2026 là kỳ đầy đủ gần nhất.
2. **Kho tri thức:** tìm `NC-WH-001` để xem quy trình nhập kho; mở nguồn hoặc tải file gốc. Dùng câu hỏi quy trình khi tìm theo nội dung.
3. **Dữ liệu doanh nghiệp:** tìm `NC-EL-001` để xem màn hình NovaView; tab Giao dịch bán hàng hỗ trợ tìm tên/SKU/mã tham chiếu/danh mục và lọc theo tháng, ví dụ `2026-10`.

## Nạp lại trên môi trường mẫu khác

Sau migration/seed roles và tạo Admin/Manager đang hoạt động:

```powershell
docker compose exec -T backend python -m app.business_data_pack --as-of 2026-11-02
```

Chỉ cho phép khi `SAMPLE_DATA=true` hoặc `DEMO_MODE=true`, và embedding là lexical. Bộ nạp kiểm tra manifest trong system_settings, dùng reference/SKU duy nhất và transaction; chạy lại trả kết quả đã nhập, không nhân đôi hoặc ghi đè sửa đổi của người dùng. Khi có lỗi trước commit, toàn bộ batch rollback. Không tự nạp vào stack chính khi restart; stack test có cấu hình nạp để kiểm thử trên dữ liệu phong phú.

Bản backup trước nhập: `backups/apbwas-20261102-034439.dump`. Các tài khoản, mật khẩu và dữ liệu có sẵn không bị thay đổi bởi bộ nạp.

## Kiểm chứng

89 backend tests đạt trên Linux/PostgreSQL; 15 luồng Playwright kiểm tra thêm ba màn hình với dataset đầy đủ. Test kiểm tra giá × lượng, chuỗi tồn, source scope, file gốc, snapshot không lấy bản ghi tương lai, chống nhập trùng, rollback và lọc giao dịch.
