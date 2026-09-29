# Incident Intelligence Copilot

AI-assisted IT incident triage and analytics, built end to end: a Databricks Lakehouse pipeline, retrieval-augmented generation over past incidents and knowledge articles, an ML routing model, and a Claude-powered triage agent, served through FastAPI to a React dashboard.

**Live demo: https://d1fjhcqqwngd2n.cloudfront.net**

> Status: Phase 2 complete. The Overview dashboard is live on AWS and reads from Databricks. RAG, the routing model and the triage agent are next. See [docs/architecture.md](docs/architecture.md).

## Why
About a quarter of incidents at a typical enterprise service desk are first sent to the wrong team. Every reassignment adds hours to resolution. This project predicts the right team, retrieves how similar incidents were fixed, and drafts a resolution for a human to accept. It also gives IT leaders a view of where incidents are spiking and why.

## Repo
| Path | What |
|---|---|
| `apps/api` | FastAPI backend |
| `apps/web` | React + TypeScript frontend |
| `tools/datagen` | Deterministic synthetic ServiceNow-shaped data generator |
| `pipelines` | Databricks Asset Bundle: bronze → silver → gold pipeline |
| `infra/terraform` | AWS: ECS Fargate API behind an ALB, S3 + CloudFront frontend, GitHub OIDC deploy role |
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

## Deployment
Every push to `main` runs lint, type checks and tests for all components plus `terraform validate`. If everything passes, GitHub Actions:
1. assumes an AWS role through **OIDC** (no AWS keys stored in GitHub; only `main` of this repo can assume it),
2. builds the API image, pushes it to ECR with an immutable tag, and rolls out a new ECS task definition (the circuit breaker rolls back automatically if health checks fail),
3. builds the frontend, syncs it to S3, and invalidates CloudFront.

CloudFront serves the frontend and routes `/api/*` to the load balancer, so the browser sees one HTTPS origin. The load balancer only accepts traffic from CloudFront's IP ranges. The API reaches Databricks as a **read-only service principal** (SELECT on one schema, CAN_USE on the warehouse). Its OAuth secret lives in Secrets Manager and is injected at runtime; it never appears in code, CI, or Terraform state.

```bash
cd infra/terraform && terraform init && terraform plan   # infra changes are applied manually
```

## Built with AI coding tools
This project is developed with Claude Code. `CLAUDE.md` holds the project conventions the agent follows. Tests, type checks and (from Phase 5) evals in CI are the quality gate for all code, whether written by hand or by AI.
