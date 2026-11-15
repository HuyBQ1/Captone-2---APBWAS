# AI tạo Word và Excel

Tải lại AI Workspace, gõ `/` và chọn **Tạo Word và Excel**. Có thể dùng trợ lý mặc định. Các Agent đã xuất bản trước đó không bị sửa; muốn dùng công cụ trong Agent riêng, bật **Tạo tệp Word** và **Tạo tệp Excel**, cấp quyền đọc nguồn tương ứng rồi xuất bản phiên bản mới.

Ví dụ:

- “Tạo file Word và Excel báo cáo tài chính tháng 07/2026.”
- “Xuất file Excel tồn kho.”
- “Tạo Word tổng hợp chính sách nghỉ phép từ tài liệu nội bộ.”
- “Tạo file Word thông báo họp lúc 9 giờ sáng mai, nội dung nhắc nhân viên chuẩn bị báo cáo công việc.”
- “Tạo file Excel dự toán văn phòng, gồm hạng mục, số lượng, đơn giá, thành tiền và dòng tổng.”

Chat hiển thị **Tệp đã tạo**, nút **Tải Word / Tải Excel**, tên và kích thước file. Mở lại hội thoại vẫn tải được. File DOCX/XLSX gốc lưu trong PostgreSQL, cùng người tạo, workspace, workflow, thời gian, loại nguồn và SHA-256. Không tự gửi email hay đưa tệp lên dịch vụ ngoài.

## Xem trước trong chat

Bấm **Xem trước** trên thẻ tệp để mở nội dung trước khi tải. Excel có các tab trang tính, phân trang dữ liệu và tùy chọn **Hiện công thức**. Giá trị hiển thị lấy từ kết quả tính sẵn trong tệp; công thức không có kết quả cache được ghi rõ, không tự coi là số 0. Word hiển thị đoạn văn, tiêu đề và bảng; tải DOCX để giữ đầy đủ định dạng trang gốc.

Khung xem mặc định rộng tối đa 1.080 px với bảng gọn hơn, có nút **Thu gọn / Toàn màn hình**. Excel bật sẵn **Vừa chiều ngang** để hiển thị đủ các cột và xuống dòng nội dung dài; tắt tùy chọn này để dùng cột rộng và thanh cuộn ngang. Dùng cuộn dọc và nút chuyển trang để đọc những dòng còn lại.

Xem trước chỉ đọc bản tệp đã lưu, không thay đổi hoặc tính lại theo database hiện tại, không gửi tệp sang dịch vụ ngoài. API kiểm tra lại cùng quyền người tạo, workspace và nguồn như khi tải xuống. Đã kiểm tra 166 kiểm thử backend và một kịch bản giao diện gồm chuyển sheet, hiện công thức, phân trang, Word và màn hình di động.

## Nguồn và phép tính

Tài chính xuất theo một tháng, dùng số doanh thu, giá vốn, chi phí và tồn kho từ database. Excel dùng mẫu APBWAS có công thức và kết quả tính sẵn; Word dùng cùng hàm tổng hợp tài chính. Thể hiện rõ dữ liệu mẫu, giá vốn/chi phí còn thiếu, lợi nhuận vận hành chưa phải sau thuế, tồn kho là hiện tại. Không tự điền số liệu thiếu. Tồn kho/danh mục xuất từ bảng products và inventory.

Tháng ghi rõ trong yêu cầu luôn ưu tiên hơn tháng trong lịch sử: “tạo báo cáo doanh thu tháng 8 bằng exel” xuất tháng 08, không lấy tháng hiện tại. Nếu thiếu năm, dùng năm của kỳ đang trao đổi hoặc năm hiện tại khi chưa có kỳ trong hội thoại. Có thể ghi đầy đủ “tháng 8 năm 2026”, “08/2026” hoặc “2026-08”. “Tháng này/tháng trước” dùng lịch Asia/Ho_Chi_Minh; yêu cầu tiếp nối không nêu tháng giữ kỳ đang trao đổi.

Nội dung mới dùng LLM hiện đang chọn để soạn, đánh dấu Word là bản dự thảo. Connected Mode luôn gọi Agent LLM để chọn công cụ, kể cả yêu cầu có `Tiêu đề: ...` rồi `Nội dung: ...` trên hai dòng; chỉ dẫn yêu cầu giữ nguyên văn nội dung đó. Demo Mode chạy mẫu tài chính/tồn kho và Word có nội dung được cung cấp bằng luồng cục bộ; không giả lập việc LLM soạn bảng tùy ý.

Excel tùy chỉnh nhận dữ liệu và công thức theo schema, không chạy mã AI. Hỗ trợ toán + − × ÷, SUM, AVERAGE, MIN, MAX, COUNT, ROUND và tham chiếu trong cùng bảng. Có kiểm tra vòng lặp, ô vượt phạm vi, chia 0, số không hữu hạn và giá trị cache. Chuỗi trông như công thức vẫn là văn bản nếu không nằm trong trường công thức. Không hỗ trợ macro, liên kết ngoài, công thức tùy ý hoặc Python do LLM sinh.

Kho tri thức xuất thành Word các trích đoạn có nguồn từ tài liệu được phép truy cập; không coi đó là bản chính sách mới được doanh nghiệp ban hành. Agent chỉ dùng tài liệu đã gắn trong cấu hình và quyền hiện tại.

## Giới hạn và quyền

Word tối đa 8 cột và 200 dòng bảng. Excel tùy chỉnh tối đa 20 cột, 1.000 dòng, 500 công thức; xuất tồn kho tối đa 2.000 SKU. Excel tài chính giữ giới hạn có sẵn 5.000 dòng bán, 1.000 chi phí và 2.000 SKU. Mỗi workflow tạo tối đa một Word và một Excel, file tối đa 8 MB. Yêu cầu vượt phạm vi báo lỗi để chia nhỏ, không cắt dữ liệu ngầm.

Tệp riêng cho người tạo và workspace, tải qua API có đăng nhập. Kiểm tra lại quyền nguồn khi tải: tài chính cần sales.read/inventory.read, kho cần inventory.read, tài liệu cần documents.read và quyền tài liệu nguồn. Không cấp thêm quyền chỉ vì người dùng nhờ AI tạo file. Công cụ cần agents.run và phải được bật trong Agent; đọc nguồn còn phụ thuộc quyền đã ghim trong Agent.

## Triển khai và kiểm tra

Migration `0010` chỉ thêm bảng generated_files, có bảo vệ downgrade khi đã có tệp. Agent mẫu được tạo bằng `python -m app.seed_file_agent`, không sửa các phiên bản Agent có sẵn. File được tạo theo bước của workflow hiện có, không thêm một bộ thực thi Agent khác. Template Excel được tạo bằng Artifact Tool, template Word có style dùng lại; ứng dụng điền dữ liệu vào template và lưu tệp gốc.

Kiểm thử bao gồm tải DOCX/XLSX thật từ chat, tính công thức, mở lại lịch sử, chặn quyền/khác workspace, tải lặp và migration PostgreSQL. Đã kiểm tra Word bằng Microsoft Word, xuất PDF và xem ảnh từng trang (báo cáo 1 trang, tồn kho 2 trang), kiểm tra Excel bằng Artifact Tool import/tính lại/render. Renderer đóng gói thiếu LibreOffice trong máy, nên dùng Microsoft Word cục bộ ở chế độ chỉ đọc để xuất PDF cho QA. Bản thử dùng dữ liệu mô phỏng và không gọi AI thật.
