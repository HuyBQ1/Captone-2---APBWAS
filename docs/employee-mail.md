# Email cho nhân viên

1. Admin mở **Gmail → Soạn email cho nhân viên**. Nhập địa chỉ nhận thư thật cho từng nhân viên, bấm **Lưu**. Email đăng nhập không thay đổi. Manager chỉ sửa địa chỉ của chính mình; Admin sửa danh bạ workspace.
2. Người gửi (Admin/Manager) kết nối Gmail bằng Google trong tài khoản APBWAS của mình.
3. Chọn toàn bộ nhân viên hoặc chọn từng người. Nhập tiêu đề, nội dung, bấm **Lưu và xem trước**. Email mẫu, địa chỉ trùng được liệt kê là bỏ qua.
4. Kiểm tra người nhận/nội dung, bấm **Xem xác nhận gửi → Xác nhận gửi ngay**. Worker gửi từng thư riêng; người nhận không thấy email của người khác.
5. Theo dõi kết quả từng người tại bản nháp hoặc lịch sử gửi. “Google đã nhận” chỉ xác nhận API chấp nhận gửi; không đảm bảo thư vào inbox. Dừng đợt gửi chỉ dừng thư chưa gửi.

Có thể yêu cầu AI Workspace: “Soạn email cho toàn bộ nhân viên nhắc họp lúc 9 giờ sáng mai, tiêu đề Thông báo họp”. AI chỉ tạo bản nháp, trả liên kết để người dùng kiểm tra và xác nhận. Trong Demo Mode cung cấp `Tiêu đề: ...` và `Nội dung: ...` trên hai dòng.

Lệnh “soạn thư doanh thu tháng này và gửi cho nhân viên” dùng mẫu nghiệp vụ đọc SQL trực tiếp, tạo bản nháp cho toàn bộ nhân viên, được Agent LLM chọn công cụ trong Connected Mode; luồng cục bộ chỉ dùng cho Demo Mode. Hỗ trợ tháng chỉ định như `07/2026`, `2026-07`, hoặc “tháng trước”. Không có giao dịch thì thư ghi rõ database chưa có dữ liệu kỳ này; không tự lấy tháng khác thay thế. Thư ghi rõ dữ liệu mẫu khi hệ thống bật chế độ dữ liệu mẫu. Cần đồng thời `mail.send` và `sales.read`; Agent tùy chỉnh phải bật công cụ `prepare_revenue_email` và cả hai quyền. Không tự thêm công cụ vào phiên bản Agent đã xuất bản.

Trong chat có thẻ email riêng, hiển thị trạng thái thực tế và nút **Mở bản nháp email**. Thẻ vẫn xuất hiện khi mở lại hội thoại hoặc khi một yêu cầu tiếp theo bị lỗi. Có thể gõ “Xem người nhận và xác nhận gửi”, “Mở bản nháp email”, “Xem lại bản nháp” để đọc email gần nhất trong cùng hội thoại, trong Connected Mode, Agent LLM chọn công cụ đọc lại nháp và không tạo đợt gửi mới. Hội thoại mới không tự lấy email ở hội thoại khác. Lệnh này không thay cho việc xác nhận gửi ở trang email.

Kết nối AI chỉ thử lại một lần khi không thiết lập được kết nối (`ConnectError`); không tự phát lại yêu cầu bị read timeout vì có thể nhà cung cấp đã nhận yêu cầu. Không đổi endpoint/model/key hoặc chuyển sang mô phỏng khi lỗi mạng.

Không có nhân viên nhận thư thật mặc định. Không tự gán email Gmail của người gửi cho nhân viên. Email `.example`, `.demo`, `.test`, `.invalid` và example.com/org/net bị từ chối.

Mỗi đợt tối đa 100 người, giới hạn mặc định 100 thư được duyệt trong 24 giờ/người gửi (`MAIL_BULK_DAILY_LIMIT`, 1–500). Đây là giới hạn ứng dụng; Google có thể từ chối vì giới hạn tài khoản của họ. Giới hạn tính cả thư chưa gửi trong các đợt đã duyệt để tránh gửi vượt mức qua nhiều đợt.

Database lưu `users.delivery_email`, `mail_campaigns`, `mail_deliveries`, hàng đợi `jobs` và audit. Token Gmail vẫn được mã hóa trong backend. API quản lý đợt gửi giới hạn chủ sở hữu và workspace. Migration `0008` bổ sung bảng/cột; không sửa dữ liệu đăng nhập hay kết nối Gmail hiện có.

Không tự động gửi lại khi HTTP timeout, mất phản hồi hoặc worker bị ngắt giữa lúc gửi: trạng thái **Chưa xác định**. Phải kiểm tra Thư đã gửi trước khi tạo đợt mới để tránh thư trùng. Chưa hỗ trợ tệp đính kèm, HTML, lịch gửi hoặc tự động gửi theo cron.

## Xác minh 2026-11-03

Build production thành công. 130 backend tests qua, kiểm tra bổ sung 27 tests Gmail/bulk mail/PostgreSQL sau khi thống nhất thứ tự khóa. 20 kiểm thử hồi quy trình duyệt qua; kiểm thử mới về thêm liên hệ, sửa thư, xem trước, chặn gửi khi chưa kết nối và hủy bản nháp cũng qua. Có kiểm tra hiển thị di động. Không gọi Google thật trong kiểm thử.

Triển khai migration 0008 tại localhost:4180: giữ 6 users, 3552 sales, 56 products và 1 kết nối Gmail; 0 chiến dịch, 0 lượt gửi. Backup trước nâng cấp: backups/apbwas-20261103-140032.dump (được bỏ qua bởi Git).

