# Email báo cáo và tệp đính kèm — 08/11/2026

Sau khi tạo Word/Excel trong một hội thoại, dùng: “gửi mail file báo cáo này cho toàn bộ nhân viên”. Công cụ prepare_report_email chỉ chọn các tệp do chính người dùng tạo trong cùng workspace và hội thoại, theo tháng đang trao đổi hoặc tháng được nêu rõ. Chọn bản mới nhất của mỗi định dạng cho kỳ đó. Không có tệp phù hợp thì nói rõ và không tự lấy tệp từ hội thoại khác.

Câu bổ sung như “nội dung báo cáo doanh thu tháng 7” giữ ý định email từ yêu cầu người dùng ngay trước đó. Tên người nhận được lấy từ tài khoản đang hoạt động với địa chỉ nhận hợp lệ, bỏ email mẫu/trùng như trước. Email luôn là bản nháp; mở “Mở bản nháp email” để xem người nhận, toàn văn, tên/kích thước và xem trước tệp trước khi xác nhận gửi thật.

Thêm migration 0011 chỉ bổ sung mail_campaigns.attachment_ids JSON, mặc định rỗng cho dữ liệu cũ. Không sửa lịch sử hoặc gửi các bản nháp cũ. Tối đa 5 tệp/tổng 12 MB. API kiểm tra lại người sở hữu/workspace và quyền nguồn lúc tạo nháp, xác nhận và trước từng lượt gửi. Worker đính kèm bytes DOCX/XLSX gốc vào MIME, giữ chính sách không tự gửi lại thư có kết quả chưa xác định. Kiểm thử đối chiếu SHA-256 của từng MIME attachment với tệp đã lưu.

Lỗi nhà cung cấp trong bước phân tích AI giờ giữ thông báo đã được provider chuẩn hóa (timeout, giới hạn token, HTTP từ chối...), thay vì luôn gọi chung là không kết nối. Email có tệp không cần bước diễn giải LLM để tạo nháp. Sửa ngữ cảnh và đính kèm không có nghĩa là provider AI hoặc Gmail luôn sẵn sàng.

Xác minh: 192 kiểm thử backend gồm PostgreSQL/migration đạt; 3 kiểm thử giao diện email đạt, gồm tạo Word/Excel → nhờ gửi file → mở nháp → xem trước attachment. Các lượt Gmail trong kiểm thử dùng HTTP mock, không gửi mail thật. Trước triển khai đã sao lưu và xác minh PostgreSQL: backups/apbwas-20261108-004656.dump. Ứng dụng chính sau triển khai migration 0011, API ready HTTP 200.

## Bổ sung cho Agent đã chọn

Agent mẫu Tạo Word và Excel phiên bản 1 chưa có công cụ email. Đã xuất bản phiên bản 2 cho đúng Agent được đánh dấu file-agent-v1, bổ sung prepare_report_email/open_employee_email và mail.send qua quy trình sửa bản nháp/xuất bản có audit. Không sửa snapshot phiên bản 1 hoặc cấu hình Agent khác; nếu có bản nháp chưa xuất bản thì script nâng cấp dừng để tránh ghi đè. Script: python -m app.upgrade_file_agent. Sao lưu trước nâng cấp: backups/apbwas-20261108-005607.dump.

“cho tôi thêm file exel” giờ nhận nguồn dữ liệu và tháng từ tệp trong cùng hội thoại, kiểm tra quyền nguồn như mọi lần tạo tệp. Bước phân tích nhận metadata tệp đã tạo; không dùng lại chỉ dẫn yêu cầu tạo tệp ở bước diễn giải, và chặn câu trả lời nói chưa tạo tệp khi đã có kết quả công cụ thành công.

Kiểm tra bổ sung: 194 backend đạt; thêm kiểm tra câu diễn giải sai trạng thái và chạy 11 kiểm tra grounding/Agent đạt. Hai kịch bản giao diện email đạt, gồm Agent đã chọn tạo Word → thêm Excel → bản nháp đính kèm. Ứng dụng chính xác nhận Agent published_version=2, công cụ email và quyền mail.send có trong snapshot, giữ đủ hai phiên bản. Workflow cũ vẫn ghim phiên bản cũ; gửi yêu cầu mới sau tải lại trang để dùng phiên bản mới, không retry workflow cũ để thay đổi phiên bản ngầm.
