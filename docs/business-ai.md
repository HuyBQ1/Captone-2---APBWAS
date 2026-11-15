# AI đọc dữ liệu doanh nghiệp

Connected Mode giờ có bước diễn giải bằng LLM sau khi công cụ đọc và tính dữ liệu thành công. Áp dụng truy vấn tài chính, doanh thu, so sánh kỳ, sản phẩm giảm doanh số, tra giá, tồn kho và báo cáo doanh thu. Khi tạo Word/Excel tài chính, AI nhận chỉ tiêu của đúng snapshot dùng tạo tệp; nội dung phân tích xuất hiện trong chat cùng nút tải. Các tệp dùng mẫu và công thức backend như trước, không tự thêm nội dung AI vào tệp đã lưu.

AI nhận các chỉ tiêu và tối đa 20 hàng kết quả đã được phép truy cập, không nhận thông tin đăng nhập database, email nhân viên hay toàn bộ database. Model dùng kết nối đã chọn trong chat hoặc cấu hình phiên bản Agent. Kiểm tra lại quyền người dùng, workspace, nguồn tệp và allowlist công cụ trước khi gửi dữ liệu. Với dữ liệu mô phỏng, giữ nhãn mô phỏng; tồn kho là hiện tại, lợi nhuận vận hành chưa phải sau thuế.

Backend tính doanh thu, giá vốn, chi phí, số đơn, tồn kho, giá trị đơn trung bình, doanh thu trung bình mỗi đơn vị và các tỷ suất. Không kết luận lợi nhuận nếu thiếu giá vốn hoặc chưa xác nhận đầy đủ chi phí. AI dẫn chỉ tiêu bằng mã tham chiếu; backend chỉ chèn số đã tính, chặn số hoặc liên kết tự thêm. Giới hạn này không phải chứng minh mọi nhận xét định tính của model là đúng: người dùng vẫn cần đối chiếu dữ liệu.

Kết quả lưu trong workflow.result.business_analysis, tin nhắn hội thoại, audit và thống kê token. Nếu provider lỗi hoặc trả số không có bằng chứng, giữ số liệu/tệp đã tính và ghi rõ phân tích AI chưa khả dụng. Demo Mode chỉ dùng công cụ, không giả lập có phân tích LLM. Không gửi thư và không thay đổi dữ liệu nghiệp vụ trong bước này.

Ví dụ: “Tính lợi nhuận và giá trị đơn trung bình tháng 8 năm 2026”, “Phân tích tồn kho sắp hết”, “Tạo Excel báo cáo tài chính tháng 8 năm 2026”. Agent tùy chỉnh vẫn phải bật công cụ nguồn và có quyền tương ứng.

Kiểm thử: bộ backend 186 trường hợp đạt; sau bổ sung chỉ tiêu trung bình/tỷ suất, 14 kiểm thử tài chính và grounding đạt. Kiểm thử HTTP dùng mock để xác minh payload tới model, số liệu nguồn, token, model tùy chọn, chặn số giả, giới hạn quyền và fallback khi provider lỗi.

Kiểm thử thật ngày 05/11/2026: người dùng cho phép gửi các chỉ tiêu tổng hợp tháng 08/2026 tới https://discovery-api.intern-ai.org.cn/v1, model deepseek-v4-flash-vision. Lượt đầu giới hạn 1.000 token bị cắt; lượt 3.200 token nhận phân tích hợp lệ, dùng 2.557 token tổng. Backend đối chiếu tất cả tham chiếu số liệu. Không gửi danh sách nhân viên, không tạo/gửi thư, không thay đổi dữ liệu nghiệp vụ. Luồng diễn giải trong ứng dụng dùng tối đa 3.200 token đầu ra cho trợ lý mặc định; Agent riêng vẫn tuân theo giới hạn đầu ra đã cấu hình.

Ngày 08/11 sửa chặn nhầm chữ số trong mã hàng: context có thêm verified_texts và tham chiếu t cho SKU, tháng/ngày, tên/danh mục chứa số từ kết quả công cụ. Cho phép trích nguyên văn đúng thực thể với kiểm tra ranh giới, không chấp nhận AP-0019 hoặc XAP-001 thay AP-001. Số viết trực tiếp chỉ được chấp nhận khi khớp giá trị nguồn hoặc cách định dạng của backend; số lạ và liên kết lạ vẫn bị chặn, với thông báo lỗi riêng. Ví dụ AP-001 tồn 50, ngưỡng 20 có thể được diễn giải bình thường; tồn 500 không có trong nguồn bị từ chối. Đây là đối chiếu giá trị, không chứng minh model đã gắn đúng ý nghĩa/đơn vị cho mọi chỉ tiêu. Không sửa lại các tin nhắn lịch sử có thông báo lỗi; yêu cầu mới dùng bộ đối chiếu mới.
