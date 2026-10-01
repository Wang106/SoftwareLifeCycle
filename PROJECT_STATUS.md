# Project Status

- Last reviewed: 2026-10-01 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Reviewed repository baseline: `961994af31da607a5b36066ee7998eb3c4ea60bc` — `feat: prepare reviewed approval and release decision requests` (developed from `e7db963e55437dad00f12a267848c759841d5198`)

The current Git `HEAD` is always authoritative; run `git log -1 --oneline` before continuing because this document is updated in a later commit than the repository baseline it reviews.

## Current phase

**Phase 6 seventh package adds Approval Action/Release Decision preparation; five of 14 command forms now prepare requests; public staging remains read-only.**

The repository implements and exposes a coherent demo/test lifecycle, but it is not yet a production multi-user system. The public environment is intentionally sample-only and read-only. Configurable OIDC authentication, exact scoped authorization and authenticated actor binding are implemented for all 14 current write routes, and every current command now appends an audit event in the same transaction. No identity provider is configured; controlled UI, broader correction/revocation and operations remain incomplete.

## Roadmap progress

Progress is counted from checked items in `ROADMAP.md`; it measures implemented roadmap scope, not production-readiness certification.

| Phase | Completed items | Progress | Status |
| --- | ---: | ---: | --- |
| Phase 1 — Domain foundation | 5 / 5 | 100% | Complete |
| Phase 2 — Release governance | 5 / 5 | 100% | Complete for demo scope |
| Phase 3 — Distribution and production trace | 5 / 5 | 100% | Complete for demo scope |
| Phase 4 — Evidence, review and auditability | 8 / 9 | 89% | Remaining: retire/bound compatibility lists |
| Phase 5 — Identity and authorization | 8 / 9 | 89% | Remaining: configure an approved OIDC provider |
| Phase 6 — Controlled write experience | 3 / 5 | 60% | Safety slices and UI priorities implemented; submission/correction/result items partial |
| Phase 7 — Production operations | 0 / 6 | 0% | Not started |
| **Overall** | **34 / 44** | **77%** | Demo lifecycle is coherent; controlled writes and operations remain |

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
- 55 backend test modules are present. The complete 2026-10-01 Python 3.12 run passed **688 tests**, including **103 real PostgreSQL 16.15 tests**, with no skips. PostgreSQL tests apply the entire migration chain in disposable schemas, observe actual session blocking and verify replay/conflict/quota/rollback behavior. Warnings remain existing deprecations/collection notices (3179 in this run).
- Alembic has the single head `0017_deployment_actual_version`; its migration initializes version zero without altering existing state. PostgreSQL SQL generation passed (858 lines). This schema verification belongs to the prior backend package; current frontend verification is recorded below.


- Five of 14 command forms implement request preparation with confirmed immutable exports and expected audit/business links. Frontend tests pass 56 cases; authenticated submission remains pending.

## In progress

- Approved OIDC provider configuration remains open. Phase 6 now has five safety slices; retry/concurrency roadmap items are complete for current keyed routes. UI, broader corrections and result confirmation/trace remain.
- All five safety packages have implementation/test/deployment evidence; provider configuration and remaining UI/correction/result scope are next.
- The unrelated `frontend/app/activity/page 2.tsx` was not present in this clean cloud checkout and was not recreated, adopted or deleted.

## Next stage

1. Extend request preparation to Impact Assessment, Acceptance-to-DVP Link and Resource, with exact context and evidence.
2. Integrate approved identity/session and authenticated submission with uncertain-result recovery for the first forms.
3. Extend correction/revocation beyond actual reports, preserving formal history.
4. Configure approved OIDC, provider-backed HTTP tests and audited grant administration.
5. Migrate legacy lists and add CI, backup/restore, monitoring and environment governance.

Roadmap progress is **34/44 (77%)**, Phase 6 **3/5 (60%)**; these are implemented
scope counts, not production-readiness certification. See [ROADMAP.md](ROADMAP.md).

