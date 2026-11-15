# Chọn Agent bằng dấu /

Trong AI Workspace, gõ `/` ở đầu ô nhập để hiện Agent có sẵn. Gõ tiếp tên để lọc (hỗ trợ tên tiếng Việt không dấu). Chọn bằng chuột hoặc phím ↑/↓ rồi Enter; Esc đóng danh sách. Dấu `/` đơn lẻ không được gửi thành một workflow.

Sau khi chọn, Agent xuất hiện phía trên ô nhập. Nhập câu yêu cầu và gửi như bình thường. Backend dùng đúng Agent và phiên bản đã xuất bản, vẫn kiểm tra công cụ, dữ liệu, quota và quyền. Nút X bên cạnh tên quay về trợ lý mặc định. Đổi sang Agent khác mở hội thoại riêng khi gửi; các tin tiếp theo của cùng Agent giữ hội thoại và ngữ cảnh. Chọn hội thoại cũ khôi phục Agent của lần chạy hiện tại.

`GET /api/agents/available?q=...` chỉ trả metadata phiên bản đã xuất bản, đúng workspace/quyền xem, và cấu hình mà người dùng hiện tại được phép chạy. Không hiển thị bản nháp, Agent lưu trữ hoặc quyền vượt tài khoản. Tối đa 100 kết quả; gõ thêm tên để thu hẹp. Không cần dịch vụ AI để mở danh sách.

`POST /api/agents/{id}/runs` bổ sung `conversation_id` tùy chọn. Chỉ nhận hội thoại thuộc người chạy, có lịch sử của cùng Agent; chặn gắn hội thoại của người khác hoặc trộn Agent. Trả thêm `conversation_id`; các client cũ không truyền trường này vẫn mở lần chạy mới như trước. Mỗi workflow giữ snapshot/version riêng như cũ. Không có migration database.

Xác minh 2026-11-05: production build thành công; 136 backend tests và 3 browser tests qua, bao gồm bàn phím, chuột, tìm không dấu, không gửi nhầm dấu /, ranh giới quyền, phiên bản xuất bản, hội thoại hai tin nhắn và bố cục điện thoại. Kiểm thử dùng môi trường riêng, không gọi AI hoặc gửi email thật.
