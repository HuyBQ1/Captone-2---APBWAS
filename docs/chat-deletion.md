# Xóa hội thoại — 08/11/2026

Trong AI Workspace, mỗi dòng lịch sử có nút thùng rác “Xóa hội thoại”. Người dùng xem xác nhận rồi chọn “Xóa vĩnh viễn” hoặc “Giữ lại”. Xóa hội thoại đang mở sẽ đưa về màn hình chat mới. Chỉ chủ hội thoại được xóa; Admin cũng không được xóa chat của người khác bằng API này.

DELETE /api/conversations/{id} xóa hàng conversation, tin nhắn, khóa nhớ Redis memory:{id}, tệp generated_files chưa được email tham chiếu, output WorkflowStep/ToolExecution, thông báo, phần lớn event và job workflow đã kết thúc. Mỗi workflow giữ một bản ghi nhỏ với conversation_id=NULL, nội dung/plan/output/snapshot được dọn và cờ conversation_deleted. Các lần retry hoặc worker chạy lại không được tái tạo chat đã xóa.

Giữ UsageRecord/tokens để xóa chat không đặt lại hạn mức; giữ audit bất biến, các bản Report/Approval/ApprovalDecision và MailCampaign/MailDelivery. Tệp đính kèm email được giữ cho cả bản nháp và lịch sử đã gửi. Giữ event có sequence cao nhất, nhưng xóa payload nếu thuộc chat đã xóa, để mốc sequence SSE không lùi lại. Không xóa sản phẩm, giao dịch, tài liệu kho tri thức, cấu hình Agent hay email đã gửi.

Từ chối xóa khi workflow đang queued/planning/running/waiting_approval hoặc job workflow chưa kết thúc. Khóa hàng hội thoại khi tạo yêu cầu tiếp nối và khi xóa; khóa workflow khi retry; khóa tệp khi gắn vào email nhằm tránh tham chiếu tệp đang bị dọn. Không đòi lại quyền đọc nội dung nguồn để chủ sở hữu dọn chat của mình.

Không chỉ ẩn hội thoại trên giao diện: các dòng tin nhắn và blob đủ điều kiện được DELETE thật trong transaction. PostgreSQL thường tái sử dụng vùng trống sau khi vacuum; kích thước file database trên ổ đĩa có thể chưa giảm ngay. API không tự chạy VACUUM FULL. Bản sao lưu trước đây vẫn có thể chứa dữ liệu cũ; không tự xóa backup.

Xác minh: frontend build đạt; 201 kiểm thử backend đạt, gồm xóa thật blob, quyền chủ sở hữu, cấm xóa khi đang chạy, cache, giữ quota/audit, giữ tệp đính kèm email và báo cáo, không ảnh hưởng chat khác, khóa ngoại PostgreSQL và sequence SSE. Bốn kịch bản trình duyệt đạt: xác nhận/hủy/xóa/reload/404 cho chat và file, Word/Excel, email có tệp và Agent tạo tệp. Không xóa hội thoại thật của người dùng trong quá trình triển khai.
