# Mã nguồn của Châu

## Chức năng được giao

- Quản lý hàng hóa và ảnh sản phẩm
- Kết nối và đồng bộ dữ liệu Nova Commerce
- Tính giá vốn, chi phí và lãi/lỗ theo tháng

## Phần bổ sung mới

Phụ trách bảng tài chính theo tháng, giá vốn, chi phí, lợi nhuận và trạng thái dữ liệu thiếu. Bộ xuất/nhập Excel tài chính sử dụng finance_excel.py. Phần này dùng db.py, models.py và router của repository đầy đủ.

## Tệp nguồn trong gói

- `src/business.tsx`
- `src/shop-connection.tsx`
- `backend/app/products.py`
- `backend/app/product_media.py`
- `backend/app/shop_connection.py`
- `backend/migrations/versions/0004_product_images.py`
- `backend/tests/test_products.py`
- `backend/tests/test_product_media.py`
- `backend/tests/test_shop_connection.py`
- `e2e/product-media.spec.ts`
- `e2e/shop-connection.spec.ts`
- `src/finance.tsx`
- `backend/app/finance.py`
- `backend/app/finance_excel.py`
- `backend/migrations/versions/0005_finance.py`
- `backend/tests/test_finance.py`
- `e2e/finance.spec.ts`
- `e2e/finance-complete.spec.ts`

## Phụ thuộc và phối hợp

src/enterprise.tsx và backend/app/enterprise.py ở repository đầy đủ chứa ProductEditor, BusinessActions và API hàng hóa. Hiếu cũng có tệp này cho phần tài khoản. Bộ test shop-connection có các ca doanh số do Triều phụ trách.

Chép các tệp vào đúng đường dẫn trong repository APBWAS đầy đủ trước khi commit. Từng gói sử dụng schema, router, cấu hình và module chung của repository gốc. Các tệp nguồn giữ nguyên nội dung tại thời điểm đóng gói. Những chức năng khác cùng nằm trong tệp dùng chung vẫn theo phân công của nhóm.
