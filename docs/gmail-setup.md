# Kết nối Gmail bằng đăng nhập Google

Đây là kết nối Gmail cho tài khoản APBWAS hiện tại, không thay thế cơ chế đăng nhập APBWAS. Không nhập mật khẩu Gmail. OAuth Client Secret và khóa mã hóa ở backend; token Google được mã hóa trong PostgreSQL và không trả cho trình duyệt.

## Tạo OAuth Client

1. Mở https://console.cloud.google.com/ bằng tài khoản Gmail muốn gửi thư. Tạo hoặc chọn project **APBWAS**.
2. **APIs & Services → Library**: tìm **Gmail API**, chọn **Enable**.
3. **Google Auth Platform → Branding**: điền tên APBWAS, email hỗ trợ và email liên hệ của bạn.
4. **Audience**: chọn External, giữ Testing khi thử nghiệm cá nhân. Thêm địa chỉ Gmail gửi vào Test users.
5. **Data Access**: thêm scope `https://www.googleapis.com/auth/gmail.send`. Ứng dụng cũng dùng `openid` và `email` để xác nhận đúng tài khoản, không xin quyền đọc hay xóa thư.
6. **Clients → Create client → Web application**. Đặt tên APBWAS Local.
7. Authorized JavaScript origins: `http://localhost:4180`.
8. Authorized redirect URIs: **`http://localhost:4180/mail/callback`**, đúng giao thức/host/port/path, không thêm dấu `/` cuối.
9. Lưu Client ID và Client Secret ở máy. Không commit file thông tin xác thực hoặc dán Client Secret vào chat.

Google OAuth web-server documentation: https://developers.google.com/identity/protocols/oauth2/web-server

Gmail send scope and permission classification: https://developers.google.com/workspace/gmail/api/auth/scopes

## Cấu hình trong máy

Mở PowerShell ở thư mục dự án và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/configure_gmail.ps1
```

Script hỏi Client ID và Client Secret bằng ô nhập ẩn, giữ nguyên các cấu hình AI/database hiện có, tái sử dụng khóa mã hóa nếu đã có và khởi động lại backend/worker để nạp cấu hình. Địa chỉ gửi lấy từ GMAIL_SENDER trong `.env`; nếu trống, script sẽ hỏi. Cấu hình được ghi vào `.env` đã bị Git và Docker build context bỏ qua, không in secret ra màn hình.

Các biến: `GMAIL_SENDER`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `MAIL_ENCRYPTION_KEY`. Khóa Fernet cần được sao lưu riêng cùng bí mật môi trường; database dump không đủ để đọc token khi mất khóa. Khi triển khai HTTPS, cập nhật cả FRONTEND_ORIGIN, GMAIL_REDIRECT_URI và redirect URI trong Google Cloud cho khớp.

## Kết nối và kiểm tra

Tải lại http://localhost:4180/mail, đăng nhập APBWAS bằng tài khoản có `mail.send` (Admin/Manager mặc định). Bấm **Kết nối bằng Google**, chọn đúng địa chỉ gửi đã cấu hình rồi cấp quyền. Google chuyển lại `/mail/callback`; ứng dụng đổi code ở backend, xác nhận email và lưu token mã hóa.

**Kiểm tra kết nối** chỉ xác thực danh tính Google và làm mới access token khi cần, không gửi thư. **Gửi thư thử cho chính tôi** mở bước xác nhận rõ địa chỉ nhận; chỉ khi bạn bấm xác nhận mới gọi Gmail API. Thư thử không gửi tới nhân viên. Nếu Google đã nhận thư nhưng mất phản hồi, hệ thống đánh dấu `unknown` và không tự gửi lại cùng idempotency key; kiểm tra Gmail trước khi chủ động thử lại.

**Ngắt kết nối** xóa token trong APBWAS và yêu cầu Google thu hồi quyền. Nếu Google không phản hồi, giao diện nói rõ chưa xác nhận thu hồi bên Google; có thể xóa quyền ứng dụng trong Google Account.

## Xử lý lỗi

- `redirect_uri_mismatch`: đối chiếu địa chỉ redirect chính xác như mục trên.
- Không được phép truy cập khi app đang Testing: thêm đúng địa chỉ gửi vào Test users, kiểm tra project và OAuth Client đang dùng.
- Không có quyền gửi: kết nối lại và cấp `gmail.send`.
- Google thu hồi/hết hạn refresh token: kết nối lại; thời hạn token của ứng dụng Testing có thể chịu giới hạn của Google. Không dùng mật khẩu tài khoản để thay thế.
- Không kết nối được từ máy khác/LAN: localhost dành cho chính máy phát triển; cần HTTPS và OAuth Client redirect phù hợp khi triển khai thực tế.

## Triển khai và giới hạn hiện tại

Migration **0007** thêm `gmail_connections`, `gmail_oauth_states`, `gmail_send_attempts` và quyền `mail.send`, bảo toàn quyền cũ. Kết nối gắn với user/workspace; state có hạn 10 phút, chỉ dùng một lần, gắn user/workspace và có PKCE. Code được đổi bằng POST ở backend; trang callback xóa query khỏi lịch sử và tắt access log/referrer. App xin `openid`, `email`, `gmail.send`, không xin đọc hộp thư. Endpoint cố định của Google, TLS mặc định và timeout được giữ; lỗi không trả token hoặc phản hồi thô của Google.

API: GET `/api/mail/status`; POST `/connect`, `/callback`, `/check`, `/test`; DELETE `/connection`. Test gửi yêu cầu `confirmed=true`, idempotency key và giới hạn 5 lần mỗi giờ; chỉ gửi tới chính địa chỉ đã kết nối. Việc soạn/gửi chiến dịch hàng loạt qua AI và quản lý địa chỉ email nhân viên là bước tiếp theo, chưa được coi là hoàn thành trong phần cấu hình Gmail này.

Kết quả kiểm thử: **121 backend tests đạt** trên môi trường riêng, gồm OAuth với HTTP transport kiểm thử, mã hóa token, state một lần/hết hạn/sai user, chọn sai email, refresh, gửi thử tự xác nhận, chống ghi trùng và timeout không tự gửi lại; **20 Playwright tests đạt**; production build thành công. Có kiểm thử migration nâng/hạ khi chưa có dữ liệu kết nối. Không thực hiện đăng nhập Google thật hoặc gửi email thật trong kiểm thử. Logs `.test-tmp/gmail-backend.log`, `.test-tmp/gmail-e2e.log`.

Trạng thái bàn giao: đã chuẩn bị giao diện/backend, địa chỉ gửi và khóa mã hóa trên máy; **chưa kết nối tài khoản thật**, vì chưa có Google OAuth Client ID/Secret và chưa được người dùng cấp quyền.