## Deployment status

| Layer | Configured target | Verified 2026-10-01 | Qualification |
| --- | --- | --- | --- |
| Frontend | Cloudflare Worker at `https://softwarelifecycle.whf969.com` | Browser User-Agent HTTP 200 / Dashboard HTML; Python User-Agent 403 / Cloudflare 1010 | Demo/test frontend, not evidence of production readiness |
| API | Render at `https://softwarelifecycle-api-test.onrender.com` | `/health/ready` HTTP 200, version `0.18.0`; harmless deployment write rejected with HTTP 403 `read_only_mode` | Public sample API is current and remains read-only with OIDC disabled |
| Database | PostgreSQL behind the Render API | Ready at Alembic revision `0017_deployment_actual_version` through API health response | Sample/test data only; database endpoint itself was not exposed or inspected directly |
| Local stack | Docker Compose: PostgreSQL + FastAPI + Next.js | Configuration and YAML structure checked; Docker CLI was unavailable, so the stack was not started | Uses idempotent demo seed by default |

Render deployment `dep-dav0vf0473hc73a8vl10` is **live** for feature commit
`bbd8a42b567c4f5b2c83017c570e47039442f3af` (finished 2026-10-01T07:48:56.742624Z UTC). Health returned HTTP 200 /
API `0.18.0` / database `0017_deployment_actual_version`. Release/application,
issue-impact and activity reads returned 200; actual-report OpenAPI fields and the
existing DEP-0081 detail's non-negative actual_version were verified. Harmless
Deployment, Changeover and actual-report writes returned 403 `read_only_mode`.
Frontend checks using a browser User-Agent returned HTTP 200 with Dashboard HTML
at both the bare domain and slash URL. The default Python User-Agent repeatedly
returned HTTP 403 with Cloudflare error code 1010; this client-dependent result is retained, not called
a fully passing default-agent smoke run. No frontend access policy, code or build was changed; no separate frontend deployment was needed. A first health attempt timed out during Render's
update_in_progress stage; the post-live checks above passed. No public setting or
application change was made to resolve that in-progress timeout.

The live URLs are volatile operational state. Recheck them rather than copying this table into a future report.

## Database and API status

- Repository and verified online API version: `0.18.0`.
- Required and verified online schema revision: `0017_deployment_actual_version`.
- Public test API is documented and configured for `READ_ONLY_MODE=true`; write requests should remain blocked with HTTP 403.
- Local `.env.example` defaults to `READ_ONLY_MODE=false`, `AUTH_MODE=disabled` for controlled development and `SEED_ON_STARTUP=true` for demo data.
- The API has both newer bounded catalog endpoints and older unbounded compatibility lists. Consumers should prefer bounded catalogs for directories and history review.
- OpenAPI is available at `/docs` when the API is running.

## Known gaps and issues

- OIDC authentication and scoped authorization exist, but there is no configured identity provider or browser login/session flow.
- There is no security-principal/grant management API or audited grant lifecycle yet; migration `0015` creates no identities or permissions.
- Public read access is suitable only for non-sensitive sample data. `CORS_ORIGINS` is not access control.
- All current OIDC writes use the authenticated principal for their atomic audit event and retain request declarations separately; historical/disabled-mode events remain unverified by design.
- All 14 current command routes are authenticated/scoped and atomically audited. Snapshot/Batch now support optional request-ID replay and PostgreSQL locking; actual-software keyed reporting now adds retry/version protection and correction evidence; legacy paths remain weaker. See `docs/write-contracts.md`.
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


Request preparation for Snapshot, actual software and Batch is available in code at
`/commands`, with validation, immutable confirmation/copy and expected audit links.
It never submits or saves a request. See [UI scope and remaining work](docs/controlled-write-ui.md).
## Phase 6 second package and recurring report requirements

