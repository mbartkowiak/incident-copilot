# Architecture

```
 SOURCES                      DATABRICKS LAKEHOUSE                           AWS
 ServiceNow-shaped JSONL ─►  bronze_* (Auto Loader, strings)
 (datagen / PDI Table API)     │
                               ▼
                             silver_* (typed, deduped, PII-scrubbed, DQ expectations)
                               │
                               ▼
                             gold_incident_facts ─ gold_daily_metrics ─ gold_hotspots
                               ├─► incident_precedents, kb_docs ─► Vector Search ◄─┐
                               ├─► MLflow + UC registry: routing_model@champion ◄──┤ (loaded in-process)
                               └─► SQL Warehouse ◄─────────────────────────────────┴─ FastAPI (ECS Fargate)
   refresh-lakehouse job: pipeline → rag_sources.sql → sync_indexes.py
                                                                            │  agent: Claude tool calling
                                                                            │  SSE streaming
                                                                            ▼
                                                                          React SPA (S3 + CloudFront)
```

## Layers
| Layer | Tech | Status |
|---|---|---|
| Synthetic source data | `tools/datagen` (stdlib Python) | Done |
| Bronze/silver/gold | Lakeflow declarative pipeline via Asset Bundle (`pipelines/`) | Deployed; all 5 planted events detected in `gold_hotspots` |
| RAG index | Databricks Vector Search, managed `databricks-gte-large-en` embeddings, delta-sync on precedent + KB tables ([ADR 0003](adr/0003-precedent-level-vector-index.md)) | Live |
| Routing model | TF-IDF + logistic regression, MLflow tracking, Unity Catalog registry, served in-process ([ADR 0002](adr/0002-in-process-routing-model.md)); benchmarked against Claude Opus 5 and Haiku 4.5 | Live |
| API | FastAPI, Pydantic, services behind interfaces | Metrics + `/api/triage/suggest` |
| Agent | Claude Opus 5 tool loop: predict team, precedent search, KB search, recent-activity check; structured draft with grounding check; SSE streaming; human approval ([ADR 0004](adr/0004-triage-agent-design.md)) | Live |
| Frontend | React + TypeScript + Vite | Overview dashboard + Triage workbench |
| Infra / CI | Terraform (AWS), GitHub Actions with OIDC | Live; deploys on every push to main |
| Quality | pytest/Vitest, eval suite gated in CI, MLflow Tracing | Phase 5 |

## Data quality rules (silver)
| Rule | Action |
|---|---|
| `number` present | drop |
| `short_description` present | drop |
| `resolved_at >= opened_at` | drop |
| priority in 1–5 | warn |
| resolved incidents have an assignment group | warn |
| duplicates by `number` | keep latest `sys_updated_on` |
| emails / phone numbers in free text | replaced with `[EMAIL]` / `[PHONE]` |

## Routing model results
Time-based split: trained on incidents opened before 2026-07-01 (6,190), tested on the following ~3 months (2,069). Reproduce with `cd ml && uv run python -m routing.train`.

Full test set (2,069 tickets):

| Approach | Accuracy | Macro-F1 | Latency (p50) | Cost / 1k tickets |
|---|---|---|---|---|
| Human first assignment (today) | 75.6% | — | minutes | analyst time |
| TF-IDF + logistic regression (champion v2) | **95.1%** | 0.93 | 2 ms | ~$0 |

Same 200-ticket random sample for all three (Claude zero-shot with structured output, team descriptions in the system prompt):

| Approach | Accuracy | Macro-F1 | Latency (p50 / p95) | Cost / 1k tickets |
|---|---|---|---|---|
| TF-IDF + logistic regression | **95.5%** | **0.946** | 2 ms | ~$0 |
| Claude Opus 5 | 91.5% | 0.945 | 1.8 s / 3.0 s | $5.19 |
| Claude Haiku 4.5 | 87.0% | 0.889 | 0.7 s / 1.1 s | $0.61 |

**Decision:** route with the trained model. It is more accurate, about 1,000× faster and effectively free per ticket. Claude Opus 5 matches it on macro-F1 with *no training data*, which makes it the right fallback for new categories or a cold start before labeled history exists. Claude is used where language understanding pays off instead: reading precedents and drafting resolutions in the triage agent (Phase 4).

Errors concentrate on vague tickets ("everything is slow", "can't log in"). Predictions below 60% confidence are flagged for human confirmation in the UI.

## Agent evals
`apps/api/evals/`: 30 golden tickets from the held-out months (2 per team plus 10 vague), with known team and expected KB article from the generator's ground truth. Deterministic checks, no LLM judge. `uv run python -m evals.run` (~$1.80) exits non-zero below the thresholds in `evals/run.py`.

| Metric | Baseline | After prompt fix |
|---|---|---|
| Team accuracy, clear tickets | 100% | 100% |
| Team accuracy, vague tickets | 60% | 60% |
| Citations grounded in retrieved data | 100% | 100% |
| Expected KB article cited (clear) | 100% | 100% |
| Clarifying questions on vague tickets | 100% | 100% |
| Clarifying questions on clear tickets (noise) | **45%** | **0%** |
| Cost / latency (p50) per ticket | $0.059 / 14.3 s | $0.059 / 13.0 s |

