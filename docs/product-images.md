# Ảnh sản phẩm Nova Commerce — 03/11/2026

Danh mục chính có 56 sản phẩm. Đã bổ sung 56 ảnh minh họa vector và 56 mô tả dựa trên tên/SKU/danh mục hiện có. Không thêm thông số kỹ thuật, bảo hành hoặc chứng nhận chưa có hồ sơ. Ảnh minh họa không phải ảnh chụp hàng thực tế; cửa sổ chi tiết thể hiện nguồn ảnh.

## Sử dụng

- Mở **Dữ liệu doanh nghiệp → Sản phẩm** để xem lưới ảnh. Có thể chuyển sang Danh sách hoặc tra tồn kho như trước.
- Nhấn sản phẩm để xem ảnh, SKU, mô tả, giá niêm yết, trạng thái, tồn kho và ngưỡng cảnh báo.
- Người có `business.manage` dùng **Thay ảnh sản phẩm** trong chi tiết để tải JPG/PNG/WebP. Tối đa 5 MB và 16 megapixel; server đọc nội dung, xoay theo EXIF, thu nhỏ tối đa 1400×1400 và lưu lại WebP. File giả ảnh/SVG do người dùng tải lên bị từ chối.
- Chỉnh sửa sản phẩm có thêm trường mô tả tối đa 2.000 ký tự. Ảnh có thể thêm sau khi tạo sản phẩm mới.

## Database và vận hành

Migration **0004** thêm `products.description` và bảng `product_images`: `product_id` (PK/FK), `content` (BYTEA), `mime_type`, `sha256`, `source`, `updated_at`. Toàn bộ bytes ảnh nằm trong PostgreSQL và được đưa vào `pg_dump` hiện có. Schema hiện có 27 bảng; tài liệu/diagram migration 0003 là phiên bản trước khi bổ sung ảnh.

GET ảnh yêu cầu đăng nhập và `inventory.read`, bao gồm cả yêu cầu dùng ETag. PUT ảnh yêu cầu `business.manage` và ghi audit. Cache private, phải kiểm tra lại; URL đổi theo hash ảnh. API danh sách chỉ truy vấn metadata ảnh, không tải toàn bộ BYTEA để phân trang.

`python -m app.seed_product_media` chỉ bổ sung ảnh cho SKU mẫu NC-/AP- chưa có ảnh và mô tả còn trống. Không ghi đè ảnh tải lên hoặc mô tả hiện có, không gọi AI hay tải ảnh từ dịch vụ bên ngoài. Chạy lại trên database chính: `added=0`, `total_images=56`.

Main compose tự chạy bước này sau migration/seed. Việc cập nhật giữ nguyên sản phẩm, giá, tồn và 3.552 bản ghi bán hàng. Kiểm chứng sau cập nhật: schema 0004, 56 ảnh, 56 mô tả, audit hợp lệ. Backup trước/sau nằm trong thư mục `backups/` được Git bỏ qua.

## Kiểm thử

Kết quả cuối: **94/94 backend tests đạt** (PostgreSQL, không skip), **16/16 Playwright tests đạt**, production build thành công. Ứng dụng chính trả readiness `database=true`, `redis=true`.

Production build thành công. Kiểm thử backend bao gồm xác thực, phân quyền đọc/đổi ảnh, thu hồi quyền với ETag, file giả ảnh, giới hạn dung lượng, chuẩn hóa ảnh, bytes trong DB, import lặp lại và giữ ảnh người dùng. Kiểm thử PostgreSQL bổ sung trường hợp nâng schema cũ hai lần mà vẫn giữ giá/version/SKU.

Playwright kiểm tra ảnh tải thành công, đổi ảnh, tải lại trang vẫn giữ ảnh, bố cục điện thoại và các luồng nghiệp vụ cũ. Stack kiểm thử dùng database riêng và provider demo; không gọi dịch vụ AI bên ngoài. Logs: `.test-tmp/product-media-backend.log`, `.test-tmp/product-media-e2e.log`.