Development mode: **Codex**. Approval actions and release decisions now implement
optional request-ID retry, original-result replay, content/actor conflict and shared
ApprovalRequest transaction locks. Keyed actions require the exact expected step;
no-key callers retain current-step behavior. Distinct release-decision numbers
remain historical records. No new migration or frontend changes are required.

Request-ID/row-lock coverage is 8/14 (57%); exact-scope authorization, trusted actor
binding and atomic audit coverage is 14/14 (100%). Broad roadmap remains 31/44 (70%):
Phase 6 is partial and provider configuration/operations remain unfinished. Future
completion reports must state Codex or ChatGPT mode, changed files/behavior, tests,
migration and push/deploy state, module percentages with unfinished content, and
remaining steps. Use ROADMAP.md for evidence-based percentages and next sequence.

Second-package verification: Python 3.12 full backend run **477 passed, 1646 warnings, no skips**, including **31 real PostgreSQL 16.15 tests**. Single Alembic head `0016_authenticated_audit_actors` and PostgreSQL SQL generation passed. No new migration or frontend change/build. Deployment `dep-dav00btg1s2s73d4nqo0` is live for `fbb66ae9a2c1833a05ee2032595eb2613d1d3a50`; health API `0.15.0` / database `0016_authenticated_audit_actors`, deployment/Snapshot writes 403 `read_only_mode`, frontend 200 with Dashboard HTML.

Staging smoke note: the stock 10-second check timed out on `/api/v1/activity` after the first three reads passed. Repeating all four reads and the harmless Snapshot write with a 45-second timeout passed; the separate deployment write also returned 403 `read_only_mode`. No smoke-check timeout or public setting was changed.

## Phase 6 third package — current capability

Development mode: **Codex**. Optional request IDs, actor/content conflicts and
transaction locks now cover Delivery, Distribution and Production Authorization.
Delivery artifact order uses set semantics while rejecting duplicates. Release
Decision, Delivery and Authorization share Release serialization for latest-decision
checks; parent ORM rows refresh. Partial child, constraint, audit and commit failures
roll back completely. Legacy payloads/HTTP 201 shapes and duplicate-number behavior
remain compatible. No migration/backfill/public writes/frontend change is introduced.

Current request-ID/row-lock coverage is **11/14 (79%)**; remaining commands are
Deployment, actual-software report and Changeover. Exact scope, actor binding and
atomic audit remain 14/14. Broad roadmap stays 31/44 (70%); provider configuration,
write UI, correction/revocation and operations are still unfinished. Full Python 3.12 suite passed **573 tests, 2326 warnings, no skips**, including **63 real PostgreSQL 16.15 tests**. This package adds 64 unit/route and 32 PostgreSQL cases. Single Alembic head and PostgreSQL SQL generation (850 lines) passed; no migration/frontend build was required. Render deployment `dep-dav0af5g1s2s73d55420` is **live** for feature commit
`42e32e9b0519a2f9f2112cd5b8cae5b92aea73c5` (finished 2026-10-01 15:02:05 Asia/Shanghai).
Post-deploy health returned HTTP 200, API `0.16.0` and database revision
`0016_authenticated_audit_actors`. Release/application, issue-impact and activity
reads returned 200. Harmless Deployment and Snapshot writes returned 403
`read_only_mode`; the three new retry routes also retained that rejection.
Frontend returned HTTP 200 with Dashboard HTML. No frontend code or separate
frontend deployment was required.

The first full run encountered a stale disposable PostgreSQL shutdown PID file (63 connection errors). The local test runtime was restarted with proper shutdown/wait; the complete rerun passed. This did not require an application or staging database change.

## Phase 6 fourth package — current development report

