# APBWAS upgrade analysis and implementation checklist

## Scope and current architecture

The supplied master prompt asks for repository analysis followed by **Phase 1: Agent Builder and Agent Version Control**. Phases 2–6 are a roadmap, not completed features in this delivery. This extends the existing application.

React uses `main.tsx` for cookie authentication, RBAC navigation and routing; `ui.tsx` for shared forms/modals/states; `workspace.tsx` for chat and workflow streaming; `pages.tsx` for workflow execution views. Tailwind/custom CSS and React Query are established. React Flow is installed for run visualization, not yet a graph editor.

FastAPI `main.py` owns authentication, workflow enqueue/retry/cancel/SSE and business APIs; `enterprise.py` owns accounts and business writes. `agent.py` plans requests; `provider.py` calls the configured backend LLM endpoint. `tools.py` is the allowlist/execution boundary. `workflows.py` persists plans, checkpoints, steps, events, usage and audit. `worker.py` leases durable PostgreSQL jobs and resumes expired leases. Redis currently supplies rate counters and conversation cache; **the existing durable job queue is SQL-backed**, not a Redis task framework.

`retrieval.py` extracts PDF/DOCX/TXT, chunks, embeds and searches pgvector with current role scopes and HNSW/exact fallback. Main installation uses explicitly labeled lexical embeddings, not production semantic embeddings. Original documents and product images are database blobs. `auth.py`, `permissions.py`, guardrails, `approvals.py` and HMAC audit are reusable security boundaries. `compose.yaml` runs PostgreSQL/Redis/init/API/worker/nginx; `compose.test.yaml` is isolated and uses deterministic provider mode. Existing schema is migration 0005. Business/finance/sample data, historical workflows and credentials must be preserved.

## Reusable features and missing components

Reuse the current planner, tool executor, jobs, SSE, audit, quota reservation, HITL and report generation. Phase 1 is missing Agent/config/tool/knowledge records, published snapshots, draft revisions, ownership boundaries, per-Agent limits, a configuration-aware runtime adapter and Agent-specific UI/history.

Later phases still need graph definitions/versions/node scheduling, workforce orchestration, cron/webhook management, OAuth/encrypted integrations, marketplace sanitization, public widget restrictions and evaluation datasets/runners. Existing `workflows` already means execution records: Phase 2 must extend or introduce clearly named definition tables, not replace that contract or install a second Agent runtime.

## Database and isolation

Migration 0006 is additive: `workspaces`, `agents`, `agent_configs`, `agent_tools`, `agent_knowledge`, `agent_versions`, `agent_draft_revisions`; workspace ownership for users/documents; nullable Agent/version/config snapshot references on existing workflow runs. Existing records map to the primary company workspace. New Agent APIs derive workspace from authenticated user records, never a client-supplied workspace header. Private Agents are owner-only; same-workspace administrators can manage them; workspace-published Agents are executable by permitted members. Agent versions and saved draft revisions are immutable, restored into a new draft, and every run pins a snapshot.

This is ownership infrastructure for **new Agent features**, not a claim that legacy global business/account endpoints have become a complete multi-tenant SaaS. Until business tables are tenant-scoped, Agents outside the primary workspace cannot use global business tools. Knowledge must match both workspace and current document scope. Deletion is soft deletion retaining versions and execution references; no data-dropping migration is needed. A downgrade may remove only unused additive structures; it must refuse when Agent data/runs exist.

## File-by-file implementation plan

