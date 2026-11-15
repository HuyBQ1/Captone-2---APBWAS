"""Author controlled company Word documents from a verified database snapshot."""
import json,re,unicodedata,hashlib,zipfile
from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/company-word'
DATE='03/11/2026'
# purpose, owner, scope, six operational stages, two controls, evidence.
SOPS={
'ORG-001':('Sổ tay cơ cấu và phối hợp vận hành','Ban điều hành','Các bộ phận kinh doanh, kho vận, tài chính, nhân sự và quản trị hệ thống.',
 'Thống nhất đầu mối xử lý và cách bàn giao công việc để yêu cầu không bị bỏ sót hoặc xử lý trùng.',[
 ('Tiếp nhận','Bộ phận đầu mối','Ghi nhu cầu, người yêu cầu, thời hạn và đầu ra cần bàn giao. Tạo mã hồ sơ để theo dõi.','Phiếu tiếp nhận có mã'),
 ('Phân công','Quản lý bộ phận','Xác định người chủ trì và bộ phận phối hợp. Làm rõ người có quyền quyết định với công việc vượt thẩm quyền.','Phân công được xác nhận'),
 ('Thống nhất','Người chủ trì','Xác nhận phạm vi và các điều kiện đầu vào với bộ phận nhận việc trước khi triển khai.','Phạm vi và mốc bàn giao'),
 ('Thực hiện','Người được giao','Cập nhật tiến độ, ghi nhận vướng mắc và lưu hồ sơ tại nơi được phân quyền.','Tiến độ có bằng chứng'),
 ('Bàn giao','Hai bên phối hợp','Đối chiếu đầu ra với yêu cầu. Chỉ đóng công việc khi bên nhận xác nhận tiếp nhận.','Xác nhận bàn giao'),
 ('Rà soát','Quản lý bộ phận','Tổng hợp việc chậm hạn hoặc phải làm lại; phân công biện pháp khắc phục và người theo dõi.','Danh sách hành động')],
 ['Yêu cầu thiếu đầu mối hoặc chưa rõ thẩm quyền phải được trả về để làm rõ trước khi thực hiện.','Không sử dụng tài khoản chung để xác nhận thay người chịu trách nhiệm.'],['Phiếu tiếp nhận và phân công','Biên bản bàn giao công việc']),
'SAL-001':('Quy trình tiếp nhận và ghi nhận bán hàng','Kinh doanh','Nhân viên tiếp nhận, người xác nhận giao dịch và kho vận.',
 'Ghi nhận đúng sản phẩm, số lượng và giá trị bán; bảo đảm giao dịch đã xác nhận được cập nhật tồn kho và đối soát.',[
 ('Tiếp nhận','Nhân viên kinh doanh','Xác định tên hàng, SKU, số lượng và yêu cầu của khách. Tra cứu đúng mã trước khi tư vấn.','Nhu cầu được xác nhận'),
 ('Kiểm tra','Kinh doanh và kho','Kiểm tra trạng thái kinh doanh, giá hiện hành và số tồn khả dụng. Chuyển thiếu hàng cho quản lý.','Kết quả kiểm tra tồn'),
 ('Xác nhận','Người có thẩm quyền','Đối chiếu số lượng, đơn giá và thành tiền. Chỉ ghi nhận khi các điều kiện đã được xác nhận.','Xác nhận giao dịch'),
 ('Ghi nhận','Người được cấp quyền','Thực hiện Ghi nhận bán hàng, kiểm tra lại thành tiền và xác nhận thao tác trừ tồn.','Mã giao dịch duy nhất'),
 ('Bàn giao','Kho vận','Chuẩn bị hàng theo hồ sơ đã xác nhận. Lưu bằng chứng bàn giao tại hệ thống vận hành được chỉ định.','Hồ sơ bàn giao hàng'),
 ('Đối soát','Kinh doanh và tài chính','Kiểm tra giao dịch bán, số tồn sau bán và lịch sử xuất. Theo dõi sai lệch đến khi được xử lý.','Kết quả đối soát')],
 ['Không ghi nhận bán vượt tồn hoặc dùng SKU thay thế khi chưa được xác nhận.','Khi mất kết nối, kiểm tra mã tham chiếu trước khi gửi lại để tránh ghi nhận hai lần.'],['Xác nhận giao dịch và mã tham chiếu','Hồ sơ bàn giao và đối soát']),
'SAL-002':('Quy trình báo giá và quản lý danh mục','Kinh doanh','Quản lý danh mục và người được giao lập báo giá.',
 'Bảo đảm báo giá có nguồn, đúng phiên bản và được kiểm tra trước khi gửi cho người nhận.',[
 ('Xác định','Nhân viên kinh doanh','Làm rõ SKU, số lượng, quy cách cần cung cấp và thời điểm khách cần phản hồi.','Yêu cầu báo giá'),
 ('Tra cứu','Người lập báo giá','Lấy giá niêm yết hiện hành và tình trạng kinh doanh của từng SKU. Không dùng giá nhớ từ trao đổi cũ.','Danh mục đã đối chiếu'),
 ('Lập dự thảo','Người lập báo giá','Ghi mã báo giá, đơn vị tiền, phạm vi cung cấp và các điều kiện còn cần xác nhận.','Báo giá dự thảo'),
 ('Kiểm tra','Quản lý kinh doanh','Kiểm tra đơn giá, số lượng và các điều kiện đặc biệt theo thẩm quyền đã được phân công.','Kết quả rà soát'),
 ('Phát hành','Người được giao','Gửi đúng bản được duyệt và lưu dấu vết phiên bản đã gửi cho người nhận.','Bản đã phát hành'),
 ('Cập nhật','Quản lý danh mục','Khi đổi giá hoặc ngừng kinh doanh, cập nhật danh mục có kiểm soát và thông báo cho người liên quan.','Lịch sử cập nhật')],
 ['Không áp dụng chiết khấu hoặc cam kết bảo hành ngoài chính sách đã được phê duyệt.','Giữ nguyên giá trị giao dịch lịch sử khi cập nhật giá niêm yết mới.'],['Hồ sơ báo giá và phê duyệt','Lịch sử sửa danh mục']),
'SAL-003':('Quy trình tiếp nhận đổi trả và khiếu nại','Chăm sóc khách hàng','Kinh doanh, kho vận, bộ phận kỹ thuật và người có thẩm quyền xử lý.',
 'Tiếp nhận có bằng chứng, xác minh đúng giao dịch và theo dõi phương án xử lý đến khi hoàn tất.',[
 ('Tiếp nhận','Chăm sóc khách hàng','Ghi mã giao dịch, SKU, số lượng, mô tả sự việc và thông tin liên hệ được phép sử dụng.','Mã hồ sơ khiếu nại'),
 ('Xác minh','Kinh doanh','Đối chiếu giao dịch và hồ sơ bàn giao. Thu thập ảnh hoặc thông tin liên quan khi cần.','Bộ bằng chứng'),
 ('Đánh giá','Kho và kỹ thuật','Kiểm tra tình trạng thực tế; tách riêng hàng chờ xử lý, không cộng vào tồn sẵn bán.','Kết quả kiểm tra'),
 ('Đề xuất','Quản lý phụ trách','Lập phương án trên cơ sở chính sách có hiệu lực và thẩm quyền đã được giao.','Phương án trình duyệt'),
 ('Thực hiện','Bộ phận được giao','Thông báo phương án được duyệt và triển khai theo hệ thống vận hành tương ứng.','Bằng chứng thực hiện'),
 ('Đóng hồ sơ','Chăm sóc khách hàng','Xác nhận kết quả với người yêu cầu, lưu hồ sơ và tổng hợp nguyên nhân cần khắc phục.','Xác nhận hoàn tất')],
 ['Không hứa hoàn tiền hoặc đổi hàng khi chưa có phê duyệt và chính sách làm căn cứ.','Không tạo giao dịch bán âm hoặc sửa doanh thu cũ để thay cho hồ sơ điều chỉnh hợp lệ.'],['Phiếu tiếp nhận và bằng chứng','Phương án và xác nhận xử lý']),
'WH-001':('Quy trình nhập kho và kiểm đếm hàng hóa','Kho vận','Nhân viên nhận hàng, người kiểm đếm và người phê duyệt điều chỉnh tồn.',
 'Kiểm soát việc nhận hàng và ghi nhận số lượng thực tế; chỉ đưa hàng đạt điều kiện vào số tồn được phép sử dụng.',[
 ('Chuẩn bị','Nhân viên nhận hàng','Nhận thông tin lô hàng dự kiến và hồ sơ bàn giao. Chuẩn bị khu vực kiểm đếm riêng.','Danh sách hàng dự kiến'),
 ('Đối chiếu','Người kiểm đếm','Đối chiếu SKU, số lượng và tình trạng bao bì với hồ sơ. Đếm lại khi có dấu hiệu chênh lệch.','Phiếu kiểm đếm'),
 ('Phân loại','Kho vận','Tách hàng đạt, hàng thiếu hồ sơ và hàng có bất thường. Ghi nhận bằng chứng, không nhập chung hàng chờ xử lý.','Kết quả phân loại'),
 ('Lập đề xuất','Người được phân quyền','Ghi số lượng thực tế sau kiểm đếm, mã hàng và lý do điều chỉnh; đính kèm hồ sơ làm căn cứ.','Đề xuất điều chỉnh tồn'),
 ('Phê duyệt','Người có thẩm quyền','Kiểm tra số trước và sau, bằng chứng và phiên bản tồn hiện hành trước khi quyết định.','Quyết định phê duyệt'),
 ('Đối soát','Kho vận','Kiểm tra tồn sau cập nhật và lịch sử biến động. Hoàn tất lưu hồ sơ lô hàng.','Xác nhận nhập kho')],
 ['Hàng chưa rõ chất lượng hoặc thiếu hồ sơ phải được cách ly và báo quản lý.','Nếu có phát sinh bán trong lúc kiểm đếm, cập nhật lại số liệu và trình phiên bản đề xuất mới.'],['Phiếu kiểm đếm và hồ sơ bàn giao','Đề xuất và quyết định nhập tồn']),
'WH-002':('Quy trình theo dõi tồn kho và bổ sung hàng','Kho vận','Quản lý kho, kinh doanh và người quyết định kế hoạch bổ sung.',
 'Phát hiện kịp thời hàng thiếu, xác định nhu cầu có căn cứ và theo dõi việc bổ sung đến khi nhập kho.',[
 ('Theo dõi','Nhân viên kho','Rà soát SKU có số lượng thấp hơn hoặc bằng ngưỡng cảnh báo. Ưu tiên hàng có số tồn bằng không.','Danh sách cần xử lý'),
 ('Đối chiếu','Kho và kinh doanh','Đối chiếu số tồn thực tế với nhu cầu đã xác nhận và lịch sử bán gần đây.','Căn cứ nhu cầu'),
 ('Đề xuất','Quản lý kho','Đề xuất lượng bổ sung, mức ưu tiên và thời điểm cần hàng; nêu rõ giả định còn thiếu.','Kế hoạch bổ sung'),
 ('Rà soát','Người có thẩm quyền','Kiểm tra khả năng đáp ứng, mức tồn mục tiêu và điều kiện cung cấp trước khi chấp thuận.','Kết quả phê duyệt'),
 ('Theo dõi','Người được giao','Cập nhật tình trạng cung cấp và thông báo khi có nguy cơ không đáp ứng mốc dự kiến.','Tiến độ bổ sung'),
 ('Hoàn tất','Kho vận','Thực hiện quy trình nhập kho khi hàng về và kiểm tra lại danh sách cảnh báo.','Kết quả nhập và tồn mới')],
 ['Không coi hàng đang dự kiến mua là hàng đã có sẵn trong kho.','Không tự suy luận thời gian giao của nhà cung cấp hoặc nhu cầu tương lai khi chưa có dữ liệu.'],['Danh sách cảnh báo và căn cứ nhu cầu','Kế hoạch bổ sung và hồ sơ nhập']),
'WH-003':('Quy trình kiểm kê và xử lý chênh lệch tồn kho','Kho vận','Người kiểm kê, người đối soát và người phê duyệt điều chỉnh.',
 'Xác minh số tồn tại cùng một mốc và xử lý chênh lệch có bằng chứng, không sửa số để che sai lệch.',[
 ('Chốt phạm vi','Quản lý kho','Xác định SKU, vị trí kiểm kê, mốc số liệu và người chịu trách nhiệm.','Kế hoạch kiểm kê'),
 ('Lấy số liệu','Người đối soát','Lưu số lượng hệ thống và các giao dịch có thể diễn ra trong thời gian kiểm kê.','Bản chụp số liệu'),
 ('Kiểm đếm','Nhóm kiểm kê','Đếm thực tế, ghi kết quả theo SKU; đếm lại độc lập khi có chênh lệch.','Phiếu kiểm kê'),
 ('Phân tích','Kho và bộ phận liên quan','Đối chiếu lịch sử nhập, xuất và bàn giao để xác định chênh lệch cần xử lý.','Biên bản chênh lệch'),
 ('Trình duyệt','Quản lý kho','Lập đề xuất điều chỉnh với lý do, bằng chứng và số tồn thực tế sau đối soát.','Đề xuất có căn cứ'),
 ('Đóng kỳ','Người đối soát','Kiểm tra số sau phê duyệt, lưu hồ sơ và phân công biện pháp phòng ngừa tái diễn.','Kết quả đóng kiểm kê')],
 ['Không so số hệ thống và số đếm tại hai mốc khác nhau mà chưa điều chỉnh phát sinh giữa kỳ.','Không xóa lịch sử hoặc thay chứng cứ để làm khớp kết quả.'],['Kế hoạch và phiếu kiểm kê','Biên bản chênh lệch và quyết định xử lý']),
'OPS-001':('Quy trình chuẩn bị và bàn giao hàng hóa','Vận hành','Kinh doanh, kho vận và đầu mối tiếp nhận bàn giao.',
 'Bảo đảm hàng chuẩn bị đúng yêu cầu đã xác nhận và việc bàn giao có dấu vết rõ ràng.',[
 ('Nhận yêu cầu','Kho vận','Nhận danh sách SKU và số lượng đã được xác nhận, cùng điều kiện bàn giao liên quan.','Yêu cầu chuẩn bị hàng'),
 ('Soạn hàng','Nhân viên kho','Lấy đúng SKU, kiểm tra tình trạng và tách riêng từng bộ bàn giao.','Danh sách đã soạn'),
 ('Kiểm tra','Người kiểm tra','Đối chiếu độc lập mã và số lượng trước khi đóng gói. Ghi nhận thiếu hoặc sai hàng.','Kết quả kiểm tra'),
 ('Đóng gói','Kho vận','Đóng gói phù hợp và gắn thông tin nhận diện cần thiết, bảo vệ dữ liệu của người nhận.','Kiện hàng có nhận diện'),
 ('Bàn giao','Người giao và nhận','Đối chiếu số kiện, số lượng và tình trạng; lưu xác nhận tại hệ thống được chỉ định.','Bằng chứng bàn giao'),
 ('Theo dõi','Đầu mối vận hành','Theo dõi ngoại lệ và chuyển thông tin xác nhận hoàn tất cho bộ phận liên quan.','Trạng thái được xác nhận')],
 ['Không tự thay SKU tương đương khi thiếu hàng.','Không coi việc đã ghi nhận bán hàng là bằng chứng đã giao đến người nhận.'],['Danh sách soạn và kiểm tra hàng','Bằng chứng bàn giao và xử lý ngoại lệ']),
'FIN-001':('Hướng dẫn lập và đọc báo cáo doanh thu','Tài chính','Người lập báo cáo và người được phân quyền xem số liệu kinh doanh.',
 'Thống nhất phạm vi số liệu, kỳ so sánh và cách trình bày để tránh diễn giải sai báo cáo.',[
 ('Chọn kỳ','Người lập báo cáo','Xác định kỳ tháng, múi giờ Việt Nam và mốc chốt dữ liệu cần sử dụng.','Phạm vi báo cáo'),
 ('Tổng hợp','Người lập báo cáo','Lấy tổng giá trị giao dịch đã ghi nhận trong kỳ và phân nhóm theo danh mục sản phẩm.','Bảng số liệu tổng hợp'),
 ('Kiểm tra','Người đối soát','Đối chiếu tổng chi tiết với tổng báo cáo; kiểm tra nguồn và các bản ghi ngoại lệ.','Kết quả đối soát'),
 ('Diễn giải','Người lập báo cáo','Ghi rõ kỳ chưa đủ tháng, cơ sở so sánh và các giới hạn của dữ liệu.','Thuyết minh số liệu'),
 ('Phát hành','Người có thẩm quyền','Rà soát nội dung, lưu phiên bản và cung cấp đúng phạm vi người được phép nhận.','Báo cáo có nhận diện'),
 ('Lưu trữ','Tài chính','Lưu bản phát hành và căn cứ; tạo báo cáo mới khi có dữ liệu bổ sung thay vì ghi đè bản cũ.','Hồ sơ phiên bản')],
 ['Giá trị bán hàng trong ứng dụng không tự đồng nghĩa với lợi nhuận, dòng tiền hoặc hóa đơn thuế.','Không xem tháng đang diễn ra và tháng trước đầy đủ là so sánh cùng số ngày.'],['Báo cáo và bảng đối soát','Thuyết minh phạm vi và phiên bản']),
'FIN-002':('Quy trình đối soát và chốt số liệu cuối kỳ','Tài chính','Tài chính, kinh doanh và kho vận theo phân công đối soát.',
 'Phát hiện sai lệch trước khi phát hành báo cáo và lưu đủ căn cứ cho việc rà soát lại.',[
 ('Chuẩn bị','Tài chính','Xác định kỳ, nguồn giao dịch và người tham gia đối soát.','Kế hoạch chốt số liệu'),
 ('Đối chiếu','Người đối soát','Đối chiếu tổng doanh thu, chi tiết theo danh mục, số lượng và mã giao dịch.','Bảng đối soát'),
 ('Rà ngoại lệ','Các bộ phận liên quan','Làm rõ giao dịch trùng, thiếu nguồn hoặc cần giải trình; ghi người xử lý từng trường hợp.','Danh sách ngoại lệ'),
 ('Xử lý','Người có thẩm quyền','Quyết định cách xử lý dựa trên hồ sơ; giữ nguyên lịch sử các bản ghi đã phát hành.','Quyết định có căn cứ'),
 ('Xác nhận','Tài chính và quản lý','Rà soát phần còn treo, nêu ảnh hưởng và xác nhận phạm vi số liệu đủ điều kiện phát hành.','Xác nhận chốt kỳ'),
 ('Phát hành','Tài chính','Lưu báo cáo mới, căn cứ và lịch sử sửa đổi; thông báo cho người nhận được phân quyền.','Bộ hồ sơ chốt kỳ')],
 ['Không bịa chứng từ hoặc người phê duyệt cho dữ liệu lịch sử thiếu thông tin.','Khi còn ngoại lệ chưa giải quyết, phải trình bày rõ thay vì âm thầm loại khỏi báo cáo.'],['Bảng đối soát và danh sách ngoại lệ','Xác nhận chốt kỳ và báo cáo phát hành']),
'HR-001':('Quy trình tiếp nhận nhân viên mới','Nhân sự','Nhân viên mới, quản lý trực tiếp và quản trị hệ thống.',
 'Bảo đảm người mới được hướng dẫn, có tài khoản đúng vai trò và biết đầu mối hỗ trợ trước khi làm việc.',[
 ('Chuẩn bị','Nhân sự','Xác nhận thông tin nhân viên, vị trí, phòng ban và quản lý trực tiếp theo hồ sơ đã được duyệt.','Danh sách tiếp nhận'),
 ('Đề nghị quyền','Quản lý trực tiếp','Xác định nhiệm vụ và quyền cần thiết, không cấp quyền rộng hơn nhu cầu công việc.','Đề nghị cấp quyền'),
 ('Cấp tài khoản','Quản trị hệ thống','Mời hoặc tạo tài khoản cá nhân, chuyển thông tin kích hoạt riêng cho đúng người nhận.','Tài khoản được cấp'),
 ('Thiết lập','Nhân viên mới','Đặt mật khẩu riêng, cập nhật hồ sơ và kiểm tra phiên đăng nhập trên thiết bị sử dụng.','Xác nhận thiết lập'),
 ('Hướng dẫn','Quản lý trực tiếp','Hướng dẫn công việc, quy trình liên quan, cách bàn giao và đầu mối hỗ trợ.','Danh sách đã hướng dẫn'),
 ('Xác nhận','Nhân sự và quản lý','Kiểm tra các đầu việc còn thiếu và thống nhất người theo dõi đến khi hoàn tất.','Biên bản hoàn tất tiếp nhận')],
 ['Không dùng tài khoản của người khác trong thời gian chờ cấp quyền.','Nhân viên tự nhập chức danh không làm thay đổi vai trò hoặc quyền truy cập.'],['Danh sách onboarding và cấp quyền','Xác nhận bàn giao hướng dẫn']),
'HR-002':('Quy trình đăng ký nghỉ và bàn giao công việc','Nhân sự','Nhân viên, quản lý trực tiếp và người nhận bàn giao.',
 'Phối hợp công việc trong thời gian vắng mặt và bảo đảm các nhiệm vụ đang xử lý có người tiếp nhận.',[
 ('Lập yêu cầu','Nhân viên','Ghi khoảng thời gian vắng mặt, công việc liên quan và người dự kiến nhận bàn giao.','Đề nghị nghỉ hoặc vắng mặt'),
 ('Kiểm tra','Quản lý trực tiếp','Đối chiếu kế hoạch công việc và bố trí người thay thế theo chính sách nhân sự có hiệu lực.','Phân công thay thế'),
 ('Xác nhận','Người có thẩm quyền','Quyết định theo thẩm quyền và thông báo rõ cho nhân viên cùng đầu mối liên quan.','Kết quả xử lý yêu cầu'),
 ('Bàn giao','Nhân viên và người nhận','Đối chiếu các báo cáo, hồ sơ và yêu cầu chờ xử lý; làm rõ thời hạn cần theo dõi.','Danh sách bàn giao'),
 ('Theo dõi','Người được giao','Cập nhật công việc phát sinh qua tài khoản riêng, báo quản lý khi vượt phạm vi được giao.','Tiến độ công việc'),
 ('Tiếp nhận lại','Nhân viên và quản lý','Đối chiếu việc đã xử lý, việc còn tồn và cập nhật lại đầu mối phụ trách.','Xác nhận tiếp nhận lại')],
 ['Không chuyển mật khẩu cá nhân cho người thay thế.','Quyền lợi và số ngày nghỉ thực hiện theo chính sách nhân sự chính thức, không suy từ tài liệu hướng dẫn này.'],['Đề nghị và quyết định liên quan','Danh sách bàn giao và tiếp nhận lại']),
'IT-001':('Quy định sử dụng tài khoản và bảo vệ dữ liệu','Công nghệ thông tin','Tất cả người sử dụng hệ thống và thiết bị làm việc.',
 'Giảm rủi ro truy cập trái phép, lộ thông tin và mất khả năng truy vết người thao tác.',[
 ('Nhận tài khoản','Người sử dụng','Xác minh thông tin được cấp thuộc về mình; sử dụng liên kết hoặc mật khẩu tạm theo hướng dẫn.','Xác nhận tiếp nhận'),
 ('Thiết lập','Người sử dụng','Đặt mật khẩu riêng trước khi làm việc, không chia sẻ với người khác hoặc lưu tại nơi công khai.','Tài khoản cá nhân'),
 ('Sử dụng','Người sử dụng','Truy cập đúng phạm vi công việc, kiểm tra tài liệu và người nhận trước khi chia sẻ.','Dấu vết sử dụng'),
 ('Kiểm tra phiên','Người sử dụng','Rà soát các thiết bị đăng nhập và kết thúc phiên không còn sử dụng.','Phiên đã được kiểm tra'),
 ('Báo sự cố','Người phát hiện','Báo quản trị viên khi có phiên lạ, mất thiết bị hoặc nghi ngờ lộ thông tin. Giữ bằng chứng liên quan.','Hồ sơ sự cố'),
 ('Khắc phục','Quản trị và người dùng','Khóa hoặc khôi phục tài khoản, đổi mật khẩu và xác nhận quyền truy cập sau xử lý.','Xác nhận khắc phục')],
 ['Không đưa mật khẩu, API key hoặc thông tin thanh toán nhạy cảm vào chat và tài liệu chia sẻ.','Không tự xóa lịch sử khi xử lý sự cố; việc rà soát phải giữ bằng chứng.'],['Đề nghị hỗ trợ và bằng chứng','Kết quả xử lý và xác nhận người dùng']),
'IT-002':('Quy trình cấp quyền và quản lý vòng đời tài khoản','Quản trị hệ thống','Quản trị viên và người phê duyệt quyền sử dụng.',
 'Cấp đúng quyền theo nhiệm vụ và thu hồi kịp thời khi nhiệm vụ hoặc trạng thái nhân sự thay đổi.',[
 ('Nhận đề nghị','Quản trị viên','Nhận thông tin người dùng, quản lý xác nhận và phạm vi công việc cần truy cập.','Đề nghị có người chịu trách nhiệm'),
 ('Rà soát quyền','Người phê duyệt','Kiểm tra vai trò và quyền bổ sung; áp dụng nguyên tắc quyền tối thiểu.','Quyền được chấp thuận'),
 ('Cấp tài khoản','Quản trị viên','Tạo tài khoản cá nhân hoặc lời mời và chuyển thông tin riêng cho đúng người nhận.','Tài khoản có vai trò'),
 ('Xác nhận','Người sử dụng','Thiết lập mật khẩu riêng, kiểm tra phạm vi truy cập và báo sai lệch.','Xác nhận sử dụng'),
 ('Thay đổi','Quản trị viên','Cập nhật vai trò hoặc khóa tài khoản theo yêu cầu hợp lệ; kiểm tra việc thu hồi phiên.','Lịch sử thay đổi'),
 ('Rà định kỳ','Quản lý và quản trị','Đối chiếu tài khoản đang hoạt động với nhu cầu thực tế, xử lý quyền không còn cần thiết.','Biên bản rà soát quyền')],
 ['Chưa cấu hình email tự động thì chuyển liên kết riêng; không thông báo hệ thống đã gửi thư.','Phải xác minh người nhận trước khi cấp liên kết khôi phục; liên kết mới thay thế liên kết chưa dùng trước đó.'],['Đề nghị cấp thay đổi thu hồi quyền','Biên bản rà soát và lịch sử xử lý']),
'IT-003':('Quy trình sao lưu và khôi phục dữ liệu','Quản trị hệ thống','Người được phân công vận hành và người phê duyệt khôi phục.',
 'Tạo bản sao có thể khôi phục và kiểm tra trước khi đưa dữ liệu khôi phục vào sử dụng.',[
 ('Lập kế hoạch','Người vận hành','Xác định phạm vi, nơi lưu và lịch sao lưu được phê duyệt; kiểm tra quyền truy cập kho lưu.','Kế hoạch sao lưu'),
 ('Sao lưu','Người vận hành','Tạo bản sao database theo công cụ được chỉ định, ghi mốc thời gian và kết quả thao tác.','Tệp sao lưu có nhận diện'),
 ('Kiểm tra','Người vận hành','Kiểm tra archive và khả năng đọc; theo dõi lỗi và xử lý bản sao không đạt.','Kết quả kiểm tra'),
 ('Khôi phục thử','Người được phân công','Khôi phục vào database riêng, không ghi đè môi trường đang sử dụng.','Môi trường kiểm tra'),
 ('Đối soát','Người kiểm tra','Kiểm tra schema, số bản ghi, file gốc và tính toàn vẹn audit với đúng khóa ký.','Biên bản đối soát'),
 ('Chuyển sử dụng','Người có thẩm quyền','Chỉ cho phép chuyển sau xác nhận; lưu kế hoạch quay lại và thông báo phạm vi ảnh hưởng.','Quyết định và nhật ký chuyển')],
 ['Giữ bí mật môi trường và khóa ký audit tại kho được kiểm soát, tách khỏi bản sao dữ liệu.','Không xóa volume của stack chính để cập nhật hoặc thử khôi phục.'],['Nhật ký sao lưu và kết quả kiểm tra','Biên bản khôi phục và đối soát']),
'DQ-001':('Quy định quản lý chất lượng dữ liệu nghiệp vụ','Quản trị dữ liệu','Người nhập dữ liệu, người đối soát và người phê duyệt báo cáo.',
 'Duy trì dữ liệu có nguồn và có thể đối chiếu giữa hàng hóa, giao dịch, tồn kho và báo cáo.',[
 ('Xác định nguồn','Người nhập dữ liệu','Ghi nguồn, mốc thời gian, chủ sở hữu và phạm vi được phép sử dụng.','Thông tin nguồn'),
 ('Kiểm tra mã','Người nhập dữ liệu','Kiểm tra SKU, khóa sản phẩm và mã tham chiếu giao dịch; không dùng tên gần giống để ghép tùy ý.','Dữ liệu nhận diện hợp lệ'),
 ('Đối soát','Người kiểm tra','Đối chiếu giá trị bán, số lượng và biến động tồn; phân loại bản ghi cần làm rõ.','Bảng kiểm chất lượng'),
 ('Xử lý lỗi','Bộ phận sở hữu','Làm rõ nguyên nhân và đề xuất sửa có dấu vết; không che ngoại lệ bằng cách xóa lịch sử.','Hồ sơ sửa dữ liệu'),
 ('Xác nhận','Người có thẩm quyền','Chấp thuận phạm vi dữ liệu đủ điều kiện và ghi rõ giới hạn còn lại.','Xác nhận sử dụng'),
 ('Theo dõi','Quản trị dữ liệu','Theo dõi lỗi tái diễn và cập nhật quy tắc kiểm tra phù hợp.','Danh sách cải tiến')],
 ['Phân biệt dữ liệu mẫu với dữ liệu kinh doanh thực tế; giữ nhãn nguồn khi xuất hoặc chia sẻ.','Phiên bản danh mục và phiên bản tồn kho là hai cơ chế kiểm soát khác nhau.'],['Thông tin nguồn và bảng đối soát','Hồ sơ sửa lỗi và xác nhận sử dụng']),
'AI-001':('Hướng dẫn sử dụng trợ lý nghiệp vụ có kiểm soát','Vận hành','Người sử dụng trợ lý và người quyết định các đề xuất nghiệp vụ.',
 'Sử dụng trợ lý để tra cứu và chuẩn bị công việc, đồng thời kiểm tra nguồn trước khi ra quyết định.',[
 ('Nêu yêu cầu','Người sử dụng','Ghi mục tiêu, SKU hoặc kỳ báo cáo rõ ràng; không đưa thông tin bí mật vào câu hỏi.','Yêu cầu có phạm vi'),
 ('Kiểm tra kế hoạch','Người sử dụng','Đọc các bước được đề xuất và phạm vi dữ liệu, làm rõ khi yêu cầu chưa đủ thông tin.','Kế hoạch được hiểu đúng'),
 ('Xem kết quả','Người sử dụng','Kiểm tra số liệu, đơn vị tiền, kỳ thời gian và các giới hạn được nêu.','Kết quả được kiểm tra'),
 ('Mở nguồn','Người sử dụng','Mở nguồn tài liệu hoặc giao dịch làm căn cứ; đối chiếu mã và phiên bản.','Nguồn đã đối chiếu'),
 ('Quyết định','Người có thẩm quyền','Rà soát độc lập các đề xuất thay đổi tồn kho trước khi phê duyệt.','Quyết định có trách nhiệm'),
 ('Theo dõi','Người sử dụng','Lưu mã workflow, báo nội dung chưa đúng và theo dõi việc xử lý ngoại lệ.','Hồ sơ theo dõi')],
 ['Giá và tồn hiện hành phải tra từ dữ liệu hàng hóa; tài liệu danh mục chỉ là snapshot.','Kết quả thiếu bằng chứng không được sử dụng để tự suy luận sự kiện hoặc bỏ qua quyền truy cập.'],['Yêu cầu kết quả và nguồn dẫn','Phê duyệt và hồ sơ phản hồi']),
'OPS-002':('Quy trình bàn giao và theo dõi thiết bị nội bộ','Vận hành','Người quản lý thiết bị, người nhận và quản lý trực tiếp.',
 'Theo dõi việc cấp, sử dụng và thu hồi thiết bị làm việc, phân biệt với hàng hóa dùng để bán.',[
 ('Đề nghị','Quản lý trực tiếp','Xác định nhu cầu, người sử dụng và thiết bị cần bàn giao theo nhiệm vụ.','Đề nghị cấp thiết bị'),
 ('Kiểm tra','Người quản lý thiết bị','Xác định nhận diện, phụ kiện và tình trạng; đối chiếu hồ sơ liên quan.','Danh sách thiết bị'),
 ('Phê duyệt','Người có thẩm quyền','Rà nhu cầu và điều kiện cấp trước khi giao cho người sử dụng.','Xác nhận cấp'),
 ('Bàn giao','Người giao và nhận','Kiểm tra thực tế, ghi tình trạng và trách nhiệm sử dụng theo biên bản.','Biên bản bàn giao'),
 ('Theo dõi','Người quản lý thiết bị','Theo dõi yêu cầu hỗ trợ và cập nhật thay đổi người sử dụng tại sổ tài sản được chỉ định.','Sổ theo dõi thiết bị'),
 ('Thu hồi','Người quản lý và nhân sự','Kiểm tra tình trạng và xác nhận thu hồi khi có thay đổi nhiệm vụ hoặc nghỉ việc.','Xác nhận thu hồi')],
 ['Không dùng giao dịch bán hàng giả để thay cho việc bàn giao tài sản nội bộ.','Không tự suy luận thời hạn bảo hành khi chưa có hồ sơ của thiết bị.'],['Đề nghị và biên bản bàn giao','Sổ theo dõi và xác nhận thu hồi']),
}