Development mode: **Codex**. Starting main is
`8955c8d4039850ecc0bb5c0907f5c10f26a1eb4c`. API `0.17.0` adds optional request-ID
retry and locks for Deployment/Changeover, preserving trusted actor/scope, HTTP 201
and legacy duplicate-number behavior. Actual reporting now shares Deployment locking
for consistent atomic before/after audit and Batch ordering, but has no request-ID,
optimistic token or correction contract yet. No migration/frontend change is needed.
Request-ID coverage is 13/14 (93%); row serialization/scope/actor/atomic audit are
14/14. Broad roadmap stays 31/44 (70%): actual-version protection, UI/correction,
provider configuration and operations are unfinished. Next package is actual-software
retry and optimistic conflict/correction. Full Python 3.12 suite: **641 passed, 2821 warnings, no skips**, including **90 real PostgreSQL 16.15 tests**. Single Alembic head `0016_authenticated_audit_actors` and PostgreSQL SQL generation passed. No new migration or frontend build/change. Render retry deployment `dep-dav0kvs1nsns7382pu00` is **live** for feature commit
`2410b55ceac01263f62fdac0b109408a8c88fd1d` (finished 2026-10-01T07:24:38.937384Z UTC). Health returned
HTTP 200 / API `0.17.0` / database `0016_authenticated_audit_actors`;
release/application, issue-impact and activity reads returned 200. Deployment,
Changeover and actual-report POSTs retained 403 `read_only_mode`. Frontend returned
HTTP 200 with Dashboard HTML; no frontend code or separate deployment was required.
The original auto-deploy `dep-dav0jpo473hc73a87bag` reported `update_failed` despite
completed image build, healthy startup and API 0.17.0. Error/warn logs were empty;
no definitive cause was exposed. The same commit was retried without code, schema
or environment changes and its final deployment state was verified. No application
fix is claimed for that unexplained operational failure.

## Phase 6 fifth package — development report

Development mode: **Codex**. Starting main: `5e236bed5ac687273b2a681d06a64734bcbae432`.
API code 0.18.0 implements actual report keyed retry with original outcomes,
expected-version conflicts and append-only correction evidence. Migration 0017
adds a non-negative Deployment version, preserving existing state at baseline zero.
All 14 current routes now declare request-ID/row-lock/scope/actor/atomic contracts.
Legacy no-key paths remain weaker; UI, broader correction/revocation, provider and
operations are unfinished. Roadmap scope is 33/44 (75%); Phase 6 is 2/5 (40%).
Full Python 3.12 backend suite: **688 passed, 3179 warnings, no skips**, including **103 real PostgreSQL 16.15 tests**. Added 34 unit/route and 13 PostgreSQL cases. Single Alembic head 0017 and generated PostgreSQL SQL (858 lines) passed; populated migration round-trip preserves legacy state. Frontend sources were unchanged; additive backend fields are unused by current read consumers, so no frontend build was required. Render deployment `dep-dav0vf0473hc73a8vl10` is **live** for feature commit
`bbd8a42b567c4f5b2c83017c570e47039442f3af` (finished 2026-10-01T07:48:56.742624Z UTC). Health returned HTTP 200 /
API `0.18.0` / database `0017_deployment_actual_version`. Release/application,
issue-impact and activity reads returned 200; actual-report OpenAPI fields and the
existing DEP-0081 detail's non-negative actual_version were verified. Harmless
Deployment, Changeover and actual-report writes returned 403 `read_only_mode`.
Frontend checks using a browser User-Agent returned HTTP 200 with Dashboard HTML
at both the bare domain and slash URL. The default Python User-Agent repeatedly
returned HTTP 403 with Cloudflare error code 1010; this client-dependent result is retained, not called
a fully passing default-agent smoke run. No frontend access policy, code or build was changed; no separate frontend deployment was needed. A first health attempt timed out during Render's
update_in_progress stage; the post-live checks above passed. No public setting or
application change was made to resolve that in-progress timeout.

## Phase 6 sixth package — request preparation

