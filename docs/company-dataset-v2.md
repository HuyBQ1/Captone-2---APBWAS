# Dữ liệu vận hành Nova Commerce

Ngày nhập: 08/11/2026. Người dùng chưa có hồ sơ nguồn và yêu cầu tạo bộ dữ liệu nghiệp vụ, trình bày theo tên doanh nghiệp bình thường.

## Nguồn và phạm vi

Sản phẩm, đơn bán, biến động kho và chi phí mới do chương trình tạo. Đây không phải chứng từ giao dịch thực tế. Nguồn được ghi trong database tại `nova-commerce-operational-v2`: `origin=generated`, `real_transactions=false`, kèm danh sách ID và số liệu đối chiếu theo tháng. Không tạo mã số thuế, pháp nhân, địa chỉ hoặc chữ ký giả. Không bật Demo Mode hoặc Sample Data.

Tệp **Nghi Phep.docx** có trước lần nhập này được giữ nguyên. Nội dung người dùng cung cấp là nhân viên được nghỉ phép 5 ngày trong 1 tháng. Không nhập quy định phép năm khác để tránh mâu thuẫn. Không suy số phép còn lại từng người khi chưa có sổ nghỉ phép cá nhân.

## Kết quả nhập

| Dữ liệu | Số lượng |
|---|---:|
| Sản phẩm | 28 |
| Ảnh minh họa sản phẩm | 28 |
| Dòng bán hàng | 1.736 |
| Mã đơn không trùng | 1.054 |
| Chi phí | 66 |
| Biến động kho | 2.038 |
| Tài liệu Word thêm mới | 5 |
| Tổng tài liệu gồm tệp đã có | 6 |

Kỳ dữ liệu: tháng 01 đến ngày 08/11/2026. Từng dòng bán có số lượng, doanh thu sau giảm giá, giá vốn, mã đơn và mã tham chiếu duy nhất. Sổ nhập/xuất liên tục theo SKU, không âm, khớp tồn hiện tại. Giá bán lịch sử không thay đổi theo giá niêm yết mới.

Chi phí gồm mặt bằng, nhân sự, vận chuyển, tiếp thị, phần mềm và khấu hao. Các tháng 01–10 được đánh dấu đủ chi phí của bộ dữ liệu. Tháng 11 đang mở, chưa xác nhận đủ chi phí; hệ thống không được kết luận lợi nhuận cuối tháng. Chưa tính thuế, hoàn tiền, công nợ và dòng tiền ngân hàng.

Ví dụ đối chiếu tháng 08/2026: doanh thu 1.452.911.520 VND; giá vốn 1.024.033.000 VND; chi phí 163.645.000 VND; lợi nhuận vận hành 265.233.520 VND; 102 mã đơn, không thiếu giá vốn hoặc mã đơn.

## Kho tri thức và Agent

Năm tài liệu mới: hồ sơ hoạt động, bán hàng/báo giá, quản lý tồn kho, quy tắc tài chính, sử dụng AI/bảo mật. Tệp Word lưu trong database, đã trích văn bản và lập chỉ mục nội bộ. Các tài liệu mới là quy tắc cấu hình cần chủ doanh nghiệp rà soát; không giả chữ ký phê duyệt. Các minh họa sản phẩm là SVG nội bộ.

Agent **Trợ lý GPT-6 Luna** được gắn 6 tài liệu, giữ phân quyền. Ngân sách của riêng Agent tăng từ 12.000 lên 50.000 token để phù hợp mức sử dụng của model; không thay hạn mức tài khoản. Tài khoản, mật khẩu, kết nối Gmail và khóa API được giữ nguyên.

## Kiểm tra và sao lưu

Bản sao trước nhập: `D:\captone 2\backups\apbwas-20261108-130117.dump`.

22 bài kiểm thử dữ liệu/AI đạt trước cập nhật bảo toàn tài liệu; sau cập nhật, 3 bài kiểm thử nhập dữ liệu đạt, gồm đối chiếu tồn kho, công thức tài chính, tính lặp an toàn và bảo toàn tệp nghỉ phép người dùng. Sáu tệp Word nguồn đã xuất bằng Word và kiểm tra bố cục một trang mỗi tệp; tài liệu nghỉ phép tạo sẵn không được nhập do đã có nguồn người dùng.

Kiểm tra database thực: 6 tài khoản, 1 kết nối Gmail, chuỗi audit hợp lệ và toàn bộ chuỗi tồn kho khớp. Web trả trạng thái sẵn sàng HTTP 200. Trình nhập chỉ chạy khi gọi rõ `python -m app.company_dataset_v2 --apply`, không tự chạy khi khởi động; lần gọi lại trả biên nhận hiện có và không nhân đôi dữ liệu.

Kiểm thử cuối: 35 bài về provider, câu trả lời doanh nghiệp và bộ dữ liệu đạt. Đã xử lý trường hợp provider đặt đoạn văn trong danh sách `steps` ở bước tổng hợp: chỉ chuyển danh sách chuỗi thành văn bản, không biến thành công cụ; vẫn kiểm chứng từng số liệu. Kế hoạch công cụ vẫn dùng schema nghiêm ngặt.

Lượt chạy thực `bee45ce1-2b3c-4b2d-9626-eac8cc855e5b` của Agent GPT-6 Luna hoàn tất, `business_analysis.status=completed`, trả lời: “Theo tài liệu Nghi Phep.docx, nhân viên được nghỉ phép 5 ngày trong một tháng.” Không dùng câu trả lời mẫu hoặc tự tạo chính sách thay tài liệu người dùng.