| File | Planned change |
|---|---|
| `backend/app/models.py` | Add Workspace, Agent/config/tool/knowledge/version models and run pins; JSONB on PostgreSQL, JSON on SQLite. |
| `backend/migrations/versions/0006_agents.py` | Add ownership and Agent tables; seed primary workspace; extend existing roles without resetting customized permissions; immutable version protection; guarded downgrade. |
| `backend/app/agent_management.py` | Validated config models, ownership service, CRUD/duplicate/archive/delete, immutable publication, diff/restore, capability catalog, test/published execution APIs. |
| `backend/app/agent_runtime.py` | Validate pinned snapshot, current RBAC/tools/knowledge, per-Agent bounds and invocation policy; adapt the existing planner/executor. |
| `backend/app/agent.py` | Accept optional Agent configuration while preserving the existing request path and deterministic financial route. |
| `backend/app/provider.py` | Apply configured model/temperature/output limits/instructions; retain backend-only credentials, fixed provider base URL and JSON plan validation. |
| `backend/app/workflows.py` | Apply pinned config at planning and before each step; enforce Agent limits, current permissions and knowledge restrictions. |
| `backend/app/tools.py`, `retrieval.py`, `approvals.py` | Enforce Agent tool/document allowlist and recheck approval authorization without bypassing HITL. |
| `backend/app/main.py` | Register Agent router; scope new Agent run access/list/history; redact snapshots in general run serialization; preserve old APIs. |
| `backend/app/permissions.py`, `seed.py`, `enterprise.py`, `provision_company.py` | Add Agent permissions and keep ownership consistent when creating users/documents. |
| `src/agents.tsx` | Agent list/editor, tool and knowledge panels, draft save, publish, archive/delete/duplicate, version comparison/restore and Playground with real job status/history. |
| `src/main.tsx`, `src/style.css` | Add RBAC navigation/routes and reuse the current responsive design system. |
| `backend/tests/test_agents.py`, `test_provider.py`, `test_postgres.py`, `conftest.py` | Config validation, ownership/cross-workspace, immutable publication, stale edits, runtime pins/RBAC revocation, tools/RAG/HITL and migration compatibility. |
| `e2e/agents.spec.ts` | Create/save/publish/run, restore into draft, old-version run remains pinned, duplicate/archive/delete, responsive controls. |
| `docs/agent-builder.md` | API/architecture/migration/security details, commands, measured results and remaining limitations. |

## API and frontend plan

New `/api/agents` APIs: list/create; capabilities; get/update/delete; duplicate; archive; publish; versions/list/detail/compare/restore; draft Playground run; published version run; execution history. All authenticated and permission checked. Existing `/api/workflows/:id` and `/events` provide actual execution detail/streaming.

Frontend routes: `/agents`, `/agents/new`, `/agents/:id/edit`, `/agents/:id/playground`, `/agents/:id/versions`. Editor separates identity/instructions, model/limits, tool permissions and knowledge. Playground clearly distinguishes draft test from published execution, records version/revision and links to the existing workflow detail.

## Dependencies and security risks

Ownership/models → migration → CRUD/config validation → immutable publish/restore → pinned runtime → Playground/UI → integration/security/E2E tests. No new LLM SDK or external service is necessary.

Risks: privilege escalation through tool configuration, stale roles, cross-workspace document IDs, prompt instructions overriding guardrails, plaintext secrets embedded in config, provider URL manipulation, mutable versions changing queued behavior, snapshot disclosure through general run lists, and sensitive tools bypassing approval. Mitigations belong in the backend at save/publish/enqueue and each runtime step. Model names come from a server allowlist; no per-Agent API keys/base URLs. Plaintext credential patterns are rejected. Snapshots cannot grant permissions beyond the executor's current role. No live external model tests without appropriate authorization; deterministic tests and provider transport tests are reported separately.

## Checklist

- [x] Inspect actual repository architecture and reusable boundaries.
- [x] Record gaps, migration/API/UI dependencies, risks and implementation order.
- [x] Add ownership/models and compatible migration.
- [x] Implement Agent drafts, publication, immutable versions, comparison and restore.
- [x] Integrate pinned execution with existing runtime, queue, RAG and approval.
- [x] Build list/editor/Playground/version UI.
- [x] Run unit/API/migration/security/E2E tests and existing regressions.
- [x] Back up, deploy additive change, verify main app and document limitations.

Delivery and measured evidence: [Phase 1 report](agent-builder.md).
