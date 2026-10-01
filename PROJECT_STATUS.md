# Project Status

- Last reviewed: 2026-10-01 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Reviewed repository baseline: `a5db39eccb0a5a73ea3232f455a9167f1af835a4` — `docs: add cloud development handoff` (starting baseline; this change starts Phase 6)

The current Git `HEAD` is always authoritative; run `git log -1 --oneline` before continuing because this document is updated in a later commit than the repository baseline it reviews.

## Current phase

**Phase 6 first write-safety package implemented for Snapshot and Production Batch; public staging remains read-only.**

The repository implements and exposes a coherent demo/test lifecycle, but it is not yet a production multi-user system. The public environment is intentionally sample-only and read-only. Configurable OIDC authentication, exact scoped authorization and authenticated actor binding are implemented for all 14 current write routes, and every current command now appends an audit event in the same transaction. No identity provider is configured; idempotency/concurrency coverage is still incomplete.

## Roadmap progress

Progress is counted from checked items in `ROADMAP.md`; it measures implemented roadmap scope, not production-readiness certification.

| Phase | Completed items | Progress | Status |
| --- | ---: | ---: | --- |
| Phase 1 — Domain foundation | 5 / 5 | 100% | Complete |
| Phase 2 — Release governance | 5 / 5 | 100% | Complete for demo scope |
| Phase 3 — Distribution and production trace | 5 / 5 | 100% | Complete for demo scope |
| Phase 4 — Evidence, review and auditability | 8 / 9 | 89% | Remaining: retire/bound compatibility lists |
| Phase 5 — Identity and authorization | 8 / 9 | 89% | Remaining: configure an approved OIDC provider |
| Phase 6 — Controlled write experience | 0 / 5 | 0% | First slice implemented; broad items remain partial |
| Phase 7 — Production operations | 0 / 6 | 0% | Not started |
| **Overall** | **31 / 44** | **70%** | Demo lifecycle is coherent; controlled writes and operations remain |

## Completed and evidenced in `main`

- End-to-end stored trace: `SCR → DVP → Snapshot → Readiness → Approval → Release Decision → Delivery → Distribution → Production Authorization → Deployment → Changeover → Batch`.
- Standard and application release catalogs, exact release profiles, component deltas, frozen manifests, snapshot history/comparison, release matrix and software passport views.
- SCR/Issue/DVP catalogs, explicit acceptance-to-test assignments, snapshot-scoped coverage, issue impact candidates and append-only impact judgments.
- Approval steps/actions, release decisions, delivery package revisions, distribution receipts, production authorizations, deployment provenance, changeovers and production batches.
- Bounded/filterable catalogs for DVP, distribution, production, governance and audit history, while retaining legacy compatibility endpoints.
- Append-only PostgreSQL protection for audit events, issue impact assessments, acceptance-to-DVP links and resource links.
- Atomic audit recording for all 14 current command routes, including snapshot freeze, deployment expectation, actual-software report, changeover and batch creation.
- Executable contract inventory for all 14 write routes, covering scope, actor source, audit, idempotency, concurrency and known gaps; tests fail if FastAPI write routes drift from the inventory.
- Provider-neutral user/service principals and scoped global/software/project roles in migration `0015_identity_roles`; no credentials, identities or grants are seeded.
- Configurable OIDC write authentication with strict asymmetric signature, issuer, audience, time and required-claim validation plus fail-closed ACTIVE local-principal resolution.
- Exact active project/software role enforcement for all 14 current write routes in OIDC mode, with `PLATFORM_ADMIN` as the only scope-free override.
- Fail-closed relationship-based scope resolution plus denial tests for wrong project/software, insufficient role and suspended membership.
- Authenticated principal UUID/full display-name binding for all current OIDC writes, while preserving original request declarations and leaving historical events unchanged.
- Migration `0016_authenticated_audit_actors` adds nullable audit identity fields and an exact principal foreign key without backfilling unverified history.
- Next.js frontend, FastAPI backend, Alembic migrations, PostgreSQL Docker Compose environment, Cloudflare Worker configuration and Render-oriented backend container.
- Snapshot and Production Batch optional request-ID replay uses the existing business UUID and atomic audit request evidence; conflicting reuse/actor changes return 409. No-key clients keep legacy behavior.
- PostgreSQL Release locking serializes snapshot numbering; Deployment then shared Authorization locks serialize finite quotas across deployments, refresh ORM state and roll back every failure path.
- 47 backend test modules are present. The complete 2026-10-01 Python 3.12 run passed **421 tests**, including **13 real PostgreSQL 16.15 tests**, with no skips. PostgreSQL tests apply the entire migration chain in disposable schemas, observe actual session blocking and verify replay/conflict/quota/rollback behavior. Warnings remain existing deprecations/collection notices (1384 in this run).
- Alembic remains at the single head `0016_authenticated_audit_actors`; no migration was required. PostgreSQL SQL generation passed (850 lines). Frontend code/contracts consumed by its read pages did not change; no new frontend build was required.


