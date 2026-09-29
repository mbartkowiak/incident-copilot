# Incident Intelligence Copilot

AI-assisted IT incident triage and analytics, built end to end: a Databricks Lakehouse pipeline, retrieval-augmented generation over past incidents and knowledge articles, an ML routing model, and a Claude-powered triage agent, served through FastAPI to a React dashboard.

> Status: Phase 1 complete (data foundation live on Databricks). See [docs/architecture.md](docs/architecture.md).

## Why
About a quarter of incidents at a typical enterprise service desk are first sent to the wrong team. Every reassignment adds hours to resolution. This project predicts the right team, retrieves how similar incidents were fixed, and drafts a resolution for a human to accept. It also gives IT leaders a view of where incidents are spiking and why.

## Repo
| Path | What |
|---|---|
| `apps/api` | FastAPI backend |
| `apps/web` | React + TypeScript frontend |
| `tools/datagen` | Deterministic synthetic ServiceNow-shaped data generator |
| `pipelines` | Databricks Asset Bundle: bronze → silver → gold pipeline |
| `docs` | Architecture and decision records |

## Quick start
```bash
# 1. Generate data (writes to ./data/raw, git-ignored)
cd tools/datagen && uv run python -m datagen --out ../../data/raw

# 2. API
cd apps/api && uv sync && uv run uvicorn app.main:app --reload

# 3. Web
cd apps/web && npm install && npm run dev
```

## Deploy the pipeline to Databricks
Requires the [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html), authenticated with `databricks auth login`.
```bash
cd pipelines
databricks bundle deploy
databricks fs cp -r ../data/raw/incidents   dbfs:/Volumes/workspace/incident_copilot/raw/incidents
databricks fs cp -r ../data/raw/kb_articles dbfs:/Volumes/workspace/incident_copilot/raw/kb_articles
databricks bundle run itsm_medallion
```

## Built with AI coding tools
This project is developed with Claude Code. `CLAUDE.md` holds the project conventions the agent follows. Tests, type checks and (from Phase 5) evals in CI are the quality gate for all code, whether written by hand or by AI.
