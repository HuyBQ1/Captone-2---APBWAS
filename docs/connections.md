# Trung tâm kết nối

Mở `/connections` hoặc mục **Kết nối** (icon phích cắm) trên sidebar.

- **Gmail**: trạng thái OAuth thật của tài khoản APBWAS hiện tại, quản lý kết nối tại `/mail`, soạn email tại `/mail/employees`. Không tự gửi thư khi mở thẻ.
- **Microsoft Word**: tải `.docx` vào API kho tri thức hiện có; bản gốc lưu database, worker trích xuất và lập chỉ mục. Không cần đăng nhập Microsoft.
- **Microsoft Excel**: `/connections/excel` sử dụng trung tâm tài chính hiện có. Xuất `.xlsx` với công thức; Admin có quyền `business.manage` nhập lại file theo mẫu APBWAS qua bước xem trước và xác nhận. Không phải trình mở bảng tính bất kỳ.
- **PDF / TXT**: tải tài liệu PDF có văn bản hoặc TXT UTF-8, tối đa 10 MB, đọc và tìm kiếm trong kho tri thức. Không bổ sung OCR ở thay đổi này.
- **CSV**: mở báo cáo hiện có để xuất CSV.

Các thẻ Word/Excel/PDF/TXT hiển thị **Sẵn sàng qua tệp**, không hiển thị “Đã kết nối” tài khoản đám mây. Hiện chưa có OAuth Microsoft 365, OneDrive hoặc Google Drive. Không tạo hoặc lưu token giả. Danh sách thẻ không mở rộng quyền người dùng; các thao tác vẫn dùng RBAC API hiện có. Không có migration database cho thay đổi này.

## Xác minh 2026-11-05

Build production thành công. 6 kiểm thử trình duyệt qua: tải Word và worker lập chỉ mục, xuất Excel, xem trước/nhập lại Excel, Gmail, bản nháp email, quyền Employee và bố cục điện thoại. Đã kiểm tra trực tiếp trang /connections trên ứng dụng chính; kết nối Gmail hiện tại được giữ nguyên. Chỉ triển khai frontend, không có migration hoặc thay đổi dữ liệu chính.

