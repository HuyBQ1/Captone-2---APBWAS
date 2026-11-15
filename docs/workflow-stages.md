# Sơ đồ giai đoạn workflow

Cập nhật 08/11/2026. API chi tiết workflow trả thêm `execution_graph`, được xây dựng bằng phép đọc từ kế hoạch, biên nhận công cụ, kết quả AI và trạng thái đợt email.

Một công cụ có thể gồm nhiều giai đoạn nội bộ. Sơ đồ phân biệt số công cụ thật và số giai đoạn hiển thị; không đổi kế hoạch LLM, không ghi thêm lần gọi công cụ, không chạy lại workflow và không phát sinh gửi email. Những giai đoạn của lượt cũ được đối chiếu từ kết quả đã lưu, không có thời gian thực thi riêng được bịa thêm. Công cụ chưa hoàn tất chỉ hiện trạng thái công cụ vì chưa có bằng chứng để xác nhận từng giai đoạn nội bộ.

Ví dụ soạn email kèm báo cáo có thể gồm chín giai đoạn: AI lập kế hoạch; kiểm tra quyền/kỳ; tìm tệp trong hội thoại; kiểm tra tệp; kiểm tra người nhận; lưu bản nháp; AI tổng hợp; người dùng xác nhận; gửi Gmail/lưu kết quả. Không thể hiện tìm tệp cũ là tạo tệp mới. Với công cụ tạo Word/Excel, truy vấn dữ liệu và tìm tài liệu, hiển thị các giai đoạn tương ứng.

Xác nhận và gửi thư là phần tiếp nối riêng sau khi Agent tạo bản nháp. Trạng thái lấy trực tiếp từ `mail_campaigns` và `mail_deliveries`, không suy từ trạng thái workflow đã hoàn tất. Draft hiện chờ người dùng xác nhận và chưa gửi. Chỉ đánh dấu gửi thành công khi tất cả người nhận có trạng thái sent; lỗi hoặc kết quả chưa xác định không được trình bày như đã gửi thành công. Sơ đồ không trả nội dung thư hoặc địa chỉ người nhận. Liên kết mở email chỉ hiện cho chủ đợt thư còn quyền gửi.

Máy tính hiển thị các nút và mũi tên theo nhiều hàng, giới hạn độ phóng ban đầu để chữ không bị phóng quá lớn. Điện thoại hiển thị danh sách giai đoạn. Có phần mở rộng mô tả cho mỗi giai đoạn.

Kiểm thử: 18 bài backend về sơ đồ, email và tệp đính kèm đạt. Playwright xác nhận một công cụ hiển thị chín giai đoạn/tám liên kết, trạng thái chờ xác nhận và giao diện điện thoại; không có request ghi nào phát sinh khi xem sơ đồ. Build TypeScript/Vite đạt.
