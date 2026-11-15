# Chuyển APBWAS sang dữ liệu doanh nghiệp thực

Ngày thực hiện: 08/11/2026 (Asia/Saigon).

## Phạm vi được yêu cầu

Xóa sản phẩm, giao dịch và tài liệu mô phỏng Nova Commerce; giữ tài khoản và cấu hình. Không xóa dữ liệu không xác định được nguồn mô phỏng.

Đã tạo và kiểm tra bản sao PostgreSQL trước khi dọn:
`D:\captone 2\backups\apbwas-20261108-022811.dump`.

## Kết quả database chính

Đã xóa 56 sản phẩm, 3.552 dòng bán hàng, 60 khoản chi phí, 55 tài liệu, 21 báo cáo và 6 tệp báo cáo phát sinh. Đã dọn dữ liệu kết quả mô phỏng của 46 workflow và 10 kỳ tài chính. Các bảng sản phẩm, bán hàng, chi phí, tài liệu, báo cáo và tệp tạo hiện có 0 bản ghi.

Giữ 6 tài khoản, phiên đăng nhập, 1 kết nối Gmail, khóa/cấu hình model và cấu hình Agent. Ba Agent được xuất bản phiên bản mới chỉ để bỏ liên kết tới tài liệu đã xóa; giữ lịch sử phiên bản. Nhật ký audit và thống kê sử dụng được giữ; chuỗi audit xác minh hợp lệ.

Đã dọn nội dung báo cáo mô phỏng trong 3 bản email lưu cục bộ, gỡ tệp liên quan và hủy bản nháp chưa gửi. Trạng thái gửi thành công cùng mã thư của lịch sử gửi được giữ. Không gửi email trong quá trình kiểm thử này. Không xóa thư đã tồn tại bên Gmail.

`DEMO_MODE=false`, `SAMPLE_DATA=false`. Dấu `sample-data-removed-v1` ngăn các trình seed tự thêm lại dữ liệu mẫu. Tệp nguồn mẫu trong repository và bản backup vẫn là tài liệu ngoại tuyến, không còn là kho tri thức hoạt động.

## Luồng trả lời AI

Connected Mode dùng LLM lập kế hoạch gọi công cụ, đọc kết quả được cấp quyền và soạn câu trả lời cuối cùng. Nội dung trả lời chính không còn ghép câu mẫu hoặc toàn bộ đoạn trích thô làm câu trả lời thay AI.

Bộ kiểm chứng chấp nhận mã tài liệu, trích dẫn và danh sách đánh số hợp lệ; vẫn chặn số liệu hoặc liên kết không có nguồn. Khi phản hồi không đạt kiểm chứng, cho model sửa tối đa một lần trong thời gian còn lại. Thiếu dữ liệu phải nói rõ cần bổ sung gì, không tự suy ra chính sách nghỉ phép hoặc lợi nhuận.

Việc tính toán được công cụ thực hiện trên dữ liệu database; AI diễn giải kết quả. Cần nhập dữ liệu sản phẩm, giao dịch, chi phí và chính sách thực trước khi yêu cầu kết luận về doanh nghiệp.

## Kiểm thử

- 226 bài kiểm thử backend đạt; sau thay đổi cuối, 24 bài kiểm thử trọng tâm đạt.
- 3 bài Playwright đạt: nguồn tài liệu, email dùng tệp báo cáo và Agent tạo Word/Excel rồi soạn email.
- Lượt kiểm thử thực qua worker và model đang cấu hình: workflow `50abd3da-7012-428f-976c-74adc353352e`, trạng thái `completed`, chế độ `llm_agent`, công cụ `search_internal_documents`.
- Câu hỏi: “Nhân viên được phép nghỉ bao nhiêu ngày?”. AI trả lời không có nguồn phù hợp (0 kết quả), chưa thể xác định số ngày nghỉ và cần bổ sung chính sách hiện hành. Không tự đưa ra số ngày nghỉ.

Sau khi cập nhật, tải lại trang bằng Ctrl+F5 và nhập tài liệu/dữ liệu thực trong Kho tri thức và Dữ liệu doanh nghiệp.
