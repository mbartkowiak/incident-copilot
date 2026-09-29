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
                               ├─► *_chunks ─► Vector Search index        (Phase 3)
                               ├─► MLflow classifier ─► serving endpoint  (Phase 3)
                               └─► SQL Warehouse ◄──────────────────────── FastAPI (ECS Fargate)
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
| RAG index | Databricks Vector Search (delta-sync on chunk tables) | Phase 3 |
| Routing model | scikit-learn/LightGBM + MLflow, compared against Claude zero-shot | Phase 3 |
| API | FastAPI, Pydantic, services behind interfaces | Skeleton |
| Agent | Claude tool calling: similar incidents, KB search, predict group, allowlisted metric queries, ServiceNow writeback | Phase 4 |
| Frontend | React + TypeScript + Vite | Skeleton |
| Infra / CI | Terraform (AWS), GitHub Actions with OIDC | CI done; infra Phase 2 |
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

## Agent memory loop (Phase 4)
Triage accept/edit/reject → `triage_feedback` → scheduled merge into gold → vector index re-sync. Later triages retrieve the human-corrected answers.

## Decisions
See `docs/adr/`.
