# Changelog

## Evidence/reference request preparation — 2026-10-01

- Codex adds Impact, Acceptance-to-DVP and Resource preparation: explicit UUIDs/judgments/reasons, canonical text, immutable confirmation/copy and expected record/audit links.
- Evidence/coverage pages expose exact UUIDs and context entries; missing snapshots/items are not invented. Resource URL/path text is validated without fetching/opening/uploading.
- Eight of 14 forms prepare requests (57% of forms); login/submission/result recovery and six forms remain. Overall roadmap remains 34/44 (77%), Phase 6 3/5 (60%).
- No backend/schema/API change or migration; API 0.18.0/head 0017 and public read-only settings remain.


- Verification: frontend 111 passed; Next.js/OpenNext builds; complete backend 688 passed, no skips, including 103 real PostgreSQL tests; six local SSR context/input cases passed. Online verification follows the scoped push.

## Governance request-preparation forms — 2026-10-01

- Codex adds Approval Action/Release Decision preparation with explicit step/action, exact declarations, immutable review/confirmation/copy and business/audit links.
- Approval detail shows step UUIDs and provides exact-target preparation links; missing/stale context never proves an active step or approved readiness.
- Five of 14 command forms prepare requests. Login, authenticated submission, provider-backed outcome handling and nine other forms remain incomplete.
- No backend/API/schema change; API 0.18.0, head 0017 and public read-only settings remain. Roadmap remains 34/44 (77%), Phase 6 3/5 (60%).

- Verification: 56 frontend tests; Next.js/OpenNext builds; complete backend 688 passed, no skips, including 103 real PostgreSQL tests. Local preparation SSR passed. No new migration. Live approval/decision review/copy and edit-invalidation passed; health 200, API 0.18.0/schema 0017, both governance writes 403 read_only_mode. Feature commit 961994a is pushed; Cloudflare live behavior verified without deployment ID, unchanged Render backend remains live.

## Request-preparation workspace — 2026-10-01

- Codex development adds /commands preparation for Snapshot, actual-software and Batch: input validation, immutable reviewed key/body, confirmation/copy and expected business/audit links.
- Release/deployment/Create pages provide exact-context entry points; deployment detail shows actual_version without inventing zero for missing data.
- All 14 command forms have explicit priorities. This page does not submit, authenticate, persist or claim business success.
- API 0.18.0 and migration head 0017 are unchanged; public staging stays read-only. Roadmap scope is 34/44 (77%), Phase 6 3/5 (60%); authenticated submission and general correction/result flows remain.
- Frontend helper tests: **30 passed, no skips**. Next.js production and OpenNext/Cloudflare Worker builds passed; existing multiple-lockfile/Autoprefixer/cache/proxy warnings remain. Complete Python 3.12 backend suite: **688 passed, 3179 warnings, no skips**, including **103 real PostgreSQL tests**. The first two attempts encountered PostgreSQL system-catalog file read failures in workspace test directories; a new isolated /tmp cluster completed the entire suite. No backend/staging database was changed to resolve this test-runtime issue. No migration is added; head remains 0017. Local Next.js SSR checks passed for /commands (Snapshot, actual and Batch) and /create, including exact prefilled deployment targets. Online deployment checks follow the scoped push.


## 0.18.0 — Actual-report retry/version/correction (2026-10-01)

- Codex development: optional request-ID actual reports require expected_version; matching retries recover original status/version from atomic audit without another write/event.
- Conflicting content/actor/global target, stale expected version and missing replacement reason return conflicts; current exact permission and trusted identity remain required.
- Corrections append ACTUAL_CORRECTED reason and complete before/after software, status, UTC time and version. Existing batches and physical flashing are not reversed.
- Migration 0017_deployment_actual_version preserves current state and initializes non-negative versions to zero without reconstructing history. Detail/report responses add actual_version; old no-key clients remain compatible but weaker.
- Added unit and real PostgreSQL coverage for retry, versions, corrections, concurrency, migration data preservation and full rollback; all 14 route contracts now declare request-ID and row serialization.
- Roadmap marks the current retry/concurrency items complete: 33/44 (75%), Phase 6 2/5 (40%); controlled UI, general correction/revocation and result confirmation/trace remain.
- Full Python 3.12 suite: 688 passed, 3179 warnings, no skips (103 real PostgreSQL tests). Single Alembic head 0017 and PostgreSQL SQL (858 lines) passed; legacy migration preservation verified. Verified deployment dep-dav0vf0473hc73a8vl10 is live for bbd8a42b567c4f5b2c83017c570e47039442f3af: API 0.18.0, schema 0017, read checks and browser-agent frontend 200; writes 403 read_only_mode. Default Python-agent frontend requests repeatedly returned 403 / Cloudflare 1010; no access-policy change was made. A health attempt timed out during update_in_progress; post-live checks passed. Public staging remains read-only.


This project does not yet publish tagged releases. Entries below summarize repository milestones from Git history; they do not claim semantic-version releases or production certification.

## Unreleased

- Verified production retry deployment `dep-dav0kvs1nsns7382pu00` for `2410b55ceac01263f62fdac0b109408a8c88fd1d`: live API `0.17.0`, database `0016_authenticated_audit_actors`, public writes 403 `read_only_mode`, read checks/frontend 200. Initial auto-deploy metadata reported update_failed with normal build/startup and no exposed errors; same-commit retry reached verified live status without code/schema/environment changes.

- Fourth-package full Python 3.12 verification: 641 passed, 2821 warnings, no skips; 90 real PostgreSQL 16.15 tests. Single Alembic head and PostgreSQL SQL generation passed.

- API `0.17.0`: Deployment/Changeover optional request-ID replay, content/actor conflict, UTC Changeover time semantics and transaction locks. Deployment locks Authorization -> Site -> Line; Changeover locks Deployment. Legacy payloads/HTTP 201 and distinct-number history remain compatible.
- Actual reporting now locks/refreshes Deployment before reading audited before-state, coordinating with Changeover/Batch; it still lacks retry/version conflict protection. Validation/constraint/audit/commit failures roll back. No migration/backfill/frontend changes.
- Added 41 unit/route cases and 27 actual PostgreSQL cases for retry, scope/actor/policy, parent refresh, global unique races, rollback, actual audit/Batch ordering and deadlock avoidance. Request-ID coverage is 13/14 (93%); broad roadmap stays 31/44 (70%).

- Verified distribution-chain deployment `dep-dav0af5g1s2s73d55420` for `42e32e9b0519a2f9f2112cd5b8cae5b92aea73c5`: live API `0.16.0`, database `0016_authenticated_audit_actors`, public writes 403 `read_only_mode`, read smoke endpoints 200 and frontend 200 with Dashboard HTML.

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
