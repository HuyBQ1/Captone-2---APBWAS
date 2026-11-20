# Mã nguồn của Hiếu

## Chức năng được giao

- Đăng ký tài khoản
- Quên và đặt lại mật khẩu
- Quản lý hồ sơ tài khoản cá nhân
- Quản lý phiên đăng nhập và thiết bị

## Phần bổ sung mới

Xem thiết bị đang đăng nhập, nhận diện phiên hiện tại và kết thúc phiên tại Cài đặt tài khoản. Mã nằm trong AccountCenter của src/enterprise.tsx và API auth/sessions trong backend/app/enterprise.py; các tệp này đã có trong gói.

## Tệp nguồn trong gói

- `src/public-accounts.tsx`
- `backend/app/public_accounts.py`
- `backend/migrations/versions/0013_registration_recovery.py`
- `backend/tests/test_public_accounts.py`
- `e2e/public-accounts.spec.ts`
- `src/enterprise.tsx`
- `backend/app/auth.py`
- `backend/app/enterprise.py`
- `backend/tests/test_enterprise.py`
- `e2e/enterprise.spec.ts`

## Phụ thuộc và phối hợp

src/enterprise.tsx và backend/app/enterprise.py chứa cả phần tài khoản và hàng hóa. Hiếu phụ trách tài khoản, hồ sơ và phiên đăng nhập, phối hợp với Châu khi sửa cùng tệp. API /api/auth/profile nằm trong backend/app/main.py ở repository đầy đủ.

Chép các tệp vào đúng đường dẫn trong repository APBWAS đầy đủ trước khi commit. Từng gói sử dụng schema, router, cấu hình và module chung của repository gốc. Các tệp nguồn giữ nguyên nội dung tại thời điểm đóng gói. Những chức năng khác cùng nằm trong tệp dùng chung vẫn theo phân công của nhóm.
