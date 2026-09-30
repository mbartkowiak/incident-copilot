# 0004: Triage agent design

**Status:** Accepted, 2026-09-29

## Context
Phase 4 adds a Claude agent that investigates a new ticket and drafts a resolution. It runs on a public demo URL, calls paid APIs, and its output is shown to a person who may act on it.

## Decision

**Cheap path first, agent on demand.** Submitting a ticket runs the routing model and vector search: instant and effectively free. The agent only runs when the dispatcher clicks "Draft with AI".

**Read-only tools over existing services.** `predict_team`, `search_similar_incidents`, `search_knowledge_base` and `check_recent_activity` wrap services that already have tests. All tools use `strict: true` schemas. `check_recent_activity` takes enum-restricted inputs that feed a fixed, parameterized SQL template; the model never writes SQL. The agent has no write tools at all.

**A human approves.** The agent returns a structured draft (`output_config.format` JSON schema): team, priority, cause, steps, citations, clarifying questions, spike note. The dispatcher edits and approves or rejects it. Only that human decision is written, to `triage_feedback`, the one table the API's service principal may modify.

**Grounding is checked, not trusted.** The server records every ID the agent actually retrieved and flags any citation outside that set. The UI marks ungrounded citations with ✗. In testing, drafts cited only retrieved sources.

**Manual loop, streamed steps.** A hand-written loop (not the SDK tool runner) emits each tool call and result as Server-Sent Events, runs a turn's tool calls in parallel, and stops after 6 turns. Per-turn Claude calls are non-streaming; the UI streams at the level of agent steps.

**Model and cost.** `claude-opus-5` at `effort: medium`, with server-side refusal fallbacks (`fallbacks: "default"`) and prompt caching on the static system prompt and tools. A typical run takes 2 turns, 18–26 s and $0.06. The model and effort are configurable (`APP_AGENT_MODEL`, `APP_AGENT_EFFORT`).

**Abuse limits.** 5 runs per client per 10 minutes and 200 per day across the demo (~$12/day worst case), plus the monthly spend limit on the Anthropic workspace.

## Memory loop
Approved and edited drafts are merged into `incident_docs` as precedents (numbers prefixed `FB-`) by the `refresh-lakehouse` job, and flow into the vector index. Later triages retrieve the human-corrected answers.

## Consequences and known limits
- Feedback text becomes retrievable content. The demo has no login, so a visitor could approve a misleading draft and "teach" the system. Mitigations: approvals are rate-limited and length-capped, tool results are passed to the model as data, and approved drafts only enter search after the batch refresh. In production, feedback would come from authenticated dispatchers, and FB- precedents could be reviewed before indexing.
- The per-client limit keys on the client IP as seen behind CloudFront, which can be spoofed. The daily cap is the real cost ceiling.
- ~20 s per run is acceptable because progress streams live. A lower effort level or Sonnet would cut latency and cost if evals (Phase 5) show quality holds.
