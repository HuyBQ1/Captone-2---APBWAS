# Rà soát và kiểm chứng dự án — 02/11/2026

Mốc rà soát này có trước yêu cầu bổ sung bản doanh nghiệp. Trạng thái hiện tại, tài khoản và kết quả 86/14 nằm trong [hướng dẫn Nova Commerce](enterprise-guide.md); không dùng thông tin tài khoản demo ở mốc cũ để đăng nhập bản đang chạy.

## Môi trường và phạm vi

Windows/PowerShell, Python 3.12, Playwright Chromium; Docker Linux engine 29.5.2, PostgreSQL 16/pgvector 0.8.7 và Redis 7.4. Stack `apbwas-review` tại cổng 4181 dùng `compose.test.yaml`, database/volume riêng, Demo planner và lexical embeddings. Không đọc `.env` chính và không gọi nhà cung cấp AI bên ngoài.

Ứng dụng chính tại cổng 4180 đã build/cập nhật, giữ nguyên volume và cấu hình Intern AI. Smoke test xác nhận frontend, readiness database/Redis, đăng nhập Manager và đọc SKU AP-001 thành công. Không chạy workflow AI mới trên dữ liệu chính. Kết quả gọi Intern AI trước đây ghi riêng trong `intern-ai-setup.md` và `intern-ai-verification.json`.

## Kết quả cuối

| Kiểm tra | Kết quả và phạm vi |
|---|---|
| TypeScript/Vite production | Build thành công; chart chunk ~600 kB còn cảnh báo kích thước |
| Backend Linux/PostgreSQL | **73 passed**, không skip; gồm 5 kiểm thử PostgreSQL riêng |
| Backend Windows/SQLite | **68 passed, 5 skipped**; 5 test PG đã chạy ở container |
| Playwright Chromium | **10 passed** trên Docker/PostgreSQL/Redis |
| npm audit | **0 vulnerabilities**; `npm-audit.json` đã cập nhật |
| pip-audit 2.10.1 | **0 known vulnerabilities** trong `backend/requirements.lock` |
| Git whitespace | `git diff --check` đạt |
| Secret check | Key cấu hình không xuất hiện trong 124 đường dẫn source/artifact không bị ignore, XML trong DOCX hoặc bundle JS; không kiểm tra lịch sử Git/hệ thống ngoài dự án |

Audit không bảo đảm không tồn tại lỗ hổng chưa được công bố. Python còn cảnh báo deprecation ở Starlette TestClient/httpx và ReportLab/ast; không làm test thất bại trên Python 3.12.

## Các lỗi đã sửa

- **Thu hồi quyền:** đọc lại role/tool toggle trong worker; kiểm tra quyền hiện tại khi mở conversation, replay idempotency, nguồn tài liệu và audit. Nguồn đã xóa không tiếp tục bị lộ qua kết quả cũ. UI xóa cache/đóng màn hình bảo vệ khi quyền đổi; đồng bộ khi focus, nhận 403 và mỗi 30 giây.
- **Hàng hóa:** tra giá/tồn kho theo tên hoặc SKU, giới hạn sản phẩm khớp và lọc hàng sắp hết; câu trả lời chứa số liệu database. Tìm kiếm bảng hỗ trợ SKU/category. Giá sản phẩm được đọc bằng business tool, không đoán từ tài liệu.
- **Tài liệu:** HNSW iterative scan và exact fallback trong phạm vi được phép khi shortlist thiếu/không đủ liên quan, timeout SQL 2500 ms; khắc phục bỏ sót nguồn khi nhiều vector trùng và có scope riêng tư.
- **Chat:** polling tải lại hội thoại nếu workflow hoàn tất trước lúc SSE kết nối. Đề xuất chờ duyệt và quyết định duyệt/từ chối đều lưu assistant message bền vững.
- **Workflow/quota:** đề xuất ghi chỉ xuất hiện một lần ở cuối plan; timeout áp dụng cả plan phục hồi; ghi token của plan hợp lệ đã gọi provider dù bị quyền chặn. Step đang chạy được đánh dấu lỗi khi thất bại; che exception nội bộ. Ghi duration cho clarification/chờ duyệt.
- **Concurrency:** thống nhất thứ tự advisory lock audit trước event; bỏ khóa workflow không cần thiết trong quota. Sửa fixture PostgreSQL để tạo bảng trong schema test, tránh dùng nhầm public tables có sẵn.
- **Đầu vào/đầu ra:** kiểm tra cấu trúc DOCX, TXT UTF-8 và embedding 384 phần tử số hữu hạn; XHR xử lý lỗi không phải JSON; CSV vô hiệu hóa công thức trong category; PDF báo cáo tự thêm trang thay vì mất dòng.
- **Vận hành/CI:** liveness/readiness, backend healthcheck, frontend chờ backend; stack test cô lập, script chờ app. CI bổ sung PostgreSQL thật, migration/concurrency/vector tests, audits và Playwright.
- **Dependency:** nâng Vite/Zod/resolvers và các package Python bị advisory cảnh báo; khóa phiên bản và kiểm thử tương thích.

