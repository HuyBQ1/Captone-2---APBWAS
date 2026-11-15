# Phase 1 delivery — AI Agent Builder and Version Control

## 1. Architecture changes

The existing FastAPI/SQLAlchemy application, cookie authentication, RBAC, planner, tool executor, SQL job worker, workflow checkpoints, SSE events, audit and HITL remain the execution path. Agent Builder adds configuration/ownership and a runtime adapter; it does not install a second Agent execution engine. Every Agent run is an ordinary existing `Workflow` plus `Job`, with nullable Agent/version references and a complete configuration snapshot pinned at enqueue time.

`workspaces` and authenticated `users.workspace_id` anchor ownership for new Agent APIs. The existing company maps to `primary`. Agent knowledge is an explicit subset of existing indexed documents, checked against document workspace and role scope. Primary-workspace Agents may use the existing business tools. Other workspaces may use only their attached knowledge until business sources are properly tenant-scoped.

## 2. Files created

- `backend/app/agent_management.py`: validated DTOs, ownership service, capabilities, CRUD, publish, duplicate, archive/unarchive, soft delete, version/draft history, comparison/restore, Playground, published execution and run history.
- `backend/app/agent_runtime.py`: pinned snapshot verification, current permissions, Agent tool allowlist, document revalidation and run visibility.
- `backend/app/seed_agents.py`: optional idempotent creation of usable, published finance/inventory/knowledge Agents; no external AI calls.
- `backend/migrations/versions/0006_agents.py`: additive migration, default ownership, permissions and PostgreSQL immutability triggers.
- `src/agents.tsx`: Agent list/editor, Playground and version/draft history pages.
- `backend/tests/test_agents.py`, `e2e/agents.spec.ts`: API/security/runtime and browser scenarios.
- `docs/agent-upgrade-plan.md`: repository analysis and file-by-file implementation plan.

## 3. Files modified

`models.py`, `permissions.py`, `config.py`, `seed.py`, `enterprise.py`, `main.py`, `agent.py`, `provider.py`, `workflows.py`, `tools.py`, `retrieval.py`, `approvals.py`; `src/main.tsx`, `src/style.css`; `.env.example`; shared test fixtures, provider tests and PostgreSQL tests. Changes preserve existing API inputs; the new Agent APIs are separate, with additive ownership/run metadata on existing records.

## 4. Migration and storage

Migration **0006** adds `workspaces`, `agents`, `agent_configs`, `agent_tools`, `agent_knowledge`, `agent_versions`, and `agent_draft_revisions`. Configuration snapshots use JSONB on PostgreSQL and JSON in SQLite tests. Indexed foreign keys link company/workspace, owner, document, author and workflow. Current draft configuration is stored in `agent_configs`, while every saved revision is retained separately. Published versions and saved draft revisions are protected by PostgreSQL triggers against UPDATE/DELETE.

Existing users/documents are assigned `primary`; existing workflow Agent fields remain NULL. Roles gain `agents.run`; Admin/Manager also gain `agents.manage`, preserving their existing permission assignments. Published snapshots contain identity, visibility, instructions, model, generation bounds, tool list, permissions and knowledge IDs. Restoring creates a new saved draft; it does not mutate published versions or historical runs.

Deletion is soft deletion, preserving referenced versions and history. The downgrade refuses when Agents exist. An unused downgrade removes new Agent structures, retaining ownership/permission infrastructure that could have acquired references; re-upgrade is tested. No business data is dropped. Backups were taken before and after deployment.

## 5. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET / POST | `/api/agents` | Scoped list/search/status/page and create draft |
| GET | `/api/agents/capabilities` | Server-approved models, tools, permissions and accessible indexed knowledge |
| GET / PUT / DELETE | `/api/agents/{id}` | Detail, optimistic draft update, soft deletion |
| POST | `/api/agents/{id}/duplicate` | Private draft copy, no published history copied |
| POST | `/api/agents/{id}/archive`, `/unarchive` | Pause/restore Agent availability |
| POST | `/api/agents/{id}/publish` | Publish immutable snapshot with draft revision precondition |
| GET | `/api/agents/{id}/versions` | Published configuration snapshots and saved draft revision history |
| GET | `/api/agents/{id}/versions/{number}/compare` | Compare published configuration with current draft |
| POST | `/api/agents/{id}/versions/{number}/restore` | Restore published configuration into a new draft |
| POST | `/api/agents/{id}/drafts/{revision}/restore` | Restore an earlier saved draft into a new draft |
| POST | `/api/agents/{id}/playground` | Queue a pinned draft test; requires current draft revision |
| GET / POST | `/api/agents/{id}/runs` | Scoped execution history / queue a specific published version |

Run requests require `request` and `idempotency_key`; published execution accepts a version number and defaults to the currently published version. Existing `/api/workflows/{id}`, `/events`, `/cancel`, `/retry` and approval routes provide real execution details, streaming, cancellation, retries and HITL. General run/list serialization does not expose private Agent snapshots.

## 6. Frontend

Routes are `/agents`, `/agents/new`, `/agents/:id/edit`, `/agents/:id/playground`, `/agents/:id/versions`. Navigation follows current permissions. Forms reuse React Query, current buttons/modals/loading/error/toast components and CSS. Editor exposes identity/avatar, visibility, instructions, model, temperature, output tokens, execution steps, token budget, tools, permission ceiling and indexed documents. Unsaved edits cannot be published. Version pages show saved draft and publication histories, configuration differences, full published snapshots and restore confirmation.

