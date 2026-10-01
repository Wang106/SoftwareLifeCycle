# Project Status

- Last reviewed: 2026-10-01 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Reviewed repository baseline: `8256675537987ae1da236b321a573f61b35cde69` — `feat: add configurable OIDC write authentication`

The current Git `HEAD` is always authoritative; run `git log -1 --oneline` before continuing because this document is updated in a later commit than the repository baseline it reviews.

## Current phase

**Phase 5 identity and authorization foundation, still read-only in public staging.**

The repository implements and exposes a coherent demo/test lifecycle, but it is not yet a production multi-user system. The public environment is intentionally sample-only and read-only. Configurable OIDC authentication is implemented for writes, but no provider is configured and project/software authorization is not implemented.

## Completed and evidenced in `main`

- End-to-end stored trace: `SCR → DVP → Snapshot → Readiness → Approval → Release Decision → Delivery → Distribution → Production Authorization → Deployment → Changeover → Batch`.
- Standard and application release catalogs, exact release profiles, component deltas, frozen manifests, snapshot history/comparison, release matrix and software passport views.
- SCR/Issue/DVP catalogs, explicit acceptance-to-test assignments, snapshot-scoped coverage, issue impact candidates and append-only impact judgments.
- Approval steps/actions, release decisions, delivery package revisions, distribution receipts, production authorizations, deployment provenance, changeovers and production batches.
- Bounded/filterable catalogs for DVP, distribution, production, governance and audit history, while retaining legacy compatibility endpoints.
- Append-only PostgreSQL protection for audit events, issue impact assessments, acceptance-to-DVP links and resource links.
- Atomic audit recording for current approval/release-decision and delivery/distribution/authorization service writes.
- Executable contract inventory for all 14 write routes, covering scope, actor source, audit, idempotency, concurrency and known gaps; tests fail if FastAPI write routes drift from the inventory.
- Provider-neutral user/service principals and scoped global/software/project roles in migration `0015_identity_roles`; no credentials, identities or grants are seeded.
- Configurable OIDC write authentication with strict asymmetric signature, issuer, audience, time and required-claim validation plus fail-closed ACTIVE local-principal resolution.
- Planned role requirements for every write route, without claiming that scoped authorization is already enforced.
- Next.js frontend, FastAPI backend, Alembic migrations, PostgreSQL Docker Compose environment, Cloudflare Worker configuration and Render-oriented backend container.
- 42 backend test modules are present. On 2026-10-01, all 366 collected backend tests passed under Python 3.12 with pytest 8.4.2; Alembic reports the single head `0015_identity_roles`, and the `0014 → 0015` offline PostgreSQL SQL generation passed. The most recent frontend production build passed on 2026-09-30; this backend-only slice did not change frontend code.

## In progress

- OIDC provider configuration and route-level scoped authorization enforcement. No identity provider is configured yet.
- No separate tracked product feature was in progress when `main` was reviewed. The working tree contained an unrelated untracked duplicate file, `frontend/app/activity/page 2.tsx`; it was not used or committed by this documentation change and its ownership should be confirmed before deletion or adoption.

## Next stage

Recommended next stage: **identity, authorization and controlled write workflows**.

1. Select/configure the approved OIDC issuer, audience and explicit JWKS endpoint.
2. Resolve exact software/project scope from stored relationships.
3. Enforce scoped roles in FastAPI before exposing writes outside local development.
4. Replace declared actor names with authenticated actor identity while retaining historical declarations.
5. Add wrong-project and insufficient-role integration tests; only then design UI write forms.

See [ROADMAP.md](ROADMAP.md) for sequencing and acceptance gates.

## Deployment status

| Layer | Configured target | Verified 2026-10-01 | Qualification |
| --- | --- | --- | --- |
| Frontend | Cloudflare Worker at `https://softwarelifecycle.whf969.com` | HTTP 200 and live dashboard HTML returned | Demo/test frontend, not evidence of production readiness |
| API | Render at `https://softwarelifecycle-api-test.onrender.com` | `/health/ready` HTTP 200, version `0.10.0`; staging reads passed; harmless write rejected with HTTP 403 `read_only_mode` | Public sample API; OIDC authentication remains disabled while read-only mode is active |
| Database | PostgreSQL behind the Render API | Ready at Alembic revision `0015_identity_roles` through API health response | Sample/test data only; database endpoint itself was not exposed or inspected directly |
| Local stack | Docker Compose: PostgreSQL + FastAPI + Next.js | Configuration and YAML structure checked; Docker CLI was unavailable, so the stack was not started | Uses idempotent demo seed by default |

The live URLs are volatile operational state. Recheck them rather than copying this table into a future report.

## Database and API status

- Repository and verified online API version: `0.10.0`.
- Required and verified online schema revision: `0015_identity_roles`.
- Public test API is documented and configured for `READ_ONLY_MODE=true`; write requests should remain blocked with HTTP 403.
- Local `.env.example` defaults to `READ_ONLY_MODE=false`, `AUTH_MODE=disabled` for controlled development and `SEED_ON_STARTUP=true` for demo data.
- The API has both newer bounded catalog endpoints and older unbounded compatibility lists. Consumers should prefer bounded catalogs for directories and history review.
- OpenAPI is available at `/docs` when the API is running.

## Known gaps and issues

- OIDC token validation exists, but there is no configured identity provider, browser login/session flow or route-level scoped authorization.
- There is no security-principal/grant management API or audited grant lifecycle yet; migration `0015` creates no identities or permissions.
- Public read access is suitable only for non-sensitive sample data. `CORS_ORIGINS` is not access control.
- Actor names in current requests are declared strings, not authenticated identities.
- Snapshot and production command paths still lack atomic audit events; approval and several other commands lack idempotency and row-level concurrency protection. See `docs/write-contracts.md`.
- Some legacy list/history APIs remain unbounded; migration to bounded catalog endpoints is incomplete.
- There is no CI workflow in the reviewed tree, so tests/builds are not enforced automatically on every push.
- Backend tests require Python 3.12 (matching `backend/Dockerfile`). The configured package source could not resolve the repository's `pytest==9.1.1` pin during this review, so the passing run used pytest 8.4.2; verify the pin against the intended package source.
- The passing backend run reports deprecation/collection warnings, dominated by `datetime.utcnow()` usage and one SQLAlchemy `TestRelease` model name collected as a possible test class.
- Frontend build emits an existing Autoprefixer warning for `end`; use `flex-end` when that CSS is next touched.
- The untracked `frontend/app/activity/page 2.tsx` needs an ownership decision and must not be silently committed or deleted.

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
