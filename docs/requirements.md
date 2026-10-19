# Đối chiếu proposal FR01–FR20 / NFR01–NFR14

Nguồn: C2SE.06 ProposalDocument APBWAS ver1.1, mục 14, trang 30–32. Chữ “có mã” không đồng nghĩa đã xác minh Connected Mode. Tên test dưới đây là kiểm thử trong `backend/tests/test_security.py`, E2E trong `e2e/core.spec.ts`. Không sửa wording proposal để biến quyết định UI thành yêu cầu gốc.

| FR | Yêu cầu proposal | Màn hình / API / module | Bằng chứng và giới hạn |
|---|---|---|---|
| FR01 | Nhận business request bằng natural language web UI | AI Workspace; POST /workflows | E2E revenue/RAG/inventory/injection |
| FR02 | Decompose request thành plan nhiều bước | Plan panel, workflow graph; agent.make_plan; Plan schema | Demo planner + connected structured adapter; chưa gọi model thật |
| FR03 | Short-term conversational Agent Memory | History; conversations/context; Redis memory + persistent context | test_checkpoint_memory_redis_expiry_idempotency |
| FR04 | Traceable structured workflow result | Workflow detail, events, input/output/report links | test_report_exports_and_stream_replay; metadata list không trả raw outputs |
| FR05 | Chọn/execute approved tools theo task | Tool cards; tools.REGISTRY/run_tool | test_unregistered_sql_tool_never_executes; allowlist/policy validation |
| FR06 | Query/process PostgreSQL business data | Business tables, reports; SQLAlchemy products/sales/inventory | SQL code có; local tests dùng SQLite; PostgreSQL chưa chạy |
| FR07 | Authorized REST business operations | Approval detail; POST /approvals/:id/decision | revision/exactly-once/conflict/cancel tests |
| FR08 | Structured tables/summaries reports | Reports/list/detail; generate_business_report | SQL Numeric aggregate, real CSV/PDF export test |
| FR09 | Index PDF/DOCX/TXT pgvector | Knowledge upload/detail; document_chunks Vector(384); background index | Upload validation + indexing service; pgvector HNSW migration chưa chạy |
| FR10 | Semantic retrieval | Knowledge search; provider.embed; cosine Top-5 | Connected embedding code; demo lexical hashing không được coi là semantic |
| FR11 | Ground answer strictly in document context | Extractive answer + source/chunk links | test_rag_scope_before_retrieval_and_document_instructions; không tạo thêm luận điểm bằng LLM |
| FR12 | Guardrails inspect/block injection | Agent pre-plan gate; typed tools, no SQL/code/URL allowlist | 7 fixed injection cases + tool test; không tuyên bố an toàn mọi prompt |
| FR13 | Sensitive action HITL trigger | Approval center; propose_inventory_adjustment | Inventory remains unchanged until decision; Admin không bypass |
| FR14 | Approve/reject/modify pending action | Approval detail revision/history | Schema validates quantity; stale revision 409; conflict inventory version |
| FR15 | RBAC Admin/Manager/Employee | Role-aware shell; permissions.require; auth session | test_employee_blocked_at_api_and_tool; private conversation |
| FR16 | Tool/data visibility theo quyền | Document scopes, finance gating, API ownership | RAG scope test, cross-user isolation, output permission checks |
| FR17 | Audit request/plan/tool/approval/output | Activity table/detail; audit HMAC chain | test_quota_and_audit_redaction; tamper test; PostgreSQL trigger code |
| FR18 | Admin accounts/roles/tool permissions | Admin users, role matrix, tool registry | CRUD API; Argon2; own Admin lockout prevention; UI/API có mã |
| FR19 | Execution history/tool metrics/audit trails | Dashboard, Workflow detail, Audit, Monitoring | Derived SQL counts, tool latency, worker heartbeat; UI routes E2E |
| FR20 | Configure approval rules/rate limits/LLM quotas | Admin AI/approval settings | quota tests; expiry and approver roles; high-impact approval không thể tắt |

| NFR | Mục tiêu proposal | Trạng thái / cách đánh giá |
|---|---|---|
| NFR01 | Intuitive chat/command UI | UI desktop/mobile/dark/keyboard; E2E shell. Chưa nghiên cứu usability với người dùng |
| NFR02 | Stream đầu <3s; standard workflow <15s | Đo local trong evaluation.json; first byte tách first useful output. Không extrapolate provider/production |
| NFR03 | ≥80% predefined scenarios planned/executed correctly | E2E 4 kịch bản; chưa benchmark bộ nghiệp vụ lớn hoặc connected planner |
| NFR04 | ≥95% valid tool calls success | Test positive paths và checkpoint recovery. Chưa test thống kê quy mô lớn |
| NFR05 | DB read-only default; destructive SQL blocked; sensitive writes HITL | No raw SQL surface; PostgreSQL READ ONLY transaction/statement timeout; optional separate read role; controlled API write. PostgreSQL enforcement test đang skip vì engine lỗi |
| NFR06 | Modular extensible tool architecture | REGISTRY schema + run_tool handlers + service modules. Main API tập trung; thêm tool cần permission/schema/tests |
| NFR07 | Relevant Top-5 ≥80% eval queries | evaluation.json: fixed 3-query demo suite; không coi lexical demo là semantic quality benchmark |
| NFR08 | 10.000 chunks / Top-5 <3s | HNSW migration, permission/model filtering có mã. Chưa đo PostgreSQL 10.000 chunks |
| NFR09 | Block ≥90% fixed injection suite + prevent unauthorized tools | 7/7 fixed cases unit test; structural allowlist/RBAC/approval kiểm tra riêng. Chưa red-team rộng |
| NFR10 | 100% configured high-impact waits for approval | Inventory proposal/apply tests; revision, expiry, cancel, exactly-once. Concurrency PostgreSQL chưa xác minh |
| NFR11 | Privacy isolation, credentials encrypted | Password hash Argon2 theo yêu cầu bổ sung (không reversible encryption). HttpOnly cookie, origin validation, source permission filtering. Transport TLS cần deployment |
| NFR12 | 100% Agent/tool audit tamper-resistant | Transactional audit + HMAC/timestamp/advisory lock + append-only DB trigger. Chưa external anchor / chống superuser |
| NFR13 | Available scheduled demo/test periods | Local harness chạy và E2E; restart policy Docker có mã. Chưa soak/availability test |
| NFR14 | Configurable token/request throttling | Redis/DB rate, planner token quota/reservation, max_steps/deadline. Embedding accounting/cost quota chưa đầy đủ |

CSV/PDF, visual design, animation, strict revision binding, real upload bytes progress và screenshots là tiện ích/chi tiết triển khai bổ sung, không được trích thành FR mới từ proposal.
