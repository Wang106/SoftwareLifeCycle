# Changelog

This project does not yet publish tagged releases. Entries below summarize repository milestones from Git history; they do not claim semantic-version releases or production certification.

## Unreleased

- Third-package full verification: 573 passed, 2326 warnings, no skips; 63 real PostgreSQL 16.15 cases. Single Alembic head and PostgreSQL SQL generation passed, no migration/frontend change. A disposable PostgreSQL startup error was fixed before the successful full rerun.

- API `0.16.0`: Delivery, Distribution and Production Authorization optional request-ID replay, content/trusted-actor conflict and PostgreSQL parent-row serialization. Legacy clients and HTTP 201 shapes remain compatible; delivery file order is equivalent and duplicate IDs remain invalid.
- Release Decision now acquires Release before ApprovalRequest, coordinating latest-decision checks with Delivery/Authorization; failures roll back domain, child items and atomic audit together. No migration or historical backfill.
- Added distribution retry/policy/actor/permission/failure tests and 32 real PostgreSQL concurrency cases, including observed cross-parent blocking and both release-decision/downstream orderings. Safety contract coverage is 11/14 (79%); broad roadmap remains 31/44 (70%).

- Verified Approval/Decision safety deployment `dep-dav00btg1s2s73d4nqo0` for `fbb66ae9a2c1833a05ee2032595eb2613d1d3a50`: live API `0.15.0`, database `0016_authenticated_audit_actors`, harmless writes 403 `read_only_mode`, frontend 200 with Dashboard HTML.

- API `0.15.0`: Approval Action and Release Decision optional request-ID retry, canonical content/actor conflict and shared PostgreSQL ApprovalRequest serialization. Keyed actions require an exact expected-step UUID and return original after-status without advancing another step. Legacy no-key clients and distinct decision-number history remain compatible.
- Full backend verification: 477 passed, 1646 warnings, no skips; 31 tests use real PostgreSQL 16.15. Single Alembic head and PostgreSQL SQL generation passed.
- Added approval failure/HTTP/scope/actor tests and 18 real PostgreSQL contention cases, including final-action/decision ordering, global-key races, stale ORM refresh and rollback/lock release. No migration; existing UUID/audit evidence is reused.
- Recorded recurring Codex/ChatGPT-mode, changes/tests, module percentage/unfinished scope and remaining-step reporting rules. Broad roadmap remains 31/44 (70%); request-ID/row-lock route coverage is now 8/14 (57%).

- Verified the Phase 6 first-package Render deployment for `3968f9f007e2a00a7268074e5e66cc1a0a8db2cc`: live API `0.14.0`, schema `0016_authenticated_audit_actors`, HTTP 403 `read_only_mode` for a harmless write, and available frontend (HTTP 200 / rendered Dashboard).

- API `0.14.0`: optional request-ID idempotency for Snapshot and Production Batch; identical authorized retries reuse the original result and audit, while changed content/actor or duplicate business numbers conflict. Existing no-key clients retain their behavior.
- PostgreSQL Release row locking serializes snapshot numbering; Deployment then shared Authorization row locks serialize batch-limit checks across deployments. Validation/constraint/audit/commit failures roll back the whole command; locked ORM state is refreshed.
- No migration or historical backfill: existing domain UUIDs and atomic audit JSONB evidence implement the retry contract; schema head remains `0016_authenticated_audit_actors`.
- Added business retry/rollback/authorization tests and real PostgreSQL concurrency tests on isolated migrated schemas, including observed database blocking, shared quotas and cross-target conflicts. Full Python 3.12 run: 421 passed, including 13 PostgreSQL tests, no skips; single Alembic head and PostgreSQL SQL generation passed.

- Added a self-contained Codex cloud handoff covering the implemented solution, verified 70% roadmap progress, operational state, risks, next development package and acceptance criteria.
- Added trusted, atomic audit events for snapshot creation and production deployment, actual-software, changeover and batch commands; all 14 current write routes are now atomically audited.
- Added rollback tests proving failed audit writes do not leave snapshot or production domain changes, and raised the API version to `0.13.0` without a schema migration.
- Added migration `0016_authenticated_audit_actors`; new OIDC-mode audit events store the authenticated principal UUID/full display name and preserve the original request declaration separately.
- Bound actor-bearing governance, distribution, impact, trace-assignment, test-release and resource domain records to the authenticated principal while retaining legacy behavior when authentication is disabled.
- Enforced exact active project/software roles on all 14 current write routes whenever OIDC mode is enabled, with `PLATFORM_ADMIN` as the only scope-free override.
- Added fail-closed scope resolution through release, SCR, approval, distribution, authorization, deployment and supported resource relationships, plus wrong-scope/role/suspension denial tests.
- Added configurable OIDC authentication for writes with strict HTTPS configuration, asymmetric algorithm allow-list, signature/issuer/audience/time validation and fail-closed ACTIVE principal resolution.
- Preserved public staging read-only precedence and controlled local `AUTH_MODE=disabled` compatibility.
- Added provider-neutral user/service principals, global role assignments, software membership and project membership in migration `0015_identity_roles`; no credentials or grants are seeded.
- Defined role requirements for every write contract and kept public staging read-only throughout the identity/authorization work.
- Added an executable contract inventory covering every FastAPI write route, with a drift test and explicit identity, authorization, audit, idempotency and concurrency gaps.
- Added the cross-ChatGPT/Codex handoff protocol and established GitHub `main` as the source of truth.
- Added maintained project status, roadmap, architecture, API and database references.
- Documented verified deployment status, known production gaps and the recommended identity/authorization phase.
- Updated the staging smoke check and deployment guide to require the current `0014_resource_links` database revision.

## 2026-09-30

- Added exact standard/application release profiles, historical snapshot manifests and comparisons, customer/project release matrix and software passport views.
- Added snapshot-bound issue impact evidence and append-only judgments.
- Added explicit acceptance-to-DVP assignments and snapshot-scoped SCR coverage review.
- Added filtered DVP catalogs, purpose-limited test releases and append-only resource references.
- Added bounded distribution, production, governance and audit catalogs with exact record links.
- Added atomic audit recording for governance and distribution service writes.

## 2026-09-29

- Added live dashboard/search, organization catalogs and application release profiles.
- Added downstream lifecycle trace, deployment provenance and browsable delivery/distribution/authorization/batch records.
- Added read-only staging preparation and connected the Cloudflare Worker configuration to the Render test API.
- Added recorded DVP execution, SCR, approval and readiness/evidence views without fabricated fallback records.

## 2026-09-28

- Established the Next.js, FastAPI, SQLAlchemy/Alembic and PostgreSQL application baseline.
- Added release/component/artifact, SCR/Issue/DVP, snapshot and artifact-policy models.
- Added readiness, approval, release decision, delivery, distribution, production authorization and production traceability services.
- Added local Docker Compose and deployment configuration.

## Maintenance rule

Every completed `开发` task adds an entry under **Unreleased** describing behavior, data/API changes and verification. When a tagged release is introduced, move the relevant entries under that version and date; do not rewrite historical Git-derived milestones.
