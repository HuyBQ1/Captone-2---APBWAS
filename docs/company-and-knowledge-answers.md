# Trả lời hồ sơ doanh nghiệp và kho tri thức — 08/11/2026

Connected Mode vẫn để model chọn công cụ. Thêm get_company_profile (quyền agents.run) để đọc tên và liên hệ/địa chỉ/mã số thuế đã cấu hình trong workspace; danh mục hàng hóa chỉ được đọc nếu có inventory.read ở cả người dùng và cấu hình Agent khi chạy Agent riêng. Không suy đoán tên pháp nhân hoặc ngành nghề đăng ký từ danh mục. Workspace khác primary chỉ đọc tên workspace của chính nó, không nhận cấu hình công ty primary.

Prompt hướng Agent chọn hồ sơ doanh nghiệp cho “đây là công ty gì”, thay vì tìm quy trình tài khoản/nhập kho. Kết quả hồ sơ được gửi cho bước tổng hợp để trả lời tối đa hai đoạn, giữ thông tin dữ liệu mẫu/mô phỏng và nói rõ thông tin chưa cấu hình. Không tự thêm công cụ vào các phiên bản Agent riêng đã xuất bản; Agent riêng phải được quản trị bật công cụ phù hợp.

search_internal_documents tiếp tục tìm nguồn theo quyền và kho tri thức đã ghim. Câu tóm tắt mặc định chỉ nêu số đoạn tìm được và hướng tới thẻ nguồn, không nối toàn bộ content vào chat. Bước tổng hợp nhận tối đa bốn trích đoạn có giới hạn, kiểm tra lại workspace/phạm vi/trạng thái tài liệu và knowledge_ids trước khi gửi model. Chỉ tổng hợp theo yêu cầu, bỏ mẫu ký tên/đầu chân trang lặp, giữ nguồn trên giao diện. Khi hoàn tất, câu tổng hợp thay phần thông báo tìm nguồn chứ không nối sau cả bức tường văn bản.

Cho phép câu trả lời văn bản có nguồn mà không bắt buộc chèn một con số cho đủ điều kiện. Số trong chính sách lấy từ document_references được trích trong đúng phần tài liệu cung cấp; số ngoài nguồn và liên kết lạ vẫn bị chặn. Đối chiếu giá trị không chứng minh mọi nhận xét định tính hoặc cách gắn đơn vị của model đều đúng.

Tin nhắn lịch sử giữ nguyên; gửi câu hỏi mới để dùng luồng mới. Khi provider hoặc quota không sẵn sàng, giữ phản hồi công cụ ngắn và thông báo lỗi; không quay lại đổ nguyên văn nguồn. Không xóa tài liệu hoặc thay đổi hồ sơ doanh nghiệp trong bản sửa này.

Kiểm thử: 219 backend đạt. Gồm model chọn hồ sơ → đọc cấu hình công ty → tổng hợp câu ngắn; chính sách nghỉ phép có số được dẫn từ trích đoạn; không lộ tài liệu bị thu quyền trước tổng hợp; không đọc nhầm workspace; câu văn có nguồn không cần số giả để qua validator. Kiểm thử HTTP model dùng mock, không gửi dữ liệu tài liệu thật ra ngoài trong bộ thử.

Sau triển khai: API ready cổng 4180 HTTP 200; đọc chỉ tên cấu hình xác nhận Nova Commerce và sample_data=true. Probe model Intern AI thật với câu “đây là công ty gì” và ngữ cảnh yêu cầu gửi báo cáo trước đó chọn đúng get_company_profile, usage 2.499 token. Probe chỉ gửi câu hỏi/ngữ cảnh mẫu/schema, không gửi liên hệ doanh nghiệp hay nội dung tài liệu. Kiểm thử trình duyệt RAG dẫn nguồn/mở nội dung gốc đạt.
