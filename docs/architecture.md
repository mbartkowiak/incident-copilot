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

## Agent memory loop
Dispatcher approve/edit/reject → `POST /api/triage/feedback` → `triage_feedback` (the only table the API may write) → `refresh-lakehouse` merges approved drafts into `incident_docs` as `FB-` precedents → vector index sync. Later triages retrieve the human-corrected answers.

## Decisions
See `docs/adr/`.
