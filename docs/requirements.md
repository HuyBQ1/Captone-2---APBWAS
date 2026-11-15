# Đối chiếu proposal FR01–FR20 / NFR01–NFR14

Nguồn: C2SE.06 ProposalDocument APBWAS ver1.1, mục 14, trang 30–32. Cập nhật kiểm chứng ngày 02/11/2026: 89 backend tests trên Linux/PostgreSQL và 15 Playwright tests. Test nằm trong `backend/tests/` và `e2e/`; kết quả/giới hạn chi tiết ở `verification.md`. Tài khoản doanh nghiệp, quản trị danh mục/bán hàng và lưu file gốc trong DB là phần mở rộng được người dùng yêu cầu, không gán thành yêu cầu mới của proposal.

| FR | Yêu cầu proposal | Màn hình / API / module | Bằng chứng và giới hạn |
|---|---|---|---|
| FR01 | Nhận business request bằng natural language web UI | AI Workspace; POST /workflows | E2E revenue/RAG/inventory/injection |
| FR02 | Decompose request thành plan nhiều bước | Plan panel, workflow graph; agent.make_plan; Plan schema | Demo regression; Intern AI gọi thật đã xác minh ngày 20/10/2026, không gọi lại trong đợt rà soát này |
| FR03 | Short-term conversational Agent Memory | History; conversations/context; Redis memory + persistent context | test_checkpoint_memory_redis_expiry_idempotency |
| FR04 | Traceable structured workflow result | Workflow detail, events, input/output/report links | test_report_exports_and_stream_replay; metadata list không trả raw outputs |
| FR05 | Chọn/execute approved tools theo task | Tool cards; tools.REGISTRY/run_tool | test_unregistered_sql_tool_never_executes; allowlist/policy validation |
| FR06 | Query/process PostgreSQL business data | Business tables, reports; SQLAlchemy products/sales/inventory | E2E PostgreSQL thật; tra giá/tồn kho theo SKU/tên, low-stock filter; READ ONLY/timeout integration |
| FR07 | Authorized REST business operations | Approval detail; POST /approvals/:id/decision | revision/exactly-once/conflict/cancel tests |
| FR08 | Structured tables/summaries reports | Reports/list/detail; generate_business_report | SQL Numeric aggregate, real CSV/PDF export test |
| FR09 | Index PDF/DOCX/TXT pgvector | Knowledge upload/detail; document_chunks Vector(384); background index | Upload/index tests + Docker worker E2E; migration/HNSW PostgreSQL đã qua |
| FR10 | Semantic retrieval | Knowledge search; provider.embed; cosine Top-5 | Connected embedding code; demo lexical hashing không được coi là semantic |
| FR11 | Ground answer strictly in document context | Extractive answer + source/chunk links | test_rag_scope_before_retrieval_and_document_instructions; không tạo thêm luận điểm bằng LLM |
| FR12 | Guardrails inspect/block injection | Agent pre-plan gate; typed tools, no SQL/code/URL allowlist | 7 fixed injection cases + tool test; không tuyên bố an toàn mọi prompt |
| FR13 | Sensitive action HITL trigger | Approval center; propose_inventory_adjustment | Inventory remains unchanged until decision; Admin không bypass |
| FR14 | Approve/reject/modify pending action | Approval detail revision/history | Schema validates quantity; stale revision 409; conflict inventory version |
| FR15 | RBAC Admin/Manager/Employee | Role-aware shell; permissions.require; auth session | test_employee_blocked_at_api_and_tool; private conversation |
| FR16 | Tool/data visibility theo quyền | Document scopes, finance gating, API ownership | Scope/cross-user tests; thu hồi quyền chặn conversation, replay, audit, nguồn đã xóa và giao diện đang mở |
| FR17 | Audit request/plan/tool/approval/output | Activity table/detail; audit HMAC chain | Redaction/tamper tests; PostgreSQL trigger chặn UPDATE/DELETE, nhiều writer event/audit không deadlock |
| FR18 | Admin accounts/roles/tool permissions | Admin users, role matrix, tool registry | CRUD API; Argon2; own Admin lockout prevention; UI/API có mã |
| FR19 | Execution history/tool metrics/audit trails | Dashboard, Workflow detail, Audit, Monitoring | Derived SQL counts, tool latency, worker heartbeat; UI routes E2E |
| FR20 | Configure approval rules/rate limits/LLM quotas | Admin AI/approval settings | quota tests; expiry and approver roles; high-impact approval không thể tắt |

| NFR | Mục tiêu proposal | Trạng thái / cách đánh giá |
|---|---|---|
| NFR01 | Intuitive chat/command UI | UI desktop/mobile/dark/keyboard; E2E shell. Chưa nghiên cứu usability với người dùng |
| NFR02 | Stream đầu <3s; standard workflow <15s | evaluation-postgres.json: 4 Demo workflows 0.533–1.051s; SSE first byte 4–6ms. Không suy ra Connected Mode/production |
| NFR03 | ≥80% predefined scenarios planned/executed correctly | E2E 4 kịch bản; chưa benchmark bộ nghiệp vụ lớn hoặc connected planner |
| NFR04 | ≥95% valid tool calls success | Test positive paths và checkpoint recovery. Chưa test thống kê quy mô lớn |
| NFR05 | DB read-only default; destructive SQL blocked; sensitive writes HITL | PostgreSQL test xác nhận READ ONLY, timeout 2500ms và INSERT bị chặn; allowlist/HITL; optional separate read role |
| NFR06 | Modular extensible tool architecture | REGISTRY schema + run_tool handlers + service modules. Main API tập trung; thêm tool cần permission/schema/tests |
| NFR07 | Relevant Top-5 ≥80% eval queries | evaluation.json: fixed 3-query demo suite; không coi lexical demo là semantic quality benchmark |
| NFR08 | 10.000 chunks / Top-5 <3s | PostgreSQL 16/pgvector 0.8.7: 10.000 vector tổng hợp, đúng 5 nguồn được phép, 17.54ms lần chốt. Benchmark lexical cục bộ, không phải chất lượng semantic hay load test |
| NFR09 | Block ≥90% fixed injection suite + prevent unauthorized tools | 7/7 fixed cases unit test; structural allowlist/RBAC/approval kiểm tra riêng. Chưa red-team rộng |
| NFR10 | 100% configured high-impact waits for approval | Inventory proposal/apply, revision/expiry/cancel; PostgreSQL hai người duyệt đồng thời chỉ áp dụng đúng một lần |
| NFR11 | Privacy isolation, credentials encrypted | Password hash Argon2 theo yêu cầu bổ sung (không reversible encryption). HttpOnly cookie, origin validation, source permission filtering. Transport TLS cần deployment |
| NFR12 | 100% Agent/tool audit tamper-resistant | Transactional audit + HMAC/timestamp/advisory lock + append-only DB trigger. Chưa external anchor / chống superuser |
| NFR13 | Available scheduled demo/test periods | Docker PostgreSQL/Redis/backend/worker/frontend chạy thật; readiness và E2E đạt. Chưa soak/availability production |
| NFR14 | Configurable token/request throttling | Redis/DB rate, planner token quota/reservation, max_steps/deadline. Embedding accounting/cost quota chưa đầy đủ |

CSV/PDF, visual design, animation, strict revision binding, real upload bytes progress và screenshots là tiện ích/chi tiết triển khai bổ sung, không được trích thành FR mới từ proposal.
