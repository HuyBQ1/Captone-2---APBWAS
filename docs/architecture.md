# Kiến trúc và schema

React Router → same-origin HTTP API → FastAPI → SQLAlchemy → PostgreSQL. SSE endpoint replay `workflow_events.sequence`, `Last-Event-ID` và cursor query. TanStack Query phục hồi dữ liệu khi SSE gián đoạn. Browser không gọi provider trực tiếp.

HTTP enqueue transaction: authenticate → quota → conversation/message → workflow → durable job → queued event → audit. Worker claim `FOR UPDATE SKIP LOCKED` và lease 10 phút. Plan validate trước execution, lại kiểm tra permission/toggle trong mỗi tool. Tool output, execution record, checkpoint, event và audit cùng transaction. Report unique workflow_id tránh report lặp khi phục hồi. Worker không được tự chạy `apply_approved_inventory_adjustment`.

Approval API khóa approval rồi workflow; cancel dùng cùng thứ tự khóa. Decision phải khớp revision đang pending và chưa hết hạn. Modify tạo revision, clear approved revision. Apply dùng `UPDATE inventory WHERE version=:expected`, quantity constraint và transaction gồm decision/audit/output/message. Test PostgreSQL xác nhận hai người duyệt đồng thời chỉ áp dụng một lần. Writer audit/event cùng lấy advisory lock audit trước event để tránh đảo thứ tự khóa.

Tài liệu gốc lưu BYTEA trong document_files, giới hạn 10 MB. Upload xác thực PDF magic header, DOCX ZIP có cấu trúc Word/30 MB decompressed bound và TXT UTF-8. Đường dẫn uploads chỉ giữ cho dữ liệu legacy; init chép file cũ vào DB. Worker parse → chunks dài 1000 ký tự, stride 850 → embedding384 → vector model_id → indexed. Query lọc scope/model trong SQL, cosine limit5, statement timeout 2500 ms. HNSW dùng iterative scan; nếu thiếu ứng viên hoặc shortlist có điểm dưới ngưỡng liên quan, xếp hạng exact trong phạm vi được phép để khắc phục mất recall sau lọc. Trả extractive evidence, không thực thi chỉ dẫn bên trong chunk. Delete xóa chunks, job, doc và file; retrieval không cache. Workflow, conversation, idempotent replay và audit đều kiểm tra lại quyền xem nguồn hiện tại. PDF scan không có OCR.

SQLAlchemy schema có users/roles/permissions/auth_sessions/account_tokens/notifications/document_files/inventory_movements/conversations/messages/workflows/workflow_steps/tool_executions/workflow_events/products/sales/inventory/documents/document_chunks/approval_requests/approval_decisions/reports/audit_logs/usage_records/system_settings/jobs. FK/index/unique constraints cho identity, email, SKU, idempotency, workflow-position, one approval/report/job per resource. Inventory version + quantity >=0. Timestamp lưu UTC, UI dùng Asia/Ho_Chi_Minh; financial period cutoff theo Việt Nam. Alembic 0001 tạo vector extension/HNSW/append-only trigger.

Session token random chỉ gửi HttpOnly cookie, DB giữ SHA256 token và TTL. Password Argon2. Redis dùng memory cache/rate limits; database session là nguồn bền vững và tài khoản/quyền được đọc lại. Redis mất khả dụng: local Demo fallback DB; Connected login fail-closed 503. Redis chưa làm primary session cache; không khai nhận mục này đã hoàn chỉnh.

Audit HMAC(timestamp, previous_hash, actor, event, resource, correlation, redacted_payload). Postgres advisory lock bảo vệ ordering nhiều writer, trigger cấm UPDATE/DELETE ở ứng dụng. Không có UI sửa/xóa audit. Key ở môi trường backend. Operator sở hữu DB superuser và key vẫn có thể rewrite chain; cần external signed anchor/WORM cho mức bảo vệ cao hơn.

Provider adapter chỉ tạo structured plan; dữ liệu doanh thu không gửi cho LLM để tự tính. Connected embeddings dùng model dimension384. API errors không tự fallback demo. Không Text-to-SQL, arbitrary URL/code, ERP tích hợp hoặc tenant isolation. PostgreSQL ứng dụng có write quyền metadata; business reads dùng READ ONLY transaction + statement_timeout 2500 ms. AGENT_DATABASE_URL cho phép dùng credential read role riêng nếu được provision.


## Bản doanh nghiệp (migration 0003)

Xem [hướng dẫn Nova Commerce](enterprise-guide.md) và [schema 26 bảng](database-design/enterprise/README.md). Hồ sơ, preferences, thông tin công ty, phiên đăng nhập, link token hash và thông báo lưu DB. Sale/inventory/movement/audit commit atomically; product_version và inventory_version tách riêng. Đã kiểm tra khôi phục backup và restart persistence.
