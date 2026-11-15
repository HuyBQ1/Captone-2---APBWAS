# Nhiều nhà cung cấp và model LLM

Admin mở **Mô hình AI** trên sidebar (`/models`) hoặc **Quản trị → Mô hình AI**.

Trong chat, ô **Model AI** nằm ngay dưới tên trợ lý ở đầu khung hội thoại. Manager và Employee được chọn các model đã được Admin cấp quyền; không cần quyền quản lý cấu hình để chọn model. Khi chọn một Agent, chat dùng model đã cấu hình trong Agent. Gỡ một Agent khỏi danh sách không xóa kết nối model. Ngày 08/11/2026 đã xác minh catalog Manager/Admin còn `deepseek-v4-flash-vision` (Intern AI) và `gpt-6-luna` (X-APIKey); kiểm thử giao diện xác nhận model được chọn đi đúng vào yêu cầu gửi.

1. Bấm **Thêm nhà cung cấp**. Nhập tên, HTTPS Base URL gốc của API tương thích OpenAI (thường có `/v1`) và API key. Không thêm `/chat/completions` vào Base URL.
2. Nhập Model ID, mỗi dòng một model; hoặc để trống, lưu rồi bấm **Lấy danh sách model**. Backend gọi `GET {base_url}/models`; chọn tối đa 100 model để cho phép sử dụng. Nếu nhà cung cấp không hỗ trợ danh sách, nhập Model ID thủ công.
3. Chọn vai trò được sử dụng, timeout và JSON mode. Kết nối chưa có model thì chưa xuất hiện trong bộ chọn.
4. **Kiểm thử** gửi một câu cố định yêu cầu JSON kế hoạch, không gửi dữ liệu doanh nghiệp và không chạy công cụ. Người dùng xác nhận trước khi kiểm thử vì có thể tốn token. Lấy danh sách model không đồng nghĩa mọi model hỗ trợ schema hoặc tài khoản có quota để chạy.
5. Trong AI Workspace, chọn **Model AI** trước khi gửi yêu cầu thông thường. Khi chọn Agent qua `/`, model theo phiên bản cấu hình Agent; chỉnh tại **AI Agents → Chỉnh sửa → LLM model**, lưu và xuất bản.

Intern AI/model từ môi trường backend tiếp tục hoạt động. Không tự chuyển sang nhà cung cấp khác nếu model mới lỗi. Không tự thêm tài khoản/model chưa được cấu hình; không yêu cầu dán API key vào chat. Hỗ trợ API Chat Completions tương thích OpenAI, không phải API native của mọi nhà cung cấp. Nhà cung cấp cần hỗ trợ phản hồi JSON đúng schema công cụ. Có thể tắt `response_format` nếu endpoint không hỗ trợ JSON mode. Không thay đổi embedding provider hoặc vector hiện có.

## Lưu trữ và quyền

Migration `0009` thêm bảng `llm_providers` và cột nullable `workflows.model_ref`, giữ dữ liệu cũ. API key mã hóa Fernet; API chỉ trả cờ `key_configured`. Key không nằm trong cấu hình/snapshot Agent, workflow, audit hoặc API response. Thông tin kết nối giới hạn workspace; API quản trị cần `settings.manage`. Bộ chọn và lần chạy kiểm tra vai trò, trạng thái bật và danh sách model được duyệt. Tắt kết nối hoặc bỏ model sẽ ngừng các lần chạy tiếp theo sử dụng model đó.

Base URL của một kết nối cố định sau khi tạo, để phiên bản Agent cũ không bị chuyển key/prompt sang endpoint khác khi sửa tên. Muốn đổi endpoint, tạo kết nối mới và chọn lại model. Có thể xoay API key cùng endpoint; để trống trường API key khi sửa để giữ key hiện tại. Mã model nội bộ có dạng `llm:<provider-id>:<model-id>`, còn request gửi nhà cung cấp chỉ dùng Model ID gốc. Quyền và trạng thái được kiểm tra lại khi worker bắt đầu.

Chỉ nhận HTTPS công khai cổng 443, không nhận URL chứa credentials/query/fragment; DNS trỏ vào mạng nội bộ bị từ chối trước khi gửi request. Không theo redirect và không tự đọc proxy môi trường cho kết nối mới. Không hỗ trợ endpoint HTTP localhost/Ollama ở thay đổi này.

## Khóa mã hóa

Dùng `LLM_ENCRYPTION_KEY` (Fernet 32 byte, base64 URL-safe). Nếu để trống, dùng `MAIL_ENCRYPTION_KEY` hiện có. Nếu backend chưa có khóa, chạy `powershell -ExecutionPolicy Bypass -File scripts/configure_llm.ps1` trong thư mục dự án. Script giữ key hiện có hoặc tái sử dụng key Gmail trước khi tạo key mới, lưu vào `.env` đã bỏ qua bởi Git, không in key.

Sao lưu khóa mã hóa riêng với database. Không thay key mã hóa tùy tiện: bản ghi đã mã hóa sẽ không đọc được. Không có thao tác tạo key mã hóa tự động mỗi lần khởi động.

## Xác minh 2026-11-05

Build production thành công. 150 kiểm thử backend qua; kiểm tra bổ sung 61 bài LLM/Agent/provider/PostgreSQL và 6 bài trình duyệt hồi quy Agent, Gmail, bản nháp email và quản lý model đều qua. Có kiểm tra hiển thị điện thoại và quyền Employee. Kiểm thử dùng khóa giả và HTTP mock; không gọi dịch vụ LLM mới hoặc gửi email thật.

Đã triển khai migration 0009: giữ 6 users, 3552 sales, 56 products, 4 agents và 1 kết nối Gmail. Khóa mã hóa có sẵn qua MAIL_ENCRYPTION_KEY; chưa tạo nhà cung cấp mới khi người dùng chưa nhập thông tin. Model môi trường deepseek-v4-flash-vision vẫn có trong bộ chọn. Backup trước nâng cấp: backups/apbwas-20261105-022327.dump (bỏ qua bởi Git).

Timeout từng kết nối vẫn chịu giới hạn timeout workflow và AI_TIMEOUT_SECONDS của hệ thống.

Ngày 08/11/2026: bỏ mức chờ cố định 25 giây ở bước tổng hợp câu trả lời. Workspace hiện đặt `AI_TIMEOUT_SECONDS=120`, kết nối Luna chờ tối đa 120 giây và workflow có thời hạn 300 giây. Bước tổng hợp dùng thời gian còn lại trong workflow, chịu giới hạn cấu hình AI/nhà cung cấp. Không chờ vô hạn, không tự phát lại yêu cầu bị read timeout. Hạn mức token, số yêu cầu/phút và các quyền không thay đổi. 38 bài kiểm thử provider/tổng hợp đạt, gồm kiểm tra mức chờ dài hơn 25 giây và không vượt deadline ngắn của workflow.

