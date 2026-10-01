# Architecture

## System context

```text
User / reviewer
      |
      v
Next.js 15 + React 19
Cloudflare Worker (OpenNext) or local web container
      |
      | server-side HTTP, API_BASE_URL
      v
FastAPI 0.9.0
domain/query services + read-only guard
      |
      | SQLAlchemy 2 + Alembic
      v
PostgreSQL 16
formal lifecycle records + append-only history
```

GitHub `main` is the engineering source of truth. Cloudflare and Render are deployment targets; their live state must be checked independently of repository configuration.

## Repository boundaries

| Area | Responsibility |
| --- | --- |
| `frontend/app` | Next.js App Router pages and server-side API reads |
| `frontend/lib`, `frontend/components` | API clients, shared types and catalog presentation |
| `backend/app/api` | HTTP contracts, request validation and response shaping |
| `backend/app/services` | Domain rules, state transitions, readiness/trace calculations and audit coordination |
| `backend/app/models` | SQLAlchemy persistence model |
| `backend/alembic` | Ordered PostgreSQL schema history |
| `backend/tests` | Domain, API-query and transaction behavior checks |
| `docs` | Deployment/operator notes supplementary to the root project documents |

## Core lifecycle

```text
Organization / software
        |
        v
SCR -- criteria/change points/issues -- DVP plan/items/executions
        |                                  |
        +---------------> Release <--------+
                              |
                       frozen Snapshot
                              |
                    readiness + approval
                              |
                       Release Decision
                              |
               Delivery revision -> Distribution
                              |
                  Production Authorization
                              |
             Deployment -> Changeover -> Batch
```

All readiness, impact and downstream claims should be scoped to exact UUIDs and, where relevant, the exact frozen snapshot. Matching names or versions are navigation aids, not proof.

## Important design rules

### Frozen evidence

A release snapshot freezes artifact metadata and recipient rules. Later source-record changes must not silently rewrite the historical snapshot. Snapshot comparison is metadata/manifest comparison, not binary content inspection.

### Append-only formal history

PostgreSQL rejects update/delete operations for audit events, issue impact assessments, acceptance-to-DVP links and resource links. Corrections are new records. Services that currently create governance/distribution records and audit events together use one transaction so both commit or both roll back.

### Read models versus command paths

Most UI pages use read-only catalog/profile endpoints. Newer catalogs are bounded, filterable and return totals independently of the current page. Existing command APIs remain available for controlled/local use, but the public test service is guarded by `READ_ONLY_MODE=true`.

### Trust boundary

Current actor fields are request data, not authenticated principals. The database has provider-neutral user/service principals and scoped role grants, but no request authentication or authorization enforcement yet. CORS is browser policy, not authorization. Until the `SECURITY.md` enforcement sequence is complete, public deployment must contain sample data only and remain read-only.

### Failure behavior

Frontend data pages prefer explicit unavailable/empty states over fabricated fallback lifecycle records. `/health/live` reports process liveness; `/health/ready` additionally verifies database connectivity and the exact required Alembic revision.

## Runtime configurations

- Local: Docker Compose runs PostgreSQL, FastAPI and Next.js; API startup migrates and optionally seeds.
- Public demo: Cloudflare Worker serves the frontend and calls the Render FastAPI service; Render uses managed PostgreSQL and should set `READ_ONLY_MODE=true`.
- Future company environment: requires a fresh database, `SEED_ON_STARTUP=false`, authentication/authorization and an approved frontend-to-API network path.

## Change discipline

- API contract changes update `API.md` and tests.
- Schema/model changes require an ordered Alembic migration and an update to `DATABASE.md`.
- New state transitions define authorization, idempotency, concurrency and audit behavior before public exposure.
- Deployment claims are verified with health/smoke checks and recorded in `PROJECT_STATUS.md`; configuration alone is not proof of a successful deployment.
