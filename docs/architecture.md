# Kiến trúc và schema

React Router → same-origin HTTP API → FastAPI → SQLAlchemy → PostgreSQL. SSE endpoint replay `workflow_events.sequence`, `Last-Event-ID` và cursor query. TanStack Query phục hồi dữ liệu khi SSE gián đoạn. Browser không gọi provider trực tiếp.

HTTP enqueue transaction: authenticate → quota → conversation/message → workflow → durable job → queued event → audit. Worker claim `FOR UPDATE SKIP LOCKED` và lease 10 phút. Plan validate trước execution, lại kiểm tra permission/toggle trong mỗi tool. Tool output, execution record, checkpoint, event và audit cùng transaction. Report unique workflow_id tránh report lặp khi phục hồi. Worker không được tự chạy `apply_approved_inventory_adjustment`.

Approval API khóa approval rồi workflow; cancel dùng cùng thứ tự khóa. Decision phải khớp revision đang pending và chưa hết hạn. Modify tạo revision, clear approved revision. Apply dùng `UPDATE inventory WHERE version=:expected`, quantity constraint và transaction gồm decision/audit/output. Duplicate/concurrent quyết định phải thấy trạng thái không pending sau lock; mục tiêu này cần integration PostgreSQL thực tế.

Tài liệu lưu UUID filename, giới hạn 10 MB, PDF magic header, DOCX ZIP/30 MB decompressed bound và TXT UTF-8. Worker parse → chunks dài 1000 ký tự, stride 850 → embedding384 → vector model_id → indexed. Query join documents trước cosine limit5, scope/model filter. Trả extractive evidence, không thực thi chỉ dẫn bên trong chunk. Delete xóa chunks, job, doc và file; retrieval không cache nên không có vector stale cache. PDF scan không có OCR.

SQLAlchemy schema có users/roles/permissions/auth_sessions/conversations/messages/workflows/workflow_steps/tool_executions/workflow_events/products/sales/inventory/documents/document_chunks/approval_requests/approval_decisions/reports/audit_logs/usage_records/system_settings/jobs. FK/index/unique constraints cho identity, email, SKU, idempotency, workflow-position, one approval/report/job per resource. Inventory version + quantity >=0. Timestamp lưu UTC, UI dùng Asia/Ho_Chi_Minh; financial period cutoff theo Việt Nam. Alembic 0001 tạo vector extension/HNSW/append-only trigger.

Session token random chỉ gửi HttpOnly cookie, DB giữ SHA256 token và TTL. Password Argon2. Redis dùng memory cache/rate limits; database session là nguồn bền vững và tài khoản/quyền được đọc lại. Redis mất khả dụng: local Demo fallback DB; Connected login fail-closed 503. Redis chưa làm primary session cache; không khai nhận mục này đã hoàn chỉnh.

Audit HMAC(timestamp, previous_hash, actor, event, resource, correlation, redacted_payload). Postgres advisory lock bảo vệ ordering nhiều writer, trigger cấm UPDATE/DELETE ở ứng dụng. Không có UI sửa/xóa audit. Key ở môi trường backend. Operator sở hữu DB superuser và key vẫn có thể rewrite chain; cần external signed anchor/WORM cho mức bảo vệ cao hơn.

Provider adapter chỉ tạo structured plan; dữ liệu doanh thu không gửi cho LLM để tự tính. Connected embeddings dùng model dimension384. API errors không tự fallback demo. Không Text-to-SQL, arbitrary URL/code, ERP tích hợp hoặc tenant isolation. PostgreSQL ứng dụng có write quyền metadata; business reads dùng READ ONLY transaction + statement_timeout 2500 ms. AGENT_DATABASE_URL cho phép dùng credential read role riêng nếu được provision.
