# Email cá nhân và quyền gửi

Áp dụng ngày 08/11/2026, migration 0012.

- Nhân viên cập nhật **Email nhận thông báo** trong Cài đặt tài khoản. Chỉ sửa hồ sơ của mình; không thay email đăng nhập, vai trò hoặc quyền gửi. Địa chỉ nhận thư được kiểm tra và chuẩn hóa khi lưu. Nếu người nhận của một đợt thư đang chờ xác nhận thay đổi, luồng gửi hiện có yêu cầu rà soát lại danh sách.
- Quyền `mail.connect` cho phép kết nối Gmail cá nhân bằng OAuth, xem/kiểm tra/ngắt kết nối của chính tài khoản và gửi một thư thử về chính Gmail đã kết nối. Employee được giới hạn 1 thư thử mỗi giờ, có xác nhận và chống gửi trùng.
- Employee có thể chọn Gmail do mình sở hữu qua OAuth, không bị buộc dùng Gmail gửi chung của công ty. Google phải xác minh địa chỉ tài khoản. Mã OAuth một lần được ràng buộc với người dùng, workspace và thời hạn; thông tin đăng nhập tiếp tục được mã hóa ở backend.
- `mail.connect` không cấp `mail.send`. Các API danh sách nhân viên, tạo/đọc email hàng loạt, duyệt gửi và worker gửi vẫn yêu cầu quyền `mail.send`. Không có tham số để đổi người nhận của thư thử thành người khác. Các tài khoản Admin/Manager đang có quyền gửi giữ nguyên quyền và quy trình xem trước/xác nhận.
- Gmail của người này không được đọc hoặc sử dụng bởi người khác. Không xin quyền đọc hộp thư. Nếu ứng dụng Google đang ở chế độ Testing, Admin cần thêm Gmail nhân viên vào Test users khi Google yêu cầu.

Agent **Trợ lý GPT-6 Luna** đã được gỡ khỏi danh sách theo yêu cầu; giữ lịch sử phiên bản/lượt chạy và kết nối model X-APIKey. Không xóa dữ liệu doanh nghiệp, tài khoản hoặc kết nối Gmail hiện có.

Kiểm tra: 32 bài backend về Gmail, hồ sơ, email hàng loạt và tệp đính kèm đạt; build TypeScript/Vite đạt; Playwright xác minh cập nhật email, mở Gmail cá nhân, ẩn nút soạn hàng loạt và hiển thị trên điện thoại đạt. Toàn bộ kiểm thử gửi dùng HTTP giả lập, không gửi thư thật.

Database chính xác nhận Employee có `mail.connect` và không có `mail.send`, giới hạn thư thử 1/giờ, OAuth đã cấu hình, Agent đã ẩn, model và kết nối Gmail cũ còn nguyên, audit hợp lệ. Backup trước migration: `D:\captone 2\backups\apbwas-20261108-132004.dump`.