## PostgreSQL và hiệu năng

Năm kiểm thử PG xác nhận: hai người duyệt đồng thời chỉ áp dụng một lần; business reader ở READ ONLY/timeout 2500 ms và INSERT bị từ chối; nhiều writer event/audit không deadlock, HMAC chain hợp lệ; migration tạo HNSW và trigger chặn UPDATE/DELETE audit; Top-5 trên 10.000 chunks có nguồn riêng tư.

Benchmark dùng 10.000 vector lexical tổng hợp, 5 chunks public liên quan và 50 chunks Admin có cùng vector liên quan. Employee chỉ nhận đúng 5 public chunks. Lần chốt toàn suite: **17.54 ms**, dưới 3 giây trên máy này. Không dùng số này khẳng định chất lượng semantic, P95, throughput, cold-start hoặc production SLA.

`evaluation-postgres.json` ghi bốn workflow Demo HTTP/SSE: accept 17–32 ms, SSE first byte 4–6 ms, output hữu ích đầu tiên 0.532–1.050 s, hoàn tất 0.533–1.051 s. Ba truy vấn retrieval seed tìm được nguồn dự kiến trong Top-5, 7–16 ms. Bộ nhỏ cố định này không đo thời gian người duyệt/provider thật. `evaluation.json` giữ phép đo SQLite cũ để không trộn môi trường.

## Chạy lại và giới hạn

Theo mục kiểm thử trong `README.md`. PG tests tạo schema UUID và chỉ xóa schema đó. Playwright thay đổi tồn kho/quyền và upload/xóa tài liệu trong database test; không chạy trên dữ liệu chính. CI đã sửa trong source nhưng **chưa push/chạy lại trên GitHub**; kết quả này là kiểm chứng cục bộ.

1. **Semantic retrieval:** cấu hình hiện tại vẫn là lexical. Cần embedding model 384 chiều/credential phù hợp, re-index và bộ câu hỏi có nhãn để đánh giá NFR07. Chat model không tự trở thành embedding model. Adapter semantic có mã nhưng không có bằng chứng chất lượng mới trong đợt này.
2. **Production:** HTTPS/cookie secure, backup/restore, resource limits, load/soak và uptime cần kiểm chứng ở môi trường triển khai. Test cục bộ không chứng minh các chỉ tiêu thống kê NFR03/NFR04/NFR13 trên tải thật.
3. **Giới hạn hiện hữu:** OCR PDF scan, SSO/email reset/notifications, tenant isolation, external audit anchor và ledger chi phí embedding chưa triển khai. Không khai nhận đã hoàn tất; xem `requirements.md` để phân biệt yêu cầu proposal với phần mở rộng.

Tham khảo kỹ thuật: [pgvector iterative scans](https://github.com/pgvector/pgvector#iterative-index-scans), [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/), [Vite security advisory](https://github.com/vitejs/vite/security/advisories/GHSA-8g5g-mxqh-grgj). Kết luận kiểm thử dựa vào chạy mã tại máy, không suy từ tài liệu nhà cung cấp.