## In progress

- Approved OIDC provider configuration remains open. Phase 6 now has its first Snapshot/Batch safety slice; the broad retry/concurrency roadmap items remain unchecked because other commands are unfinished.
- Code deployment verification is pending the push of this package; repository state and live state are reported separately.
- The unrelated `frontend/app/activity/page 2.tsx` was not present in this clean cloud checkout and was not recreated, adopted or deleted.

## Next stage

1. Add request-ID replay and transition locking to approval actions and release decisions, with PostgreSQL contention tests.
2. Define optimistic concurrency or append-only correction for actual-software reports.
3. Select/configure the approved OIDC provider and add provider-backed HTTP integration tests.
4. Only then evaluate controlled UI writes and a non-read-only target environment.

Roadmap progress remains **31/44 (70%)**: two broad Phase 6 items are partially implemented, not fully complete. See [ROADMAP.md](ROADMAP.md).

## Deployment status

| Layer | Configured target | Verified 2026-10-01 | Qualification |
| --- | --- | --- | --- |
| Frontend | Cloudflare Worker at `https://softwarelifecycle.whf969.com` | HTTP 200 and live dashboard HTML returned | Demo/test frontend, not evidence of production readiness |
| API | Render at `https://softwarelifecycle-api-test.onrender.com` | `/health/ready` HTTP 200, version `0.13.0`; harmless write rejected with HTTP 403 `read_only_mode` | Public sample API is current and remains read-only with OIDC disabled |
| Database | PostgreSQL behind the Render API | Ready at Alembic revision `0016_authenticated_audit_actors` through API health response | Sample/test data only; database endpoint itself was not exposed or inspected directly |
| Local stack | Docker Compose: PostgreSQL + FastAPI + Next.js | Configuration and YAML structure checked; Docker CLI was unavailable, so the stack was not started | Uses idempotent demo seed by default |

The live URLs are volatile operational state. Recheck them rather than copying this table into a future report.

## Database and API status

- Repository API version: `0.14.0`; last verified online version: `0.13.0` before this package is pushed.
- Required and verified online schema revision: `0016_authenticated_audit_actors`.
- Public test API is documented and configured for `READ_ONLY_MODE=true`; write requests should remain blocked with HTTP 403.
- Local `.env.example` defaults to `READ_ONLY_MODE=false`, `AUTH_MODE=disabled` for controlled development and `SEED_ON_STARTUP=true` for demo data.
- The API has both newer bounded catalog endpoints and older unbounded compatibility lists. Consumers should prefer bounded catalogs for directories and history review.
- OpenAPI is available at `/docs` when the API is running.

## Known gaps and issues

- OIDC authentication and scoped authorization exist, but there is no configured identity provider or browser login/session flow.
- There is no security-principal/grant management API or audited grant lifecycle yet; migration `0015` creates no identities or permissions.
- Public read access is suitable only for non-sensitive sample data. `CORS_ORIGINS` is not access control.
- All current OIDC writes use the authenticated principal for their atomic audit event and retain request declarations separately; historical/disabled-mode events remain unverified by design.
- All 14 current command routes are authenticated/scoped and atomically audited. Snapshot/Batch now support optional request-ID replay and PostgreSQL locking; approval and several other commands still lack retry/concurrency protection. See `docs/write-contracts.md`.
- Some legacy list/history APIs remain unbounded; migration to bounded catalog endpoints is incomplete.
- There is no CI workflow in the reviewed tree, so tests/builds are not enforced automatically on every push.
- Backend tests require Python 3.12 (matching `backend/Dockerfile`); this review used the repository's pinned `pytest==9.1.1` environment.
- The passing backend run reports deprecation/collection warnings, dominated by `datetime.utcnow()` usage and one SQLAlchemy `TestRelease` model name collected as a possible test class.
- Frontend build emits an existing Autoprefixer warning for `end`; use `flex-end` when that CSS is next touched.
- The earlier untracked `frontend/app/activity/page 2.tsx` remains outside this task; it was absent from this clean checkout and was not recreated, adopted or deleted.

## Handoff rules

At the start of `规划 / 开发 / 检查 / 汇总 / 继续`:

1. Fetch `origin/main`, confirm branch and working-tree state, and preserve unrelated changes.
2. Read this file plus the relevant architecture/API/database/roadmap sections.
3. Treat code, migrations, tests and deployment checks as evidence; do not infer completion from a chat.

At the end of any completed development task:

1. Update **Current phase**, **Completed**, **In progress**, **Next stage**, **Known gaps** and the reviewed baseline where applicable.
2. Update `CHANGELOG.md`; update `API.md`, `DATABASE.md` and `ARCHITECTURE.md` if their contracts changed.
3. Record checks actually run and distinguish passing, warning, skipped and unavailable checks.
4. Review the final diff, commit only in-scope files, push, and report the resulting commit hash and push status.
