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
| Routing model | TF-IDF + logistic regression, MLflow tracking, Unity Catalog registry, served in-process ([ADR 0002](adr/0002-in-process-routing-model.md)) | Live; Claude comparison pending |
| API | FastAPI, Pydantic, services behind interfaces | Metrics + `/api/triage/suggest` |
| Agent | Claude tool calling: similar incidents, KB search, predict group, allowlisted metric queries, ServiceNow writeback | Phase 4 |
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

| Approach | Accuracy | Macro-F1 | Latency (p50) | Cost / 1k tickets |
|---|---|---|---|---|
| Human first assignment (today) | 75.6% | — | minutes | analyst time |
| TF-IDF + logistic regression (champion v2) | **95.1%** | 0.93 | 2 ms | ~$0 |
| Claude zero-shot (Opus 5, Haiku 4.5) | pending | | | |

Errors concentrate on vague tickets ("everything is slow", "can't log in"). Predictions below 60% confidence are flagged for human confirmation in the UI.

## Agent memory loop (Phase 4)
Triage accept/edit/reject → `triage_feedback` → scheduled merge into gold → vector index re-sync. Later triages retrieve the human-corrected answers.

## Decisions
See `docs/adr/`.