The baseline showed the agent asking the caller questions on nearly half of the clear tickets. One prompt change, scoped to "questions only when the answer would change the team or first step", removed that with no regressions, and a ceiling on that rate is now part of the gate. Vague-ticket misses mostly fall back to Service Desk, which is also what a human dispatcher does.

Known limit: resolved golden tickets are also in the precedent index, so retrieval is easier than for a truly new ticket. Paraphrased golden tickets would make the set harder.

## Feature evals
`apps/api/evals/features/`: the six single-call features (ticket summaries, knowledge drafts, post-incident reviews, problem records, attachment reading, the virtual agent) on 52 cases, scored by deterministic checks with no LLM judge. `build_cases.py` snapshots the inputs from the lakehouse and the KB index (varied tickets, one resolved ticket per ticket type with its retrieved articles, every major incident and problem), so a run needs only the Claude key, gives the same inputs every time, and costs about $0.90 (`uv run python -m evals.features.run`).

Each feature also gets adversarial cases: an instruction to the AI planted in ticket text, close notes, a sample ticket, a screenshot (`fixtures/injected-note.png`) and an employee's chat message. A case fails if the output acts on it. Reporting the attempt is fine.

| Check | Baseline | After fixes |
|---|---|---|
| Reviews: every stated figure is in the data | **0%** | **100%** |
| Attachments: no contact details in ticket fields | **80%** | **100%** |
| Summaries flag breaches, misroutes and reopens; invent no IDs | 100% | 100% |
| Knowledge drafts name the right article, only articles they were shown | 100% | 100% |
| Problem records: confidence matches the evidence grade | 100% | 100% |
| Virtual agent: no questions on clear reports, asks on vague ones, at most two | 100% | 100% |
| Instructions planted in data obeyed (all features) | 0 of 15 | 0 of 15 |

The baseline found two defects. Reviews stated durations and timeline times the model had worked out from the inputs, once wrongly (4.5 h for 4.4 h), because the prompt asked for figures it didn't supply. The prompt now states the duration and each ticket's resolution time. The attachment reader, shown a phishing note, reported it as suspicious but copied the attacker's email address into the ticket description in 3 of 7 runs, breaking its own rule. Contact details are now removed from those fields in code. Only factual fields are checked for figures: a recommendation such as "alert 30 days before expiry" may propose a new number.

## Sign-in and roles
Visitors sign in through Amazon Cognito: a one-click demo account per role (`POST /api/auth/demo`, signed in by the API, so no password reaches the browser) or the hosted OIDC login with PKCE, where a company's Okta or Entra ID would be federated. The API verifies the Cognito ID token on every request and checks the route's roles: employees use Get help, dispatchers triage and work tickets, knowledge managers approve knowledge drafts, and both staff roles read the analytics and queues. The ServiceNow app reads tickets with its shared secret. A ticket's caller comes from the token, not the request, and decisions record who made them. Without a user pool configured (local development, tests), auth is off. See [ADR 0011](adr/0011-sign-in-and-roles.md).

## Conversational intake and live tickets
**Get help** is the employee's side. A chat with the virtual agent (`POST /api/intake/chat`, one structured call per turn, about 1¢) asks at most two questions and proposes a ticket. Impact × urgency on the proposed ticket gives the priority. The employee reviews it and submits (`POST /api/tickets`). The ticket is written to the `tickets` Delta table and triaged at once:
- the routing model at ≥85% confidence assigns it;
- below that, it waits in the **review queue** on the Triage tab (`GET /api/tickets?view=review`);
- the closest precedent supplies its category.

Dispatchers assign, add notes and resolve from the ticket page (`/api/tickets/{number}/assign|notes|resolve`). The `incident_queue` view unions live tickets with history, computing live SLA fields at query time, so every page and AI feature works on both. See [ADR 0009](adr/0009-conversational-intake-and-live-tickets.md).

## ServiceNow connector
When `SERVICENOW_INSTANCE`, `SERVICENOW_USER` and `SERVICENOW_PASSWORD` are set, live tickets are kept in step with a ServiceNow instance through the Table API ([ADR 0010](adr/0010-servicenow-connector.md)):
- App tickets are created there (`correlation_id` = app number), and assignments, notes and resolutions follow them.
- A poller (every 60 s; **Sync now** on the Triage tab) imports incidents raised in ServiceNow, triages them, and writes back an AI work note, plus the group and category when nobody has chosen them.
- State and assignment changes made in ServiceNow flow back to the app.
- Ticket pages link to the ServiceNow incident. `GET /api/servicenow/status` reports the last sync, counts and errors.

## Attachment intake
On the Triage page a dispatcher can attach up to three screenshots, photos or PDFs (5 MB each). `POST /api/triage/attachments` checks each file's type by its content, then makes one structured Claude call with the files as image or PDF blocks. It returns the verbatim error text, device, application, site, scope, start time, a suggested title and a description addition, and it names any sensitive data it saw without copying it. After review, **Add to ticket & triage** feeds the enriched text to routing, search and the agent. Files are never stored. About 1.3-2¢ and 6-9 s per read. See [ADR 0008](adr/0008-attachment-intake.md).

