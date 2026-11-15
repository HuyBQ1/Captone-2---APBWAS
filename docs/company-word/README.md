# Thư viện Word Nova Commerce phiên bản 1.1

Ngày soạn: 03/11/2026. Bộ tài liệu gồm **18 quy trình và hướng dẫn hai trang**, cùng **8 danh mục hàng hóa một trang**, tổng cộng **44 trang**.

Mỗi văn bản có tên rõ ràng, mã tài liệu, phiên bản, đơn vị chủ trì, phân loại, trách nhiệm và phần rà soát/phê duyệt. Quy trình có sáu bước, đầu mối thực hiện, đầu ra, ngoại lệ và hồ sơ cần lưu. Bảng danh mục đối chiếu SKU, giá, số tồn và ngưỡng tại thời điểm lập. Các ô ký để trống; văn bản đang chờ rà soát/phê duyệt, không có chữ ký hoặc quyết định ban hành giả.

Đã kiểm tra trực quan đủ 44 trang sau khi xuất bằng Microsoft Word và raster hóa bằng Poppler. Không có lỗi tràn bảng, thiếu dấu tiếng Việt hoặc ngắt trang ngoài dự kiến. Tiện ích render_docx.py không chạy được vì môi trường Windows không có LibreOffice; quy trình kiểm tra sử dụng Word gốc và Poppler của runtime đã cấu hình.

Các bản DOCX được lưu trực tiếp trong PostgreSQL và đã lập chỉ mục, gồm cả nội dung bảng. Phân quyền giữ nguyên: 19 tài liệu nội bộ chung, 5 tài liệu quản lý, 2 tài liệu quản trị. Danh sách mặc định hiển thị tài liệu hiện hành; bản TXT cũ chuyển trạng thái archived và giữ nguyên file, nội dung cùng chunk để không làm hỏng nguồn dẫn lịch sử.

`manifest.json` ghi checksum của từng file đã kiểm tra; `publication.json` ghi ánh xạ bản cũ/bản Word mới. Tệp ZIP ở thư mục docs chứa đúng 26 file Word, chia theo phạm vi quyền. Không kèm PDF hoặc ảnh QA.

Backend đã thêm kiểm tra đọc nội dung trong ô bảng Word, ẩn bản lưu trữ khỏi danh sách mặc định và ngăn xóa/re-index bản lưu trữ. Bản hiện tại đã qua 83 tests trên Windows; 8 PostgreSQL-only tests được skip ở lần chạy này. Việc lưu 26 bản Word, phân quyền, audit và tìm kiếm nội dung bảng đã kiểm chứng trực tiếp trên PostgreSQL chính.
