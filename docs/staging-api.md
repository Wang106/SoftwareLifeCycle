# Test database and API deployment

This guide is for **demo data only**. The API has no user authentication or project-level authorization yet. `READ_ONLY_MODE=true` blocks writes, but it does not restrict who can read a public endpoint. Never load company files, customer data, passwords, or other sensitive records into an internet-facing test database.

## Choose a test database

| Environment | Database | When to use |
| --- | --- | --- |
| Developer machine | PostgreSQL 16 in the repository's Docker Compose | Local feature work and migration tests; `docker compose up --build` runs PostgreSQL, API, and web together. |
| Shared online test | A separate managed PostgreSQL database near the API service | Connect the Cloudflare frontend to a public HTTPS API without exposing the database port. Render Postgres plus a Render Docker web service is one example. |
| Alternative online test | Neon PostgreSQL plus a Docker-capable API host | Useful when the database and API are hosted separately; check connection limits and region before selecting a plan. |

Use PostgreSQL for end-to-end testing: migrations depend on PostgreSQL `JSONB` and the append-only trigger. SQLite can support isolated unit tests but cannot validate this schema and database rule.

## Deploy a sample-only API (Render example)

1. Create a **new test PostgreSQL database**. Keep it separate from any future company database. Put the database and API service in the same region; use the provider's internal database connection URL for the API.
2. Create a Docker web service from `Wang106/SoftwareLifeCycle`, branch `main`. Set its root directory to `backend` (or set Docker build context to `backend` and Dockerfile path to `backend/Dockerfile`). The image uses `entrypoint.sh`: Alembic migration, optional Seed, then FastAPI. Do not point the web service at the repository-root Dockerfile.
3. Set these service environment variables in the hosting dashboard, not in Git:

   ```text
   DATABASE_URL=<test database internal PostgreSQL URL>
   SEED_ON_STARTUP=true
   READ_ONLY_MODE=true
   CORS_ORIGINS=https://softwarelifecycle.whf969.com
   ```

   Both `postgres://` and `postgresql://` provider URLs are normalized to the installed `psycopg` driver. Preserve provider-required SSL options. The API service must listen on the host-provided `PORT`, which `entrypoint.sh` already uses.
4. Set the web service health check to `/health/ready`. Wait until it reports `status: ready` and revision `0013_acceptance_dvp_links`. The demo Seed is idempotent, so restarting this **test** service does not duplicate the named demo chain.
5. Test `https://<public-api-host>/health/ready`, `/api/v1/releases/application`, `/api/v1/issues/310/impact`, and `/api/v1/activity`. A write request must return HTTP 403 with `read_only_mode`. Run `python scripts/check_staging.py https://<public-api-host>` from the repository root to check these endpoints.
6. The Wrangler configuration sets the public test API origin as `API_BASE_URL=https://softwarelifecycle-api-test.onrender.com`. Deploy the Worker from `main` or wait for its connected Git build, then verify the homepage no longer says `Live dashboard unavailable`. To use another API origin later, change this runtime binding in the Wrangler configuration (or the Cloudflare Dashboard). Keep `DATABASE_URL` on the API service, never on Cloudflare Worker or in `NEXT_PUBLIC_*` variables.

`CORS_ORIGINS` alone is not access control. The frontend fetches the API server-side, while the public API URL is still reachable by other clients. `READ_ONLY_MODE` is a temporary sample-data guard, not a substitute for future identity and permission controls.

## Later company deployment

Keep the PostgreSQL engine and Alembic history. Provision a fresh internal PostgreSQL instance and API service, set `SEED_ON_STARTUP=false`, apply migration, and add authentication/authorization before loading real company data. An internet-hosted Cloudflare Worker cannot reach a private internal address without an explicitly designed network path; choose the company gateway or move the web frontend inside the internal network at that stage.
