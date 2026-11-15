# Nova Commerce — tài khoản, dữ liệu và vận hành

Cập nhật 02/11/2026. Triển khai hiện tại là một doanh nghiệp trên Docker local, truy cập `http://localhost:4180`.

Đã bổ sung [bộ dữ liệu NCV1](novacommerce-business-data.md) cho Báo cáo, Kho tri thức và Dữ liệu doanh nghiệp: 56 sản phẩm, 3.552 giao dịch, 29 tài liệu phân quyền và 21 báo cáo sau nhập. Mốc kiểm thử mới nhất là 89 backend/15 Playwright; số 86/14 ở phần lịch sử nâng cấp bên dưới là mốc trước khi bổ sung dữ liệu.

## Đăng nhập lần đầu

Ba tài khoản nội bộ đã được tạo trong PostgreSQL:

| Vai trò | Tên đăng nhập |
|---|---|
| Admin | admin@novacommerce.example |
| Manager | manager@novacommerce.example |
| Employee | employee@novacommerce.example |

Mật khẩu tạm riêng nằm trong **tệp riêng `backups/novacommerce-accounts.json` trên máy**, không nằm trong source/Git. Thư mục backups bị loại khỏi Docker build context. `.example` là tên đăng nhập nội bộ, không phải hộp thư email đang hoạt động.

Mỗi người đăng nhập bằng thông tin được cấp, đổi mật khẩu ở màn hình bắt buộc, rồi đăng nhập lại. Phiên dùng mật khẩu tạm chỉ được truy cập các API tài khoản; không mở dữ liệu nghiệp vụ. Ba tài khoản mẫu `@apbwas.demo` đã ngừng đăng nhập trong database chính; hội thoại, workflow, báo cáo và audit của chúng vẫn được giữ. Stack kiểm thử tại cổng 4181 dùng database riêng và tài khoản mẫu riêng.

Admin có quyền quản trị doanh nghiệp/tài khoản, danh mục và bán hàng. Manager mặc định xem doanh thu, quản lý tri thức, đề xuất/duyệt tồn kho. Employee xem hàng hóa/tri thức được phép và workflow của mình. Admin có thể cấp thêm `business.manage` trong ma trận quyền; ghi nhận bán hàng còn cần `sales.read`.

## Nhân viên và bảo mật tài khoản

- **Mời nhân viên:** Quản trị → Người dùng → Mời nhân viên. Tài khoản lưu DB; người nhận tự đặt mật khẩu bằng liên kết một lần, hiệu lực 24 giờ.
- **Tạo tài khoản với mật khẩu ban đầu:** nhân viên phải đổi mật khẩu trước khi làm việc.
- **Quên mật khẩu:** quản trị viên mở Chỉnh sửa → Cấp liên kết khôi phục. Liên kết có hiệu lực một giờ; cấp lại sẽ vô hiệu liên kết cũ. Admin chuyển riêng liên kết cho đúng người nhận. Chưa có SMTP; không tuyên bố đã gửi email.
- **Khóa/đổi vai trò:** thu hồi các phiên hiện có. Khóa tài khoản còn vô hiệu các liên kết chưa dùng. Không cho tự khóa/hạ quyền Admin đang thao tác.
- **Hồ sơ:** lưu tên, điện thoại, phòng ban và chức danh trong DB. Vai trò do Admin quản lý. Màn hình tài khoản liệt kê thiết bị/IP/thời điểm/hạn phiên và cho kết thúc từng phiên của chính mình.
- Mật khẩu băm Argon2; DB chỉ giữ hash của session/reset token. Liên kết dùng URL fragment để không gửi token vào access log của web server. Đổi/khôi phục mật khẩu thu hồi tất cả phiên.

Không mở đăng ký tự do cấp vai trò doanh nghiệp. Account lifecycle được kiểm soát bởi Admin.

## Hàng hóa và bán hàng

Ở Dữ liệu doanh nghiệp, Admin thêm/sửa sản phẩm, giá, ngưỡng cảnh báo và ngừng kinh doanh. Sản phẩm mới có tồn kho 0. Mã SKU duy nhất; sửa sản phẩm kiểm tra version để tránh ghi đè thay đổi của người khác. Không xóa sản phẩm đã có lịch sử.

Nhập/điều chỉnh tồn kho dùng đề xuất và phê duyệt hiện có. Agent không được tự áp dụng tồn kho. Sau duyệt, tồn kho và lịch sử biến động được ghi cùng transaction. Ledger mới ghi các thay đổi kể từ migration 0003; thay đổi cũ vẫn nằm trong approval/audit lịch sử.

**Ghi nhận bán hàng** là thao tác con người xác nhận rõ ràng: chọn sản phẩm, số lượng, xem thành tiền, xác nhận trừ tồn. Backend kiểm tra quyền, trạng thái/phiên bản sản phẩm và tồn kho; tính tiền từ giá trong DB. Sale, giảm tồn, tăng version, movement và audit commit cùng nhau. Mã giao dịch chống ghi trùng khi gửi lại. Hai giao dịch đồng thời không được bán vượt tồn. Lịch sử tồn kho hiển thị số trước/sau và biến động.

