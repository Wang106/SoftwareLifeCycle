# SoftwareLifeCycle

Automotive software lifecycle governance platform for BMS / ECU software.

The implemented traceability chain is:

`SCR → DVP → Snapshot → Readiness → Approval → Release Decision → Delivery → Distribution → Production Authorization → Deployment → Changeover → Batch`

The demo dataset follows one consistent frozen release path:

`SNAP-008 → APR-0121 → RD-0081 → DP-0226 → DIST-0326 → PA-0081 → DEP-0081 → CO-0032 → PB-1005-A`

The Activity workspace is backed by an append-only audit ledger. PostgreSQL rejects updates and deletes to formal audit events; corrections must be recorded as new events.

## Stack

- Next.js + TypeScript, deployed to Cloudflare Workers through OpenNext
- FastAPI + SQLAlchemy + Alembic
- PostgreSQL
- Docker Compose for a complete local environment

## Local environment

```bash
cp .env.example .env
docker compose up --build
```

Open the web application at `http://localhost:3000` and the API documentation at `http://localhost:8000/docs`.

The API container performs these steps in order:

1. applies every Alembic migration;
2. loads the idempotent demo dataset when `SEED_ON_STARTUP=true`;
3. starts FastAPI;
4. becomes healthy only when PostgreSQL is reachable and is on the required migration revision.

Set `SEED_ON_STARTUP=false` for a production database after the demo data is no longer wanted.

## Health checks

- `GET /health` — compatibility health endpoint
- `GET /health/live` — process liveness
- `GET /health/ready` — database connectivity and schema revision readiness

Use `/health/ready` for load balancers and container health checks.

## Cloudflare frontend

The root Wrangler configuration deploys the Worker to `softwarelifecycle.whf969.com`.

```bash
npm ci
npm run build
npm run deploy
```

Configure `API_BASE_URL` as a Cloudflare Worker runtime environment variable pointing to the public FastAPI origin, for example `https://api.example.com`. It is intentionally a server-side variable: the frontend pages query FastAPI from the Worker and do not expose an internal container address to browsers.

For Cloudflare Workers Builds, also add any variables needed during static generation under **Build variables and secrets**. The deploy command uses `--keep-vars`, so dashboard-managed runtime variables are preserved.

## Backend deployment

Build and run `backend/Dockerfile` with a managed PostgreSQL database. At minimum configure:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
CORS_ORIGINS=https://softwarelifecycle.whf969.com
SEED_ON_STARTUP=false
```

For the first demo deployment, `SEED_ON_STARTUP=true` safely creates or updates the named demo records. The seed is idempotent, but production data should normally be provisioned separately.

Before sending traffic, verify:

```bash
curl --fail https://API_HOST/health/ready
curl --fail https://API_HOST/api/v1/distributions/DIST-0326
curl --fail https://API_HOST/api/v1/authorizations/PA-0081
curl --fail https://API_HOST/api/v1/deployments/DEP-0081
```

## Verification

```bash
cd backend && pytest -q
cd frontend && npm run build
```

The product baseline is available at `docs/baseline-v1.1.html`.
