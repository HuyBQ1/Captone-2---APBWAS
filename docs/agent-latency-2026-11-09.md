# Agent latency review

Updated 2026-11-09 (Asia/Ho_Chi_Minh).

## Changes

- Compact planner JSON and schema annotations while retaining constraints, references, and all argument properties.
- Send tool labels/descriptions to the planner; backend permissions and risk controls remain authoritative.
- Ask the planner to omit null/unused arguments and use short step labels.
- Bound the four-paragraph synthesis response to 1,200 output tokens (or the lower Agent allowance). Planner limits for custom document content are unchanged.
- Emit `business.analysis.started` before synthesis, with a commit, so future event histories distinguish analysis latency from tool execution.

No model, credential, quota, timeout or authorization changes. Connected Mode still calls the selected LLM and validates its tool plan and grounded answer. No cached or hardcoded answers introduced.

## Verification

56 tests passed across provider, business AI, connected routing, file follow-up and workflow graph suites in a network-disabled container with an isolated SQLite database.

Planner schema shrank from 2,570 to 1,938 characters (24.6%). This is schema size, not an end-to-end speedup measurement.

One live generic greeting to the configured `deepseek-v4-flash-vision` model took 16.65 seconds, reported 2,120 tokens and returned a conversational answer without tools. No business data was sent in that test. This single request is not a controlled before/after benchmark.

Historical workflow `55f4c792-4ddf-43cc-be81-48c1c773b377`: planning about 18.02 s, tool execution about 0.05 s, post-tool processing/analysis about 9.80 s. Another run waited about 50.42 s between enqueue and planning; the single worker can add queue wait behind long-running work. No extra concurrent model calls were enabled because the provider has also returned HTTP 429.

Backend/worker rebuilt and restarted. Backend readiness returned HTTP 200; frontend was started again on port 4180.
