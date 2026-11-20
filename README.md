# Mã nguồn của Triều

## Chức năng được giao

- Báo cáo doanh số và xem chi tiết theo tháng
- Kết nối Gmail và gửi email nhân viên
- Xem trước tệp Word và Excel

## Phần bổ sung mới

Phụ trách hộp xem trước tệp, chuyển sheet, xem bảng, công thức và phân trang nội dung. API được office_files.py trong repository đầy đủ gọi tới office_preview.py. Các bộ kiểm thử đi kèm còn bao gồm tạo tệp qua luồng hiện có. Agent và Workflow tiếp tục nằm ngoài phần phân công.

## Tệp nguồn trong gói

- `src/nova-sales-report.tsx`
- `src/mail.tsx`
- `src/bulk-mail.tsx`
- `backend/app/gmail.py`
- `backend/app/mail_campaigns.py`
- `backend/migrations/versions/0007_gmail.py`
- `backend/migrations/versions/0008_bulk_mail.py`
- `backend/migrations/versions/0011_mail_attachments.py`
- `backend/migrations/versions/0012_personal_gmail.py`
- `backend/tests/test_gmail.py`
- `backend/tests/test_bulk_mail.py`
- `backend/tests/test_mail_attachments.py`
- `e2e/gmail.spec.ts`
- `e2e/personal-gmail.spec.ts`
- `e2e/bulk-mail.spec.ts`
- `src/file-preview.tsx`
- `backend/app/office_preview.py`
- `backend/tests/test_office_files.py`
- `backend/tests/test_word_documents.py`
- `e2e/office-files.spec.ts`

## Phụ thuộc và phối hợp

src/pages.tsx ở repository đầy đủ chứa Reports và ReportDetail; backend/app/main.py chứa API doanh số. Tệp dùng chung office_files.py liên kết xem trước với lưu và tải tệp. Châu giữ bộ test shop-connection có các ca báo cáo.

Chép các tệp vào đúng đường dẫn trong repository APBWAS đầy đủ trước khi commit. Từng gói sử dụng schema, router, cấu hình và module chung của repository gốc. Các tệp nguồn giữ nguyên nội dung tại thời điểm đóng gói. Những chức năng khác cùng nằm trong tệp dùng chung vẫn theo phân công của nhóm.
