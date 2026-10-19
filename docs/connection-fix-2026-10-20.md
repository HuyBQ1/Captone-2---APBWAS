# Khôi phục kết nối Docker — 20/10/2026

Nguyên nhân quan sát được: cổng Windows 5432 đã thuộc PostgreSQL của dự án khác; 4173 thuộc ứng dụng Aion2. PostgreSQL APBWAS ở trạng thái container chưa chạy, sau lần khởi động có NetworkSettings.Networks rỗng. Init không resolve được hostname `postgres`, thoát 1, khiến dependency chặn backend/worker/frontend.

Đã bỏ publish cổng PostgreSQL, chuyển web sang `${FRONTEND_PORT:-4180}`, cập nhật cấu hình mẫu và README. Tạo lại riêng container PostgreSQL để phục hồi endpoint mạng, giữ volume dữ liệu; sau đó chạy `docker compose up -d`. Các ứng dụng khác tiếp tục chạy.

Kiểm chứng qua http://localhost:4180: frontend GET 200, đăng nhập tài khoản Manager seed 200, GET /api/overview 200 và trả 13 workflow. Đã logout phiên dùng để kiểm tra. PostgreSQL/Redis healthy; init Exited (0); backend/worker/frontend Up. Đây là xác minh kết nối/login/dashboard trên PostgreSQL thật, không phải benchmark đầy đủ NFR hay bộ kiểm thử concurrency.