Đây là ghi nhận giao dịch bán hàng đơn sản phẩm; chưa phải bộ ERP kế toán/thuế, hóa đơn điện tử hoặc xử lý giao vận.

## Dữ liệu được lưu ở đâu

| Dữ liệu bền vững | Nơi lưu |
|---|---|
| Tài khoản, hồ sơ, vai trò/quyền | users, roles, permissions |
| Phiên đăng nhập, liên kết kích hoạt/khôi phục | auth_sessions, account_tokens — chỉ hash token |
| Tùy chọn sáng/tối, sidebar | users.preferences; không phụ thuộc localStorage |
| Tên/liên hệ/địa chỉ doanh nghiệp, các giới hạn | system_settings |
| Hội thoại, tin nhắn, ngữ cảnh | conversations, messages |
| Kế hoạch/kết quả/trạng thái/công cụ/sự kiện | workflows, workflow_steps, tool_executions, workflow_events |
| Sản phẩm, doanh số, tồn kho và biến động | products, sales, inventory, inventory_movements |
| Phê duyệt và các quyết định | approval_requests, approval_decisions |
| Báo cáo và số liệu để xuất CSV/PDF | reports |
| Metadata, nội dung trích xuất, vector và file gốc | documents, document_chunks, document_files.content (BYTEA) |
| Thông báo và trạng thái đã đọc | notifications, riêng từng người dùng |
| Audit, usage và job bền vững | audit_logs, usage_records, jobs |

PostgreSQL là nguồn dữ liệu bền vững. Redis phục vụ cache/rate limit và không thay thế database. File gốc mới lưu trực tiếp trong DB, giới hạn 10 MB; init chép file upload cũ vào DB nếu có, giữ nguyên volume cũ. Đợt chuyển đổi ghi nhận `missing_originals=0`. Khởi động lại dịch vụ không mất các dữ liệu này.

**Ngoại lệ cần thiết:** API key và audit signing key là bí mật môi trường backend, không đưa vào DB/frontend. Mật khẩu tạm để bàn giao nằm trong tệp riêng; DB giữ hash, không giữ plaintext. Trạng thái UI chưa lưu như ô nhập đang gõ chưa gửi không phải bản ghi nghiệp vụ.

Schema hiện tại: **26 bảng, 178 cột, 27 khóa ngoại**. Xem [data dictionary và sơ đồ mới](database-design/enterprise/README.md). DOCX database design version 1.1 cũ mô tả schema trước migration 0003, được giữ như bản lịch sử.

## Sao lưu và khôi phục

Chạy `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup.ps1`. Script tạo PostgreSQL custom archive trong `backups/`, không truyền dữ liệu binary qua text pipeline và xác thực archive bằng pg_restore. Backup DB bao gồm cả file gốc đã lưu ở document_files. Giữ `.env`/audit signing key riêng trong kho bí mật của người vận hành; chúng không có trong database dump.

Trước nâng cấp đã tạo `backups/apbwas-20261102-024802.dump`. Đã restore vào **database thử nghiệm khác**, chạy migration 0003 thành công, giữ 3 user cũ, 8 sản phẩm, 28 workflow và 146 audit record của snapshot. Không restore đè database chính.

Sau nâng cấp và cấp tài khoản đã tạo thêm `backups/apbwas-20261102-030507.dump`. Restore vào database thử nghiệm khác xác nhận **26 bảng, 6 user (3 hoạt động), 28 workflow, schema 0003**. Chuỗi HMAC audit của database chính vẫn hợp lệ.

Khi khôi phục thực tế, tạo database mới, dùng `pg_restore --no-owner --no-privileges --exit-on-error`, kiểm tra dữ liệu và HMAC với đúng signing key, rồi mới chuyển cấu hình ứng dụng. Không dùng `down -v` hoặc xóa volume để cập nhật phiên bản.

## Kiểm chứng và phần cấu hình còn lại

- 86 backend tests đạt trên Linux/PostgreSQL, gồm nâng schema cũ không mất dữ liệu, concurrent sale, one-use token, scope và migration. Sau khi bổ sung màn hình ledger, 10 enterprise API tests và toàn bộ 14 Playwright tests đã chạy lại đạt.
- Production build đạt. Khởi động lại PostgreSQL/Redis/backend/worker/frontend của stack thử nghiệm vẫn giữ session DB, preferences, sản phẩm/tồn kho, metadata/file gốc/chunks tài liệu; xem `enterprise-persistence.json`.
- Ba tài khoản chính mới đã đăng nhập thử, đúng vai trò và bị bắt buộc đổi mật khẩu; tài khoản Admin mẫu bị từ chối, login không còn hiện các nút mẫu.
- Chưa push các thay đổi lên GitHub. Không gọi AI bên ngoài trong đợt nâng cấp này.

Email tự động cần SMTP/tên miền thật; HTTPS và sao lưu ngoài máy cần môi trường triển khai thực tế. Chưa có multi-tenant, SSO/MFA, OCR hay benchmark chất lượng semantic mới. Bộ hàng hóa cũ vẫn được đánh dấu dữ liệu mẫu; không tự đổi nhãn thành dữ liệu doanh nghiệp thật.
