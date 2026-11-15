# Đăng ký tài khoản và quên mật khẩu

Triển khai ngày 08/11/2026, migration 0013.

## Người dùng

Màn hình đăng nhập có **Tạo tài khoản** và **Quên mật khẩu**. Có thể mở trực tiếp `/register` và `/forgot-password`.

Đăng ký yêu cầu họ tên, email đăng nhập và mật khẩu ít nhất 10 ký tự. Mật khẩu xác nhận được kiểm tra trên giao diện. Backend không nhận vai trò từ người đăng ký; tài khoản lưu trong `users` với vai trò Employee, `active=false`, `registration_pending=true`. Chưa được đăng nhập hoặc truy cập dữ liệu công ty khi chưa duyệt.

Admin mở **Quản trị → Người dùng → Đăng ký chờ duyệt**, xác minh nhân viên rồi duyệt hoặc từ chối. Duyệt kích hoạt tài khoản Employee; từ chối giữ tài khoản bất hoạt. Các tài khoản đã tồn tại không bị ghi đè bởi một yêu cầu đăng ký trùng email.

Quên mật khẩu nhận email đăng nhập và trả thông báo chung, không tiết lộ tài khoản có tồn tại hay không. Nếu tài khoản đang hoạt động và Gmail gửi của công ty đã kết nối, worker gửi một liên kết có hiệu lực 1 giờ. Thư gửi tới email đăng nhập, không dùng email nhận thông báo có thể tự chỉnh trong hồ sơ. Tài khoản chờ duyệt hoặc đã khóa không được tự kích hoạt bằng luồng này.

Mở liên kết `/reset-password#token=...`, nhập mật khẩu mới và xác nhận. Mã chỉ dùng một lần; đổi mật khẩu thu hồi các phiên đăng nhập cũ và vô hiệu hóa mã còn lại. Admin vẫn có thể cấp liên kết khôi phục thủ công khi cần hỗ trợ.

## Dữ liệu và gửi thư

- Mật khẩu lưu bằng Argon2 trong `users.password_hash`, không lưu bản rõ.
- Mã khôi phục lưu SHA-256, mục đích, thời hạn và thời điểm sử dụng trong `account_tokens`.
- `account_emails` là hộp thư chờ gửi trong database: người nhận, người gửi, trạng thái, mã Gmail và kết quả. Liên kết chờ gửi được mã hóa bằng khóa Gmail backend; xóa phần mã hóa sau khi xử lý.
- Job `account_email` dùng kết nối Gmail công ty có quyền gửi, không dùng kết nối cá nhân Employee và không cấp thêm quyền gửi cho người yêu cầu.
- Worker kiểm tra lại tài khoản, quyền người gửi, kết nối và hiệu lực mã trước khi gửi. Mã cũ/đã dùng bị bỏ qua. Khi không xác định kết quả gửi hoặc worker gián đoạn lúc gửi, không tự gửi lại gây trùng.
- `auth_request_attempts` lưu dấu yêu cầu để giới hạn theo email và địa chỉ mạng. Các giá trị dùng HMAC thay bản rõ. Tối đa 3 yêu cầu/email/giờ; đăng ký tối đa 5 yêu cầu/địa chỉ mạng/giờ và khôi phục tối đa 20. Giới hạn này áp dụng từ database, không phụ thuộc Redis.
- Các yêu cầu công khai không trả mã, mật khẩu, khóa hoặc thông tin đăng nhập Gmail. URL khôi phục dựa trên cấu hình server, không dựa vào Host header do người gọi cung cấp.

## Kiểm tra triển khai

249 bài backend đạt, gồm PostgreSQL với schema tách biệt: đăng ký đồng thời tạo đúng một tài khoản, hai lần dùng mã đồng thời chỉ một lần thành công, migration lặp an toàn và giữ dữ liệu cũ. Hai bài Playwright đạt cho đăng ký, quên mật khẩu, đặt mật khẩu mới và Admin duyệt. Gửi email trong các kiểm thử dùng HTTP giả lập; không gửi email thật.

Backup trước nâng cấp: `D:\captone 2\backups\apbwas-20261108-141048.dump`.

Sau nâng cấp đã so sánh fingerprint trước/sau của định danh, mật khẩu, vai trò và trạng thái tài khoản, thông tin Gmail mã hóa và khóa LLM mã hóa: nguyên vẹn. Database có 6 tài khoản cũ, 0 đăng ký chờ duyệt, 0 thư thử khôi phục được tạo vào dữ liệu đang dùng. Gmail gửi khôi phục có kết nối hợp lệ theo cấu hình; audit hợp lệ và web sẵn sàng HTTP 200. Việc Google chấp nhận gửi và người dùng nhận thư chỉ xác nhận khi có yêu cầu khôi phục thật.
