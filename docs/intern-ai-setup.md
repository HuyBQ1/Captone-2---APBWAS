# Intern AI / DeepSeek — xác minh 20/10/2026

Backend được cấu hình provider `openai_compatible`, endpoint `https://discovery-api.intern-ai.org.cn/v1`, model `deepseek-v4-flash-vision`. API key chỉ nằm trong `.env` bị Git/Docker build context bỏ qua. Tên model được giữ đúng theo tài khoản người dùng; endpoint `/models` trả 200 và có model này.

Đã gọi một kế hoạch mẫu trực tiếp, validate Pydantic thành công. Sau khi người dùng cho phép thử workflow, kiểm tra đầy đủ qua http://localhost:4180: Manager → request kiểm tra sản phẩm sắp hết hàng → Intern AI lập kế hoạch thật → backend thực thi `get_inventory_status` → completed. Đợt đo ghi nhận 1322 token, khoảng 5.08 giây; metadata không có secret nằm trong `intern-ai-verification.json`.

Dữ liệu doanh nghiệp vẫn là bộ seed mẫu (`SAMPLE_DATA=true`); giao diện hiển thị riêng trạng thái AI thật và dữ liệu mẫu. Endpoint đã liệt kê chỉ các model generation, chưa cấu hình embedding model riêng. Chọn rõ `EMBEDDING_PROVIDER=lexical` để dùng các chunk mẫu hiện có, model_id `demo-hash-v1-384`; đây không phải semantic retrieval và không có fallback embedding âm thầm. Có thể cấu hình OpenAI/Gemini embedding riêng rồi re-index.

Frontend build và Docker build thành công. Backend: 39 passed, 2 PostgreSQL-only tests skipped trên cả Windows và Linux container. Các test mới kiểm tra đúng endpoint/model, secret chỉ ở Authorization header, không có key trong metadata hoặc payload prompt, che lỗi upstream, không tự fallback sang provider khác, HTTPS URL validation và RBAC vẫn chặn model đề nghị vượt quyền.

Tích hợp hiện dùng đầu vào văn bản để lập kế hoạch; tên model có vision không có nghĩa UI đã triển khai upload ảnh cho chat. Không chạy benchmark throughput/chi phí hoặc đánh giá toàn bộ chất lượng model từ một workflow này. Key đã từng xuất hiện trong hội thoại nên cần người sở hữu thu hồi/thay key trên nhà cung cấp; mã nguồn không lưu key.