Playground distinguishes saved draft testing from published execution, polls existing run state, renders Markdown output, shows token usage, links to existing node/tool input-output/events and approval detail, and shows execution history. Layout was checked on desktop and 390px mobile screens.

## 7. Business/runtime logic

- Draft updates use an optimistic revision; concurrent publication locks the Agent row and does not duplicate a version.
- Enqueue validates current roles, model allowlist, selected tools, knowledge scopes and idempotency before adding an existing SQL job.
- The runtime uses the pinned snapshot, not the latest draft, and caps execution steps by both Agent and system limits. Tokens consumed during planning are recorded even if the Agent budget subsequently blocks tool execution.
- A tool must satisfy system registration/toggle, Agent selection, configured permission ceiling and the executor's current permission. Revocation is checked at planning and tool execution. Sensitive inventory changes still pause for human approval and recheck Agent/workspace authorization before applying.
- RAG searches only attached document IDs and current role/workspace scopes; empty attachments return no sources without an embedding call. Archived/deleted/inaccessible attachments fail closed. Historical source access is rechecked.
- Configured model, temperature, output limit and instructions feed the existing provider planner. Backend base URL and credentials remain server-owned. Finance shortcuts remain deterministic SQL and do not require an external planner call.
- Publishing/archiving does not rewrite old versions. Archiving/deleting stops new executions and causes resumed steps to fail safely if the Agent is no longer available.

## 8. Security

New APIs derive workspace from the authenticated user, with private ownership or published workspace visibility. Cross-workspace Agent IDs, run access, knowledge attachments and approvals are denied. Current permissions remain authoritative, including after enqueue. A user cannot configure elevated permissions, direct execution of the approval-apply tool, arbitrary provider URLs or per-Agent API credentials. Credential patterns in instructions are rejected; no credentials are sent to React.

Private snapshots are not returned by generic workflow lists or Agent history. Snapshot/version IDs provide traceability; the full configuration is accessible through management-protected version APIs. Existing quota reservation, rate counters, durable job leases, guardrails, deadline handling and audit remain enabled.

## 9. Tests

**115 backend tests passed** on isolated Linux/PostgreSQL, **19 Playwright tests passed**, and production build passed. New cases include Agent CRUD, validation/elevation, ownership and cross-workspace access, workspace-public execution with the executor's permissions, draft pinning, immutable versions, comparison/restore, saved draft history, tool/RAG restrictions, role revocation, HITL/archive revalidation, idempotent enqueue, token budget accounting and usable example seeding.

PostgreSQL tests verify immutable version triggers, concurrent publication producing one version, migration from an old schema preserving users, repeatable upgrade and unused downgrade/re-upgrade. Provider transport tests verify selected model/temperature/output limit/instructions and backend-only credentials; these are controlled transport tests, not live provider calls. Existing authentication, business data, inventory, finance, reports, RAG, audit and browser regressions also passed.

Evidence: `.test-tmp/agents-backend.log`, `.test-tmp/agents-e2e.log`; desktop/mobile screenshots in `.test-tmp/agent-*.png`. Normal chart bundle-size and dependency deprecation warnings remain; they did not fail the build/tests.

## 10. Commands

```powershell
docker compose up -d --build
docker compose exec -T backend python -m app.seed_agents
npm run build
docker compose -f compose.test.yaml up -d --build
docker compose -f compose.test.yaml exec -T -e PG_TEST_DATABASE_URL=postgresql+psycopg://apbwas_test:local-test-only@postgres:5432/apbwas_test backend pytest tests -q
$env:E2E_URL='http://localhost:4181'; npm run test:e2e
docker compose -f compose.test.yaml down --volumes
```

`AGENT_MODELS` optionally lists additional model IDs approved for the same backend provider/credentials; the configured `AI_MODEL` is always present. Do not insert keys into Agent instructions. The test compose command uses only isolated databases; do not use `down --volumes` on the main stack.

## 11. Main deployment verification

Main readiness reports database/Redis healthy; schema is 0006. Counts remain **6 users, 3.552 sales, 56 products, 56 images and 55 document records**; HMAC audit is valid. Three real published Agent configurations and their first saved draft revisions were created: **Phân tích tài chính**, **Tra cứu tồn kho**, **Trợ lý tri thức**.

A Finance Agent v1 run was queued and processed by the main worker, completed with pinned version ID and the expected July sample operating profit **516.502.000 VND**, with zero planner tokens and no external AI call. This validates the existing queue/runtime integration on the deployed app. It does not claim a fresh live LLM-provider round trip for this upgrade.

## 12. Remaining scope and limitations

Phases 2–6 (visual graph editor, workforce, schedules/webhooks, integrations/OAuth, marketplace, embeds and evaluation runner) are **not implemented by Phase 1**. The existing business/auth application remains a single-company installation; new Agent ownership does not make all legacy global endpoints a fully tenant-isolated SaaS. Business tools outside the primary workspace are denied accordingly.

The durable queue remains SQL-backed with Redis caching/rate coordination; no Redis task framework was added. Agent instructions configure planning, while tool-result answers follow the existing runtime. Playground performs real authorized tool operations and is not a data-write sandbox. Current lists bound configuration attachments/history to 100 items and run history is paged. Broader performance/load benchmarking, multi-provider accounts, cross-workspace administration and external OAuth are future work. Model choices beyond the configured provider allowlist require backend setup and live verification. No changes from this phase were pushed to GitHub.
