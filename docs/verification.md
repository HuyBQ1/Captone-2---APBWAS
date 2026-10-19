# Báo cáo kiểm tra thực tế — 14/10/2026 (Asia/Saigon)

## Môi trường

Windows, Node/npm, Python 3.12 virtual environment, Chromium Playwright. Harness API thật + worker process riêng + SQLite database chỉ để kiểm thử; Redis không chạy; Demo Agent/lexical embeddings. Không có OpenAI/Gemini key. Docker Desktop được khởi động nhưng Linux/default engine không có named pipe. Log Docker báo lỗi khởi tạo Inference manager listener; không thay đổi cấu hình hệ thống để ép chạy.

## Kết quả đã có

- TypeScript và Vite production build thành công, tạo `dist/`. Chunks libraries được tách; chart chunk vẫn ~600 kB uncompressed và Vite đưa cảnh báo bundle size, không phải lỗi build.
- `npm audit`: 0 vulnerabilities sau các bản vá router/Vite/PostCSS/Tailwind/Playwright. `pip check`: không có dependency bị thiếu hoặc xung đột. Chưa chạy Python security advisory audit.
- Backend: **25 passed, 2 skipped**. Kiểm thử RBAC, allowlist SQL/tool, scope RAG, injection, approval revision, duplicate decision, inventory conflict, approval expiry, cancel, idempotency, quota, redaction/tamper, stream replay, password revocation, Admin CRUD/config, recovery checkpoint và upload/index PDF/DOCX thật. Hai PostgreSQL-only tests skip vì chưa có engine/`PG_TEST_DATABASE_URL`.
- 6/6 Playwright E2E đã qua: revenue/report/CSV; RAG/citation/document; pending approval/Manager apply; Employee denied/injection; tất cả Admin routes + dark mode + mobile drawer/no horizontal viewport overflow/no JS pageerror trong test shell; tạo/sửa/khóa user và bật/tắt tool qua UI.
- UI screenshots trong `docs/screenshots/`; đã xem desktop dashboard, AI Workspace và mobile. Screenshot chờ animation xong, capture reduced-motion; chart cũng hỗ trợ preference này.
- CSV thực là UTF-8 BOM, PDF có header %PDF và font tiếng Việt (Arial local / DejaVu Docker). Kiểm thử export qua API đã qua. Chưa visually render PDF cho nhiều trang lớn vì seed report chỉ có 3 danh mục.
- Docker Compose `config --quiet` đã qua. Compose stack/migration PostgreSQL/HNSW/trigger chưa chạy thật do engine lỗi.

## Đo thời gian local

`scripts/evaluate.py` đo 4 workflow chuẩn qua HTTP/SSE, tách accept latency, stream first byte, useful tool output và completion. Bản đo lưu `evaluation.json`. Lần đo trước khi chốt mã: accept khoảng 1.01–1.02s; SSE first-byte riêng khoảng 0.003s; first useful 2.55–3.57s; workflow hoàn tất 2.55–5.64s. Phê duyệt không thuộc 4 workflow đo này; không tính thời gian con người vào SLA.

3 truy vấn retrieval cố định tìm được tài liệu dự kiến trong Top-5 (3/3), ~0.003–0.005s. Chỉ có vài chunk seed và lexical demo; không suy ra NFR08 10.000 chunks, semantic model accuracy hoặc provider latency. 7/7 bộ injection cố định qua unit test; không suy ra phòng thủ mọi kiểu injection.

## Các lỗi đã sửa trong quá trình xác minh

- Windows folder ACL thiếu Modify: người dùng đã cấp quyền; source nằm đúng workspace.
- JSX form brace và dependency advisories: sửa/build lại.
- Origin qua Vite proxy: thêm exact configured FRONTEND_ORIGIN, giữ kiểm tra same-origin và thêm CSRF check cho login.
- Metadata hội thoại ghi đè result đã lấy: giữ result cùng workflow ID, chỉ chuyển khi workflow mới khác ID.
- React StrictMode initial auth request race: ignore response của effect đã cleanup.
- Timestamp naive của SQLite: UTC TypeDecorator trước bind/after load, UI hiển thị đúng múi giờ Việt Nam.
- E2E mobile selector trùng tên: chọn link trong nav theo title, không chọn link gợi ý khác.

## Còn cần xác minh

- PostgreSQL simultaneous approvals/read-only enforcement (mã test opt-in đã có), vector extension/HNSW và append-only trigger.
- OpenAI/Gemini planner + semantic embeddings bằng key thật.
- NFR performance/load/soak, 10.000 chunks, red-team nhiều kiểu injection.
- Quota/cost ledger embeddings, external audit anchor và primary Redis session cache còn là giới hạn triển khai được ghi trong README.
