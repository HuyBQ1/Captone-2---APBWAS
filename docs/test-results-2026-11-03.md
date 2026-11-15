# Kết quả kiểm thử ngày 03/11/2026

| Kiểm tra | Kết quả |
|---|---|
| Backend pytest trong container Linux với PostgreSQL thật | 91 passed, 0 failed, 0 skipped; 18.30 giây |
| Playwright Chromium | 15 passed, 0 failed; 36.4 giây |
| TypeScript và Vite production build | Thành công; 5.76 giây |

Backend chạy với PG_TEST_DATABASE_URL trong stack riêng `apbwas-review`; frontend test tại cổng 4181. Bộ thử gồm PostgreSQL concurrency/migration/vector, tài khoản/phân quyền, giao dịch bán hàng/tồn kho, nguồn RAG, nội dung bảng Word, lưu trữ phiên bản và nghiệp vụ qua trình duyệt.

Các bài thử dùng Demo planner, lexical embeddings và mock provider; không gọi API AI thật. Không chạy các thao tác kiểm thử thay đổi dữ liệu trên database Nova Commerce tại cổng 4180. Stack thử nghiệm được dọn sau khi chạy.

## Lệnh đã chạy

```powershell
npm run build
docker compose -f compose.test.yaml up -d --build
docker compose -f compose.test.yaml exec -T -e PG_TEST_DATABASE_URL=postgresql+psycopg://apbwas_test:local-test-only@postgres:5432/apbwas_test backend pytest tests -q --tb=short --junitxml=/tmp/apbwas-test-results.xml
$env:E2E_URL='http://localhost:4181'
npm run test:e2e
```

## Cảnh báo còn lại

- Chunk biểu đồ khoảng 600 kB, Vite cảnh báo kích thước bundle. Build vẫn thành công.
- Starlette TestClient cảnh báo httpx deprecated; ReportLab cảnh báo ast.NameConstant deprecated. Hai cảnh báo không làm test thất bại trên Python 3.12.
- Playwright báo NO_COLOR bị bỏ qua khi FORCE_COLOR được bật; không ảnh hưởng kết quả.

Log và JUnit của lần chạy được lưu trong `.test-tmp/test-run-*-20261103.*`, không đưa vào Git. Kết quả này là kiểm thử cục bộ, không phải kết quả GitHub Actions hoặc xác nhận hiệu năng/provider sản xuất.