Development mode: **Codex**. Starting main: `4f1af50ade84c4daa964499f75725969c476685a`.
Three request-preparation forms add validation, fixed-key confirmation/copy, exact
context links and expected audit identifiers. All 14 command forms have a priority
plan. There is no submit transport, login or successful-write claim. API remains
0.18.0; schema remains 0017, with no migration. Roadmap scope becomes 34/44 (77%),
Phase 6 3/5 (60%); authenticated submission, broader corrections and full result
trace are unfinished. Frontend helper tests: **30 passed, no skips**. Next.js production and OpenNext/Cloudflare Worker builds passed; existing multiple-lockfile/Autoprefixer/cache/proxy warnings remain. Complete Python 3.12 backend suite: **688 passed, 3179 warnings, no skips**, including **103 real PostgreSQL tests**. The first two attempts encountered PostgreSQL system-catalog file read failures in workspace test directories; a new isolated /tmp cluster completed the entire suite. No backend/staging database was changed to resolve this test-runtime issue. No migration is added; head remains 0017. Local Next.js SSR checks passed for /commands (Snapshot, actual and Batch) and /create, including exact prefilled deployment targets. Feature commit `dc3a20841b7e58bb6638e3914ff298e5d0047a3e` was pushed to main. The live Cloudflare /commands page was verified in the browser: Snapshot review requires explicit confirmation before copy, repeated copy preserves the same key/body, and editing the release target removes the old review. No API write was sent. Cloudflare deployment ID/commit metadata is unavailable through the installed tools; live feature behavior is verified, not a provider deployment identifier. Render connector confirms the unchanged backend deployment dep-dav0vf0473hc73a8vl10 remains live for bbd8a42. Fresh command-line probes completed: health HTTP 200, API 0.18.0, database 0017_deployment_actual_version; harmless empty Deployment and Batch POSTs both returned 403 with detail read_only_mode. Browser navigation to the API was separately blocked with ERR_BLOCKED_BY_CLIENT; this is an environment/browser limitation, not a failing API smoke check. Public settings were not changed.

## Phase 6 seventh package — governance request preparation

Codex extends /commands with Approval Action and Release Decision forms, immutable
request review, explicit confirmation and stable copy/retry content. Approval uses
exact expected_step_id and a selected action; approval detail shows step UUIDs and
can prefill its first visible pending/waiting step. Decision records exact readiness
and decision declarations, not computed business readiness. Declared operators never
replace authenticated principals. Evidence/history and exact expected audit links are
provided without submission or business-success claims. Five of 14 forms now prepare
requests; the other nine, approved OIDC/session/target, submission, uncertain outcomes
and general correction/revocation remain. No backend change or migration; API 0.18.0,
head 0017. Roadmap scope remains 34/44 (77%), Phase 6 3/5 (60%).

Frontend helper tests: 56 passed, no skips (26 added governance cases). Next.js and OpenNext/Cloudflare Worker production builds passed. Complete Python 3.12 backend suite: 688 passed, 3179 warnings, no skips, including 103 real PostgreSQL 16.15 tests in a new isolated /tmp cluster. Local SSR checks passed for approval/decision exact target/step context, oversized-step rejection and Create entry. No migration or backend change. Feature commit `961994af31da607a5b36066ee7998eb3c4ea60bc` was pushed to main.
Live Cloudflare approval detail APR-0121 shows exact step UUIDs and no fabricated
pending-step link for its closed state. Its decision-preparation link retains the
approval number. Both new forms were reviewed/confirmed/copied in the live browser;
repeated copies retained identical keys/content, editing decision/step removed the
old review, and switching operation cleared old fields. No business POST was sent.
The initial browser tab still showed the prior workspace during automatic deployment;
fresh navigation then exposed the new detail/forms. Live feature behavior is verified;
Cloudflare deployment ID/commit metadata remains unavailable through installed tools.
Render connector confirms dep-dav0vf0473hc73a8vl10 remains live for unchanged backend
commit bbd8a42. Fresh health returned 200 / API 0.18.0 / exact database revision
0017_deployment_actual_version; harmless approval-action and release-decision POSTs
both returned 403 read_only_mode. Public settings remain unchanged.