def para(doc,text,style=None):
    p=doc.add_paragraph(text,style);return p

def table(doc,headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for i,width in enumerate(widths):t.columns[i].width=Inches(width)
    for j,text in enumerate(headers):t.rows[0].cells[j].text=text
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells=t.add_row().cells
        for j,value in enumerate(row):cells[j].text=str(value)
    for i,row in enumerate(t.rows):
        trpr=row._tr.get_or_add_trPr();no_split=OxmlElement('w:cantSplit');trpr.append(no_split)
        for j,c in enumerate(row.cells):
            c.width=Inches(widths[j]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=c._tc.get_or_add_tcPr();shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'18324C' if i==0 else ('F3F5F7' if i%2==0 else 'FFFFFF'));tcpr.append(shade)
            borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'5');el.set(qn('w:color'),'D9D9D9');borders.append(el)
            tcpr.append(borders);margins=OxmlElement('w:tcMar')
            for edge in ['top','bottom','left','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'85');el.set(qn('w:type'),'dxa');margins.append(el)
            tcpr.append(margins)
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(2);p.paragraph_format.space_before=Pt(2);p.paragraph_format.line_spacing=1.05
                if j==0 and len(str(rows[0][0] if rows else ''))<4:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                if 'Đơn giá VND' in headers and j==2:p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
                if 'Tồn và ngưỡng' in headers and j==3:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:r.font.size=Pt(10.5);r.font.bold=i==0;r.font.color.rgb=RGBColor.from_string('FFFFFF' if i==0 else '000000')
    para(doc,'').paragraph_format.space_after=Pt(1)
    return t

def base(code,title,department,scope):
    d=Document();s=d.sections[0];s.page_width=Inches(8.5);s.page_height=Inches(11)
    for border in list(d.styles.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    s.top_margin=Inches(.65);s.bottom_margin=Inches(.65);s.left_margin=Inches(.8);s.right_margin=Inches(.8)
    s.header_distance=Inches(.25);s.footer_distance=Inches(.25)
    for name in ['Normal','Title','Subtitle','Heading 1','Heading 2']:
        style=d.styles[name];style.font.name='Arial';style.font.color.rgb=RGBColor(0,0,0)
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Arial')
    normal=d.styles['Normal'];normal.font.size=Pt(11);normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.12
    d.styles['Title'].font.size=Pt(20);d.styles['Title'].font.bold=True;d.styles['Title'].paragraph_format.space_after=Pt(12)
    for name,size in [('Heading 1',13),('Heading 2',11.5)]:
        d.styles[name].font.size=Pt(size);d.styles[name].font.bold=True;d.styles[name].paragraph_format.space_before=Pt(10);d.styles[name].paragraph_format.space_after=Pt(5)
    header=s.header.paragraphs[0];header.text='NOVA COMMERCE   |   HỆ THỐNG TÀI LIỆU NỘI BỘ';header.runs[0].font.size=Pt(8);header.runs[0].font.color.rgb=RGBColor(0,0,0)
    footer=s.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run(f'NC-{code}  |  1.1  |  Bản mẫu chờ phê duyệt  |  Trang ').font.size=Pt(8)
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    para(d,title,'Title')
    classification={'all':'Nội bộ','Manager':'Nội bộ quản lý','Admin':'Hạn chế quản trị'}[scope]
    para(d,f'Mã tài liệu  NC-{code}     Phiên bản  1.1     Ngày soạn  {DATE}')
    para(d,f'Đơn vị chủ trì  {department}     Phân loại  {classification}')
    para(d,'Trạng thái  Chờ rà soát và phê duyệt')
    d.core_properties.title=title;d.core_properties.author='Nova Commerce';d.core_properties.subject='Quy trình và hướng dẫn nội bộ';d.core_properties.keywords=f'NC-{code}, Nova Commerce, 1.1'
    return d

def signatures(d,department):
    d.add_heading('Xác nhận kiểm soát tài liệu',1)
    para(d,f'Soạn thảo  {department}     Họ tên và ký  ____________________')
    para(d,'Rà soát  Quản lý phụ trách     Họ tên và ký  ____________________')
    para(d,'Phê duyệt  Người được ủy quyền     Ngày và ký  ____________________')
    p=para(d,'Tài liệu chỉ có hiệu lực sau khi hoàn tất phê duyệt và thông báo ban hành.');p.runs[0].italic=True;p.runs[0].font.size=Pt(10)

def slug(text):
    text=text.replace('đ','d').replace('Đ','D')
    text=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().replace(' ','_')
    return re.sub(r'[^A-Za-z0-9_]','',text)[:70]

def build(source):
    OUT.mkdir(parents=True,exist_ok=True);manifest=[]
    for original in source['documents']:
        code=re.search(r'\[NC-([^\]]+)\]',original['name']).group(1)
        if code in SOPS:
            title,owner,scope,purpose,steps,controls,records=SOPS[code]
            d=base(code,title,owner,original['scope'])
            d.add_heading('1 Mục đích và phạm vi',1);para(d,purpose);para(d,'Đối tượng áp dụng  '+scope)
            d.add_heading('2 Trách nhiệm',1)
            table(d,['Vai trò','Trách nhiệm chính'],[
                ['Bộ phận chủ trì',f'{owner} tổ chức thực hiện, hướng dẫn và tổng hợp các vấn đề cần xử lý.'],
                ['Người thực hiện','Làm đúng phạm vi được giao, kiểm tra đầu vào và lưu đủ bằng chứng.'],
                ['Quản lý có thẩm quyền','Rà soát ngoại lệ, quyết định theo phân công và kiểm tra việc hoàn tất.']], [1.65,5.25])
            para(d,'Người nhận tài liệu phải kiểm tra mã và phiên bản trước khi sử dụng. Các bản in cần được đối chiếu với bản đang được quản lý trong Kho tri thức.')
            signatures(d,owner)
            d.add_page_break();d.add_heading('3 Quy trình thực hiện',1)
            table(d,['Bước','Chịu trách nhiệm','Công việc cần thực hiện','Đầu ra'],[[f'{i}\n{step[0]}',step[1],step[2],step[3]] for i,step in enumerate(steps,1)],[.85,1.25,3.4,1.4])
            d.add_heading('4 Ngoại lệ và điểm kiểm soát',1)
            for text in controls:para(d,text,'List Bullet')
            d.add_heading('5 Hồ sơ và tiêu chí hoàn tất',1)
            table(d,['Hồ sơ cần lưu','Đầu mối quản lý','Kiểm tra trước khi đóng'],[[record,owner,'Có mã nhận diện, người phụ trách, ngày xử lý và bằng chứng liên quan.'] for record in records],[2.45,1.5,2.95])
            para(d,'Chỉ đóng hồ sơ khi đầu ra đã được xác nhận, các ngoại lệ đã có người tiếp nhận và tài liệu được lưu đúng phạm vi quyền. Thời hạn lưu thực hiện theo lịch lưu trữ được doanh nghiệp phê duyệt.')
        elif code.startswith('CAT-'):
            old_title=original['name'].split('] ',1)[1].removesuffix('.txt')
            category=old_title.replace('Danh mục và hướng dẫn nhóm ','')
            title='Danh mục hàng hóa '+category.lower();d=base(code,title,'Quản trị danh mục',original['scope'])
            para(d,'Tài liệu phục vụ đối chiếu mã hàng và chuẩn bị báo giá. Giá và số tồn là snapshot tại thời điểm lập; trước khi xác nhận giao dịch phải kiểm tra lại dữ liệu hiện hành.')
            d.add_heading('1 Danh mục theo nhóm hàng',1)
            products=[p for p in source['products'] if p['category']==category]
            rows=[[p['sku'],p['name'],f"{p['price']:,}".replace(',','.'),f"{p['quantity']} / {p['threshold']}"] for p in products]
            table(d,['Mã SKU','Tên hàng hóa','Đơn giá VND','Tồn và ngưỡng'],rows,[1.1,3.2,1.3,1.3])
            d.add_heading('2 Hướng dẫn đối chiếu',1)
            for text in ['Đối chiếu SKU và tên hàng; không thay mã tương đương khi chưa xác nhận với người có thẩm quyền.','Số tồn nhỏ hơn hoặc bằng ngưỡng là cảnh báo bổ sung; số bằng không không đủ điều kiện ghi nhận bán.','Thông số kỹ thuật, điều kiện cung cấp và bảo hành phải được xác minh từ hồ sơ sản phẩm hoặc báo giá đã duyệt.','Không suy ngược giá trị giao dịch cũ từ giá niêm yết hiện tại; số liệu bán đã ghi nhận được quản lý riêng.']:
                para(d,text,'List Bullet')
            para(d,'Nguồn đối chiếu  Danh mục và tồn kho Nova Commerce, snapshot ngày '+DATE+'. Bộ dữ liệu NCV1 phục vụ mô phỏng nghiệp vụ; không phải báo giá đã phát hành cho khách hàng.')
            signatures(d,'Quản trị danh mục')
        else:raise ValueError('Unexpected source document '+code)
        path=OUT/f'NC-{code}_{slug(title)}_v1.1.docx';d.save(path)
        manifest.append({'id':original['id'],'code':'NC-'+code,'title':title,'scope':original['scope'],'file':path.name,'source_sha256':original['sha256'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'documents':len(manifest),'output':str(OUT)}))

if __name__=='__main__':build(json.loads((ROOT/'.test-tmp/word-source.json').read_text(encoding='utf-8')))
