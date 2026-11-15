# Kết quả kiểm thử APBWAS — 08/11/2026

## Kết quả cuối

| Hạng mục | Kết quả |
| --- | --- |
| Frontend TypeScript và Vite production build | Đạt, 19,61 giây |
| Backend, gồm PostgreSQL thực | 187 đạt, không bỏ qua, 43,79 giây |
| Giao diện Chromium | Cả 28 kịch bản được xác minh đạt qua lượt tổng hợp và chạy lại các ca đã sửa |
| npm audit | 0 lỗ hổng được báo cáo |
| pip-audit requirements.lock | 48 package, 0 lỗ hổng đã biết |
| Khởi động lại backend/worker/frontend thử nghiệm | API ready HTTP 200; số bản ghi giữ nguyên |
| Hệ thống chính cổng 4180 | /api/health/ready và /workspace HTTP 200 |
| Migration hệ thống chính | 0010 |
| Chuỗi audit hệ thống chính | Hợp lệ qua kiểm tra chỉ đọc |

## Phạm vi

Backend kiểm tra xác thực, phân quyền, phiên làm việc, tài khoản, liên kết kích hoạt/khôi phục, dữ liệu sản phẩm, media, giao dịch và tồn kho, tài chính, Word/Excel và công thức, xem trước tệp, kho tri thức, Agent/phiên bản, nhiều model, Gmail, mail hàng loạt, kiểm tra số liệu AI, audit và các migration. PostgreSQL thực kiểm tra đồng thời phê duyệt, chống bán vượt tồn kho, chống ghi trùng, liên kết tài khoản chỉ dùng một lần, publish Agent, quota email, SQL chỉ đọc, audit/event không deadlock và truy xuất pgvector với 10.000 đoạn tài liệu.

Giao diện gồm tạo/xuất bản/chạy Agent, menu slash, model và quyền theo vai trò, hội thoại, RAG và nguồn, báo cáo/CSV, tài khoản doanh nghiệp, ảnh sản phẩm/tải ảnh/lưu sau reload, tồn kho/phê duyệt/bán hàng, Excel import/export và phân tích tài chính trong chat, tạo/tải/xem trước Word/Excel, bố cục di động, chế độ tối và email nháp/Gmail chưa cấu hình.

## Vấn đề phát hiện và xử lý

1. Playwright thiếu Chromium headless shell revision 1248 sau thay đổi phiên bản dependency. Đã cài Chromium tương ứng, sau đó mới chạy giao diện thực tế.
2. Lượt giao diện đầu: 27 đạt, ca ảnh sản phẩm bị HTTP 429 ở bước đăng nhập Admin vì bộ thử dùng cùng tài khoản nhiều lần trong một phút. Đã sửa riêng kịch bản: chờ phản hồi đăng nhập, chỉ khi đúng 429 mới chờ 61 giây và thử thêm một lần; vẫn giữ giới hạn đăng nhập của ứng dụng. Ca ảnh sản phẩm đạt khi chạy riêng, và đạt trong lượt tổng hợp sau (khoảng 1,1 phút, có thực thi nhánh chờ).
3. Lượt tổng hợp sau: 27 đạt; ca business-data có locator mơ hồ khi môi trường thử đã chứa thêm bản Word mã NC-WH-001 do kịch bản upload trước tạo ra. Đã chọn chính xác tài liệu gốc theo tiêu đề, giữ kiểm tra trạng thái chỉ mục và nội dung kho vận. Chạy lại ca này đạt trong 1,7 giây.

Vì vậy kết quả 28 kịch bản là kết quả hợp nhất sau sửa và chạy lại, không phải tuyên bố một lượt chạy đơn có 28/28. Hai thay đổi mã trong lần rà soát này chỉ ở e2e/product-media.spec.ts và e2e/business-data.spec.ts. Không cần sửa hoặc triển khai lại mã ứng dụng chính.

## Lưu trữ và hiệu năng

Sau restart các container ứng dụng thử nghiệm: 8 generated_files, 58 sản phẩm, 3.594 giao dịch, 9 tài khoản giữ nguyên số lượng; API qua frontend thử nghiệm trả 200. Đây là dữ liệu riêng của bộ thử, không phải số liệu doanh nghiệp ở cổng 4180.

Bốn luồng demo HTTP/worker hoàn tất trong 0,531–1,066 giây; ba truy vấn kho tri thức đều có tài liệu mong đợi trong top 5, mất 0,007–0,010 giây. Các con số này chỉ đo môi trường cục bộ, dữ liệu mô phỏng và tìm kiếm lexical, không suy rộng thành hiệu năng AI thật hoặc tải doanh nghiệp.

## Cảnh báo và giới hạn

- Build có cảnh báo chunk JavaScript lớn và annotation trong Zod; build vẫn thành công.
- Hai cảnh báo deprecated từ thư viện kiểm thử FastAPI/Starlette và ReportLab; không có kiểm thử backend thất bại.
- Kiểm thử provider, Gmail và gửi email dùng mock; lần này không gửi email thật và không gửi dữ liệu tài chính tới provider AI. Lượt kiểm thử Intern AI thật ngày 05/11 được ghi riêng trong business-ai.md, không được tính là kiểm thử lại lần này.
- Chưa thực hiện thử tải dài hạn, chứng nhận an ninh, gửi thư thật hay kiểm tra độ chính xác mọi nhận xét định tính của LLM.
- Không thay đổi database, tài khoản, dữ liệu hay cấu hình bí mật của hệ thống chính. Kiểm tra hệ thống chính chỉ đọc health, migration và audit.

## Bằng chứng cục bộ

Log tại `.test-tmp/retest-20261108-*`: build, stack, backend, npm-audit.json, python-audit.log, e2e.log, e2e-final.log, product-media.log, business-data.log, evaluation.log, main-integrity.log, persistence-before.log và persistence-after.log. Hai lượt giao diện có lỗi nêu trên được giữ nguyên log; không thay log lỗi bằng kết quả chạy lại.

Để chạy trọn bộ từ dữ liệu thử mới: dùng `docker compose -f compose.test.yaml down --volumes` rồi `up -d --build`, chạy pytest với PG_TEST_DATABASE_URL trỏ database thử, và Playwright với E2E_URL=http://localhost:4181. Không dùng lệnh xóa volume với compose.yaml của hệ thống chính.