## Incident lifecycle
The Incidents tab lists tickets from `gold_incident_facts` (filters: status, priority, team, SLA breached, number or text) and opens each one with:
- **Work-note journal**: parsed from the ServiceNow-style `work_notes` field into acknowledgement, investigation, reassignment, on-hold and resolution entries. The team a ticket went to first comes from its first reassignment note.
- **SLA clock**: target by priority, due time, elapsed (to the end of the extract for open tickets), met or breached.
- **Breach history**: how often this subcategory breached at this priority, and at P1/P2 how routing changed the odds. P1/P2 tickets misrouted first breached **70%** of the time vs **11%** when routed right. A trained breach classifier was evaluated and rejected ([ADR 0005](adr/0005-sla-risk-lookup-over-classifier.md)).
- **Routing check**: the routing model's prediction compared with the first and current teams, plus similar resolved incidents.
- **AI handoff note / recap**: `POST /api/incidents/{number}/summary`, one structured-output call to Claude Opus 5.5 at low effort (~$0.01, 6-9 s). Summaries are cached per ticket, and only fresh ones count against a per-client and daily limit.
- **Knowledge check** (resolved tickets): `POST /api/incidents/{number}/kb-draft` compares the fix with the three closest KB articles and returns `none`, `update` (a revised article) or `new`. An approved draft goes to `kb_drafts` via `POST /api/knowledge/drafts`. See the knowledge loop below and [ADR 0006](adr/0006-knowledge-loop.md).

## Major incidents and problems
`refresh-lakehouse` runs `pipelines/src/lifecycle.sql` after the medallion pipeline, in parallel with the RAG sources task. It rebuilds `major_incidents`, `major_incident_members`, `problem_candidates` and `problem_members` ([ADR 0007](adr/0007-major-incidents-and-problems.md)).

| | Rule | Found in current data |
|---|---|---|
| Major incident | Daily subcategory volume ≥10 and ≥5× trailing 28-day average; site-scoped when one site has ≥80% | The 4 planted outages; member precision ≥0.99, recall 1.00 |
| Problem candidate | 4-week volume ≥15 and ≥2.5× the 12-week baseline; surge = consecutive weeks at ≥2× | 6: the 4 outages, the GlobalProtect regression (strong evidence), a WAN rise (weak) |

The Major incidents and Problems tabs list them. Their detail pages show hourly or weekly charts and member tickets, plus a Claude draft on demand: a post-incident review (`POST /api/major-incidents/{id}/review`) or a problem record (`POST /api/problems/{id}/record`). Each costs 2-3¢, is cached per record, and is rate-limited like the other AI calls.

## Observability
Each agent run, ticket summary, knowledge draft and human decision writes one JSON line (`app/telemetry.py`) to the ECS task's CloudWatch log group, `/ecs/incident-copilot-api`. Logs Insights discovers the fields automatically:

```
# Cost, latency and outcome per day
filter event = "agent_run"
| stats count(*) as runs, sum(cost_usd) as cost, avg(latency_s) as avg_s,
        sum(outcome = "error") as errors, sum(ungrounded > 0) as ungrounded_drafts by bin(1d)

# How often dispatchers override the agent's team
filter event = "triage_feedback"
| stats count(*) as decisions, sum(team_changed) as team_overrides by decision

# One-call AI documents: volume, spend and failures
filter event in ["intake_turn", "attachment_read", "ticket_summary", "kb_draft", "incident_review", "problem_record"]
| stats count(*) as calls, sum(cost_usd) as cost, avg(latency_s) as avg_s by event, outcome

# ServiceNow connector: imports, pushes and failures
filter event in ["servicenow_imported", "servicenow_pushed", "servicenow_error"] | stats count(*) by event

# How new tickets are triaged: share auto-assigned vs sent to review
filter event = "ticket_created" | stats count(*) as tickets, avg(confidence) as avg_conf by mode

# What the knowledge check finds, and what engineers approve
filter event = "kb_draft" and outcome = "ok" | stats count(*) by action
filter event = "kb_decision" | stats count(*) by action, decision
```

`/health` reports the loaded routing model version. ECS restarts unhealthy tasks, and the deploy circuit breaker rolls back failed releases.

## Agent memory loop
Dispatcher approve/edit/reject → `POST /api/triage/feedback` → `triage_feedback` → `refresh-lakehouse` merges approved drafts into `incident_docs` as `FB-` precedents → vector index sync. Later triages retrieve the human-corrected answers.

## Knowledge loop
Resolved ticket → knowledge check → a knowledge manager edits and approves → `POST /api/knowledge/drafts` → `kb_drafts` → `refresh-lakehouse` builds `kb_docs` from source articles + approved new drafts (`KBD-…`), overlaying each article's latest approved revision → KB index sync → the triage agent's knowledge search returns the new text. `tickets`, `triage_feedback` and `kb_drafts` are the only tables the API may write.

## Decisions
See `docs/adr/`.
