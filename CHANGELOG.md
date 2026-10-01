# Changelog

This project does not yet publish tagged releases. Entries below summarize repository milestones from Git history; they do not claim semantic-version releases or production certification.

## Unreleased

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
