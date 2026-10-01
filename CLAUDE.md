# Incident Intelligence Copilot

AI-assisted ITSM triage and analytics: ServiceNow-style incident data → Databricks Lakehouse → RAG + ML + Claude agent → FastAPI → React. Architecture: `docs/architecture.md`. Decisions: `docs/adr/`.

## Layout
- `apps/api` — FastAPI backend (Python 3.12, uv). `app/` code, `tests/` pytest.
- `apps/web` — React + TypeScript + Vite SPA.
- `tools/datagen` — deterministic synthetic ITSM data generator (stdlib only).
- `pipelines` — Databricks Asset Bundle: Lakeflow declarative pipeline (bronze → silver → gold), plus the `refresh-lakehouse` job (pipeline → RAG source tables → Vector Search sync, and in parallel `lifecycle.sql` → major incidents and problem candidates).
- `ml` — routing model: training, evaluation vs human routing and Claude, MLflow/Unity Catalog registration.
- `infra/terraform` — AWS infrastructure (applied manually; CI only deploys app code).
- `servicenow-app` — ServiceNow scoped app `x_67971_copilot` (ServiceNow SDK / Fluent). `npm run build`, then `npx now-sdk install --auth pdi` (credential alias `pdi` = the developer instance; the `dev` alias points at an old instance). Commit `src/fluent/generated/keys.ts`; never delete Fluent records without deciding whether the deletion should propagate.
- `docs` — architecture, ADRs, AI workflow notes.

## Commands
```
# API
cd apps/api && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run uvicorn app.main:app --reload            # http://localhost:8000/health
uv run python -m app.servicenow_seed           # one-time: groups, sites, demo users in the ServiceNow instance

# Web
cd apps/web && npm install && npm run dev        # http://localhost:5173
npm run lint && npm run build

# Synthetic data
cd tools/datagen && uv run python -m datagen --out ../../data/raw --count 8000 --seed 42
uv run pytest

# Databricks (needs CLI + auth)
cd pipelines && databricks bundle validate && databricks bundle deploy
databricks bundle run refresh_lakehouse

# Routing model (registers a new version and moves @champion)
cd ml && uv run pytest && uv run python -m routing.train --register
uv run python -m sla.evaluate                     # SLA-risk estimator comparison (ADR 0005)
```

On this machine the repo lives in OneDrive, which blocks hardlinks: set `UV_LINK_MODE=copy` for uv.

## Conventions
- Every change ships with tests; CI (`.github/workflows/ci.yml`) must stay green.
- Python: ruff + mypy strict, Pydantic models at every API boundary. TypeScript: strict mode, no `any`.
- External services (Databricks, Claude, ServiceNow) are wrapped in `apps/api/app/services/` behind interfaces so tests use fakes — never hit real services in unit tests.
- The agent never executes free-form SQL; it may only call allowlisted, parameterized query templates.
- Secrets come from env vars (local `.env`, AWS Secrets Manager in prod). Never commit keys; `.env.example` documents required vars.
- Record non-obvious architecture choices as a short ADR in `docs/adr/NNNN-title.md`.
- Keep the synthetic generator deterministic for a given `--seed`; evals depend on it.
- scikit-learn is pinned to the same version in `ml/` and `apps/api/`: the API loads the model trained in `ml/`.
