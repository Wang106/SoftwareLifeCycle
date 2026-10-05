# Project Status

- Last reviewed: 2026-10-05 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Reviewed starting repository baseline: `9f39932ee5501c06150295e931a1b67f1a8f7631` — self identity/grant API0.18.28 merged as013d7ab; exact-main CI, production deployment and API denial/runtime checks passed; Preview URL returned, browser access blocked1010

The current Git `HEAD` is always authoritative; run `git log -1 --oneline` before continuing because this document is updated in a later commit than the repository baseline it reviews.

## Current phase

Authenticated self identity and independently paginated active own-grant reads are implemented in API0.18.28. They provide session integration context; provider-backed browser login/logout/expiration and audited grant administration remain pending.

**All 63 pages support default Chinese and selectable English. All 14 request-preparation forms are implemented; deployment, authorization, distribution and exact delivery revision details use bounded profile/catalog reads; ASR downstream now uses fixed summaries and scoped catalogs. ASR evidence now uses exact Snapshot pagination; Shared release coverage uses SQL aggregates and SSR details and ASR component/baseline declarations use independently paginated collections; ASR frozen policy and exact Snapshot detail now have pinned artifact/rule pages; Snapshot comparison now has pinned SQL summary/difference pages; ASR passport now has paired UUID summary and four bounded histories; current readiness now uses SQL policy/exception summaries and a bounded exception page; release directories and exact legacy resolution now use bounded reads; SCR/Issue directories now use bounded queries/full statistics; SCR detail uses scalar summary, independent collection pages and selected point/plan item pages; SCR coverage now uses full SQL counts, paged collections and exact selected-group evidence; Issue detail/impact now use full counts and paged relations/candidates/judgments/frozen evidence; organization directories/profiles now use scalar summaries/full counts and bounded owned collections; manufacturing directory/detail now use complete scalar summaries and owned bounded line pages; all 17 identified read-consumer groups are migrated; DVP exact profiles now use scalar counts and independent owned relation pages. Approval detail uses scalar summary and independently paged steps/actions; reviewed legacy GET retirements total50; three active scalar compatibility reads have bounded growth evidence. Fixed53-candidate closure is complete. Authenticated submission remains pending; public staging remains read-only.**

The repository implements and exposes a coherent demo/test lifecycle, but it is not yet a production multi-user system. The public environment is intentionally sample-only and read-only. Configurable OIDC authentication, exact scoped authorization and authenticated actor binding are implemented for all 14 current write routes, and every current command now appends an audit event in the same transaction. No identity provider is configured; controlled UI, broader correction/revocation and operations remain incomplete.

## Roadmap progress

Progress is counted from checked items in `ROADMAP.md`; it measures implemented roadmap scope, not production-readiness certification.

| Phase | Completed items | Progress | Status |
| --- | ---: | ---: | --- |
| Phase 1 — Domain foundation | 5 / 5 | 100% | Complete |
| Phase 2 — Release governance | 5 / 5 | 100% | Complete for demo scope |
| Phase 3 — Distribution and production trace | 5 / 5 | 100% | Complete for demo scope |
| Phase 4 — Evidence, review and auditability | 9 / 9 | 100% | Fixed compatibility scope completed |
| Phase 5 — Identity and authorization | 8 / 9 | 89% | Remaining: configure an approved OIDC provider |
| Phase 6 — Controlled write experience | 3 / 5 | 60% | Safety slices and UI priorities implemented; submission/correction/result items partial |
| Phase 7 — Production operations | 1 / 6 | 17% | CI complete; recovery/monitoring/environments/network/data remain |
| **Overall** | **36 / 44** | **82%** | Demo lifecycle is coherent; controlled writes and operations remain |

Separate read-consumer tracking: **17 / 17 (100%)**; manufacturing completes the
last identified group-17 consumers. The fixed compatibility endpoint retirement/bounds acceptance requirement is complete (50 retired +3 bounded). See [the fixed scope-group ledger](docs/read-consumer-migration.md).
This finer counter does not change ROADMAP acceptance-item accounting or certify production readiness.

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
- 66 backend test modules are present. The complete 2026-10-03 (Asia/Shanghai) Python 3.12 run passed **875 tests**, including **111 real PostgreSQL 16.15 tests**, with no skips. PostgreSQL tests apply the entire migration chain in disposable schemas, observe actual session blocking and verify replay/conflict/quota/rollback behavior. Warnings remain existing deprecations/collection notices (5456 in this run).
- Alembic has the single head `0018_asr_evidence_index`; it adds only a DVP execution scope index. Full PostgreSQL upgrade and 0018-to-0017 downgrade SQL generation passed; real PostgreSQL index upgrade/downgrade/upgrade preserved records.


- All 14 command forms implement request preparation with confirmed immutable exports and expected audit/business links. Frontend tests pass 339 cases; authenticated submission remains pending.

## In progress

- Approved OIDC provider configuration remains open. Phase 6 now has five safety slices; retry/concurrency roadmap items are complete for current keyed routes. UI, broader corrections and result confirmation/trace remain.
- All five safety packages have implementation/test/deployment evidence; provider configuration and remaining UI/correction/result scope are next.
- The unrelated `frontend/app/activity/page 2.tsx` was not present in this clean cloud checkout and was not recreated, adopted or deleted.

## Next stage

1. Configure an approved identity provider, browser session and controlled write target; the fixed read-consumer/compatibility scope and CI are complete.
2. Integrate approved identity/session and authenticated submission with uncertain-result recovery for the first forms.
3. Extend correction/revocation beyond actual reports, preserving formal history.
4. Configure approved OIDC, provider-backed HTTP tests and audited grant administration.
5. Migrate legacy lists and add CI, backup/restore, monitoring and environment governance.

Roadmap progress is **34/44 (77%)**, Phase 6 **3/5 (60%)**; these are implemented
scope counts, not production-readiness certification. See [ROADMAP.md](ROADMAP.md).

## Deployment status

| Layer | Configured target | Verified 2026-10-03 | Qualification |
| --- | --- | --- | --- |
| Frontend | Cloudflare Worker at `https://softwarelifecycle.whf969.com` | Live SCR/Issue directories verified: Chinese/English, full statistics, pagination and invalid filters | Demo/test frontend, not evidence of production readiness |
| API | Render at `https://softwarelifecycle-api-test.onrender.com` | `/health/ready` HTTP 200, version `0.18.15`; Snapshot/Deployment probes rejected with HTTP 403 `read_only_mode` | Public sample API is current and remains read-only with OIDC disabled |
| Database | PostgreSQL behind the Render API | Ready at `0018_asr_evidence_index`; read-only SQL confirms revision and index | Sample/test data only; read-only schema/index inspection |
| Local stack | Docker Compose: PostgreSQL + FastAPI + Next.js | Configuration and YAML structure checked; Docker CLI was unavailable, so the stack was not started | Uses idempotent demo seed by default |

Historical actual-report rollout (2026-10-01): Render deployment `dep-dav0vf0473hc73a8vl10` was **live** for feature commit
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

- Repository and verified online API version: `0.18.9`. Current rollout evidence is recorded below.
- Required and verified online schema revision: `0018_asr_evidence_index`.
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
- Main/PR CI validates backend/PostgreSQL/migrations/frontend and reports stable CI acceptance; branch protection and CI-gated deployment remain separate configuration.
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

## Phase 6 eighth package — evidence and resource request preparation

Codex adds Impact Assessment, Acceptance-to-DVP Link and Resource preparation.
Exact issue/release/snapshot and SCR/criterion context can be prefilled from evidence
pages; criterion/DVP and judgment/assignment UUIDs are visible. Resource locations
are validated text references, never fetched/opened/uploaded. The helper follows
existing text trimming, explicit judgments and hyphenated audit UUID suffixes;
review/confirmation/stable copy and edit/context invalidation remain transport-free.
Eight of 14 forms now prepare requests; six forms, approved OIDC/session/target,
authenticated submission, uncertain outcomes and general correction/revocation remain.
No backend/API/schema change or migration; API 0.18.0, head 0017. Roadmap remains
34/44 (77%), Phase 6 3/5 (60%); preparation is not successful business execution.

Frontend tests: 111 passed, no skips (55 added evidence/reference cases). Next.js production build within OpenNext and Cloudflare Worker bundling passed; existing build/deprecation warnings remain. Complete Python 3.12 backend suite: 688 passed, 3179 warnings, no skips, including 103 real PostgreSQL 16.15 tests in a new isolated /tmp cluster. Six local SSR cases passed: impact/assignment/resource context, invalid entity type, oversized release UUID, ignored location prefill and Create entry. No migration or backend code change. Feature commit `5c95c961fb1907bf473dbec012adc4e1b66bf431` is pushed to main. Live Cloudflare UI verified all eight choices, exact Issue/release/snapshot and SCR/criterion prefill, explicit DVP selection, review confirmation, stable Impact copy, credential-URL rejection, inert local-path Resource preparation/copy and edit invalidation. No business submission was made. Health returned 200 with API 0.18.0 and database revision 0017_deployment_actual_version; Impact, Acceptance-to-DVP and Resource write probes each returned 403 read_only_mode. Unchanged Render backend deployment dep-dav0vf0473hc73a8vl10 remains live at bbd8a42b567c4f5b2c83017c570e47039442f3af. Cloudflare live behavior is verified; a provider deployment ID/commit binding was not available.

## Phase 6 ninth package — distribution-chain request preparation

Development mode: **Codex**. Starting main: `89d355f51a0b67c3e796f7e5a00941290e94fd54`.
Delivery, Distribution and Production Authorization extend the confirmed immutable
/commands export. Eleven of 14 forms prepare requests; no authenticated submission,
file sending, receipt acknowledgment or authorization approval is added.
Delivery requires an explicit package revision and 1–200 distinct frozen artifact
UUIDs, sorted as an immutable set; policy/recipient strings retain exact spelling.
Distribution targets an exact package UUID/revision. Authorization requires exact
distribution/release/customer/project IDs, purpose/site/line, and an explicit finite
positive PostgreSQL integer limit or unlimited selection. New Authorization records remain DRAFT.
Context links do not preselect artifacts/recipients/capacity or pin a release decision.
Expected audit events use existing EVT-DP-/EVT-DS-/EVT-PA- plus UUID hex.
No backend/API/schema/migration changes; head remains 0017, API 0.18.0.
Roadmap remains 34/44 (77%), Phase 6 3/5 (60%); remaining forms and provider-backed
submission, outcome recovery and broader correction/revocation remain open.
Frontend tests: 176 passed, no skips (65 added distribution-chain cases). Final Next.js/OpenNext Cloudflare Worker production build passed. Complete Python 3.12 backend suite: 688 passed, 3179 warnings, no skips, including 103 real PostgreSQL 16.15 tests in a fresh isolated /tmp cluster. Six local SSR checks passed for all three exact UUID targets, empty explicit defaults/ignored recipient-artifact-limit query prefill, missing/array targets and Create entry. Initial local next start hit the workspace networkInterfaces limitation; explicit 127.0.0.1 host resolved it without application changes. No migration. Feature commit `a8f299afddc5da23d8a5b00d53cb316b8519e46c` is pushed to main. Live Cloudflare UI verified eleven choices; exact release/package/distribution UUID entry links and visible frozen artifact/customer/project UUIDs; duplicate Delivery file rejection, review confirmation and stable copy after asynchronous clipboard completion; Distribution recipient edit invalidation; zero-limit rejection, finite export and explicit unlimited null only after clearing the limit; Authorization confirmation/copy. No business submission was made. Cloudflare live behavior is verified, but a provider deployment ID/commit binding is unavailable. Render connector confirms unchanged backend deployment dep-dav0vf0473hc73a8vl10 remains live at bbd8a42b567c4f5b2c83017c570e47039442f3af (API code 0.18.0). Current Render logs show GET /health/ready 200 at 2026-10-01T14:29:00Z. A read-only Render PostgreSQL query directly returned 0017_deployment_actual_version; provider inventory reports PostgreSQL 18, while local concurrency tests use 16.15. Direct API health-body and the three delivery/distribution/authorization 403 read_only_mode probes were blocked by workspace network policy, so fresh direct responses are not claimed. Public read-only configuration/code were unchanged; prior direct 403 evidence remains historical.

## Phase 6 tenth package — final request-preparation forms

Development mode: **Codex**. Starting main: `8196b214e33c5848200040f5ceaeaa2af3120353`.
Test Release, Deployment and Changeover complete preparation for all 14 current
commands. This is 100% of preparation forms, not authenticated submission or
production readiness. Test drafts require exact release/frozen snapshot UUIDs and
explicit SOFTWARE_TEST/BATTERY_TEST/CUSTOMER_TEST purpose; actor/reason follow
existing Pydantic trimming. Deployment requires exact authorization/line UUIDs,
creates PENDING and derives expected software from authorization at execution.
Changeover requires explicit source UUID; target is the deployment's expected release.
Its COMPLETED history does not prove physical flashing or update actual software.
Existing immutable confirmation/copy, edit/context invalidation and optional UTC
time semantics are reused. EVT-TR- uses hyphenated UUID; EVT-DPLOY-/EVT-CO- use hex.
No backend/API/schema/migration/login/transport/public setting changes; API 0.18.0,
head 0017. Roadmap remains 34/44 (77%), Phase 6 3/5 (60%). Provider/session/controlled
target, permission-aware selection, uncertain outcomes and broader corrections remain.
Verification: 214 frontend tests passed (38 added); production Next/OpenNext build passed; seven SSR context/default checks passed; full backend suite passed 688 tests including 103 real PostgreSQL 16 concurrency/integration tests, with no skips. No migration or backend contract change. Online verification after feature commit `210b124e3b2a0b3a04b9ddcb75f913e3a514d2a9`: Cloudflare serves all 14 forms; exact snapshot/authorization/deployment context, explicit purpose/source, UTC conversion, review invalidation and confirmed copy were exercised without business submission. Repeated Deployment copy retained the same body/key. `/health/ready` returned 200 with API 0.18.0 and revision 0017; Test Release, Deployment and Changeover POST probes each returned 403 `{"detail":"read_only_mode"}`. Read-only Render SQL independently confirmed `0017_deployment_actual_version`. Render backend remains live on bbd8a42; no backend redeploy was required. Cloudflare rollout was verified by live page behavior; a provider deployment ID was not available.

## Deployment detail bounded-read package — 2026-10-02

Developed from GitHub main `ae344d72a442d9c7533b77e0712a7d56b0f129e1`.
Approved identity/session/controlled target remain unconfigured, so this package
advances the documented legacy-consumer migration without opening write access.
The exact deployment profile replaces frontend legacy detail/provenance reads,
omits embedded histories, reports complete batch/changeover counts and links to
existing bounded catalogs. Decision scope uses the delivered release/snapshot.
Stored MATCH and observed UUID-pair state are shown separately; missing references
stay null. Old endpoints remain compatible. Counts are not permissions, capacity
or a transaction-consistent receipt; database count cost can still grow with rows.
Existing deployment_id indexes suffice; no new migration. API version is 0.18.1,
required Alembic head remains 0017_deployment_actual_version.
Only this consumer is migrated; remaining compatibility lists/details, approved
OIDC/session, authenticated submission/recovery, corrections and operations remain.
Roadmap remains 34/44 (77%), Phase 4 8/9 and Phase 6 3/5 (60%).
Verification: 11 new deployment-profile tests passed, including exact scope, missing references, legacy shape, stored/observed mismatch, 106/107 history counts without row loading and unchanged SQL query count. Full Python 3.12 backend suite: 699 passed, 3267 warnings, no skips, including 103 real PostgreSQL 16 tests. Frontend: 214 tests passed; production Next/OpenNext build passed. Four SSR checks passed for large history/exact catalog links, empty/missing delivery, unavailable profile and profile-only API calls. No migration. Online verification after feature commit `a3ea30e3bd0b8181c24f37a35289835c0d462626`: Render deployment `dep-dav9frnavr4c7396mtu0` is live for that commit. Health returned 200 with API 0.18.1 and database revision 0017_deployment_actual_version. Exact DEP-0081 profile returned 200, counts 1/1, MATCH observation and actual_version 0 without embedded histories; missing profile returned 404. Harmless empty Deployment and Batch POSTs both returned 403 read_only_mode. Read-only PostgreSQL SQL independently confirmed head 0017. Cloudflare live deployment detail and exact-deployment batch/exact-delivered-snapshot decision catalogs were verified in the browser; no business write was submitted. Recent Render error logs were empty. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is the frontend evidence.

## Authorization/distribution bounded-read package — 2026-10-02

Developed from GitHub main `d287ce83c73195d428b99673d15720ef6e7604f4`.
Two exact GET profiles replace authorization/distribution frontend legacy detail
reads. Complete counts cover all stored child statuses; arrays are omitted without
loading history rows. Existing bounded catalogs use exact returned parent UUIDs.
Exact scope, recipient, delivery revision, note/timeline and command preparation
context remain; null parent references are not guessed. Finite slot display uses
the full batch count and clamps at zero; unlimited stays null/no finite limit.
Counts are observations, not permission, reserved capacity or a write receipt.
API 0.18.2, no migration, required head 0017_deployment_actual_version. Existing
foreign-key indexes cover distribution/deployment counts, but batch authorization
count has no dedicated index and can scan rows; constant latency is not claimed.
Old endpoints and all 14 write contracts remain compatible. Public staging stays
read-only. Only these two additional consumers are migrated; delivery/release/other
legacy histories, OIDC/session, submission/recovery, corrections and operations remain.
Roadmap remains 34/44 (77%), Phase 4 8/9 and Phase 6 3/5 (60%).
Verification: 15 new profile tests passed, including exact/sibling scope, missing context, unchanged legacy shapes, read-only routes and 105 added histories with fixed query counts and no child payload loading. Full Python 3.12 backend suite: 714 passed, 3477 warnings, no skips, including 103 real PostgreSQL 16 tests. Frontend: 214 tests passed; production Next/OpenNext build passed. Seven SSR checks passed for exact links/revision/command UUIDs, all-status counts/zero clamp, unlimited/empty history, missing delivery, both unavailable profiles and profile-only API calls. No migration. Online verification after feature commit `c1348ed445918d5dfac225dd7386a79a83317a9b`: Render deployment `dep-dav9mlvlk1mc73be8h8g` is live for that commit. Health returned 200 with API 0.18.2 and database revision 0017_deployment_actual_version; read-only PostgreSQL SQL independently confirmed that revision. Exact PA-0081 and DIST-0326 profiles returned 200 with counts 1/1 and 1 respectively, exact parent references and no embedded histories; missing profiles returned 404. Harmless empty Authorization and Distribution POSTs both returned 403 read_only_mode. Cloudflare live details and exact-distribution authorization/exact-authorization batch catalog links were verified in the browser; no business write was submitted. Recent Render error logs were empty. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is the frontend evidence.

## Delivery revision bounded-read package — 2026-10-02

Development mode: **Codex**. Developed from GitHub main
`ec983d0434afd6e014c69d58e371f46ce323606c`. API 0.18.3 adds exact
package-number/revision profile and bounded artifact reads. The profile omits
child arrays, counts all stored items/distribution statuses, reports fixed
ALLOW/APPROVAL_REQUIRED/OTHER policy totals and distinct non-null control-reference
count. Unknown legacy decisions remain in OTHER, so summary size stays fixed.
The artifact page keeps recorded item/artifact UUIDs with null metadata when a
reference is missing, omits storage_reference, and sorts deterministically by
coalesced frozen filename, artifact UUID and item UUID. Frontend totals never derive
from the visible page; control reference text applies only to displayed rows.
Distribution history opens the existing catalog by exact package UUID. Existing
request-preparation/audit links stay exact; unavailable reads have no legacy fallback.
No schema migration: migration 0007 already indexes both package foreign keys and
uniquely identifies package number/revision. Counts and joined filename sorting may
still scan/sort many rows; bounded payloads do not imply constant database work.
Legacy reads and all 14 writes, scoped authorization, actor binding, transaction
locks and atomic audit remain compatible. Public staging stays read-only.
Roadmap remains 34/44 (77%), Phase 4 8/9 and Phase 6 3/5 (60%): release/other legacy
consumers, approved OIDC/session/controlled target, submission/recovery,
correction/revocation and operations remain pending.

Verification: 19 new delivery profile/artifact tests pass within the complete Python 3.12 backend suite: 733 passed, 3568 warnings, no skips, including 103 real PostgreSQL 16 migrated-schema concurrency/integration tests. Frontend: 214 passed, no skips; final Next/OpenNext Cloudflare production build passed. Eleven local SSR checks passed for full totals, exact UUID/revision links, first/next paging, empty/missing parents, lost metadata, beyond-end page, unavailable/invalid/array pagination, missing profile without fallback, invalid revision without API calls and profile/artifact-only reads. No migration. Online verification after feature commit `1efe0c28e2c5d68a36b00103b540329a38b1df04`: Render deployment `dep-dava0k6417fc73ds081g` is live for that commit (finished 2026-10-01T18:03:49Z). Health returned 200 with API 0.18.3 and revision 0017_deployment_actual_version; read-only PostgreSQL SQL independently confirmed that revision. DP-0226 revision 1 profile returned 200, exact package UUID, counts 3 artifacts/1 distribution, policy counts 2 ALLOW/1 APPROVAL_REQUIRED/0 OTHER and 1 distinct control. Two one-item artifact pages returned distinct exact UUIDs with total 3, next offsets 1/2 and no storage references. Missing exact revision returned 404; limit 101 returned 422. Empty Delivery/Distribution POSTs returned 403 read_only_mode. Cloudflare live detail, first/next artifact paging with unchanged full totals and exact-package distribution catalog were verified in the browser; no business writes were submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is frontend evidence. The first Render log query failed with a provider Loki 502/503; a subsequent query succeeded with no recent error logs, without application changes.

## Default Chinese and English interface — 2026-10-02

All 63 page entry points and all 14 preparation forms now use the shared bilingual
interface, default Chinese. The language-only cookie persists the selected preference;
UI switching preserves form state, request_id, raw enum values, JSON and exact links.
Stored evidence and identifiers stay original; known demo summaries have display translations. See [interface contract](docs/i18n.md).
API 0.18.3 and schema 0017_deployment_actual_version are unchanged; no migration.
Public staging remains read-only. Authenticated submission and OIDC configuration are
still pending. Roadmap checked scope stays 34/44 (77%); bilingual coverage is an
additional UI requirement, not completion of the Phase 6 submission gate.

Verification: frontend 292 passed (78 localization/coverage checks plus 214 command
checks); final Next/OpenNext production build passed. Full backend: 733 passed,
3568 existing warnings, no skips, including 103 real PostgreSQL integration/concurrency
tests. Local SSR: 126 page/language checks, invalid preference fallback and stable raw
input/option values for 14 forms. Live bilingual/persistence/immutable-request checks passed; rollout evidence is recorded in HANDOFF.md.

## Bilingual rollout verification — 2026-10-02

Development mode: **Codex**. Feature commit `3cf9aaaeefa1cd025878be84d56c0af272869c7d`
adds the shared interface; `38d66578d6f8ddae9c8d344b16ac878eae6c20d3` fills dynamic
state markers; final UI commit `9e30aaf374bc8b7f6a920902bd988e3794c4510f` fills demo
audit summaries and policy labels. All were pushed to main. No backend code/schema
change; API 0.18.3 and required database revision 0017_deployment_actual_version.

Final frontend: **292 passed**, no skips; Next/OpenNext Cloudflare production build
passed. Full backend: **733 passed**, 3568 existing deprecation warnings, no skips;
103 collected real PostgreSQL migrated-schema integration/concurrency tests are included.
Local production SSR: 126 existing-route/language checks, invalid preference fallback,
14 forms' identical raw input/option values. Additional populated Snapshot/Dashboard
checks in both languages verify state/policy/summary translation while preserving exact
UUIDs, hashes, filenames and unknown authored evidence; bilingual 404 recovery passes.

Live Cloudflare UI was verified after the final UI commit: missing preference first
rendered Chinese; switching immediately updated text/title, preserved target, reviewed
request ID and confirmation state, and produced byte-identical confirmed clipboard JSON
in both languages. Clipboard was compared after async copy completion. English selection
survived reload and navigation; Chinese was restored. SNAP-008 shows current/frozen,
confidentiality, component and AI-policy translations with unchanged UUIDs/hashes/files.
Dashboard demo activity summaries are Chinese. No business command was submitted.
Cloudflare provider deployment ID/commit metadata is unavailable through installed
tools; live final feature behavior is the frontend deployment evidence.

Render's existing backend deployment `dep-dava0k6417fc73ds081g` remains live for
`1efe0c28e2c5d68a36b00103b540329a38b1df04`; this frontend-only package did not
redeploy unchanged backend code. Health returned HTTP 200 ready/API 0.18.3/head 0017;
read-only PostgreSQL SQL independently confirmed `0017_deployment_actual_version`.
Empty Snapshot and exact Deployment Batch POST probes returned HTTP 403 read_only_mode.
Public staging remains read-only. Sampled browser errors came from the browser metadata
extension, not the application source; no application runtime error was observed in
that sample. The unrelated `frontend/app/activity/page 2.tsx` was absent and was not
created, adopted or removed.

Current-page bilingual coverage is complete; roadmap scope stays **34/44 (77%)**.
Phase 4 8/9, Phase 5 8/9, Phase 6 3/5, Phase 7 0/6. Remaining preparation versus
submission distinction remains: OIDC/session/controlled target, submission/recovery/
result trace, broader append-only correction/revocation, remaining bounded consumers
and production operations. Planning estimate remains 8–12 more focused packages to
controlled internal use, 16–24 total to a production-ready review, subject to approvals.
Suggested next code package: migrate remaining release detail/trace consumers to bounded
profiles/catalogs while approved identity/session and controlled target are specified.

## ASR downstream bounded-read package — 2026-10-02

Developed from GitHub main `7b2ae568e4b571eb59fe1d77e8d57899ea86103b`. API 0.18.4 adds
`GET /api/v1/releases/application/id/{release_id}/downstream-summary` with six
all-status history counts and separate actual-release/batch-release observations.
It retains the old exact stored-parent chain: deliveries belong to release;
distributions belong to those packages; authorizations belong directly to release;
deployments belong to those authorizations; changeovers and batches belong to those
deployments. Expected/actual/batch release mismatches remain visible.

`authorization_release_id` on all three production catalogs filters the release of
the deployment's stored authorization. Existing `release_id` semantics remain;
combined filters intersect. The ASR page uses exact UUID links into bounded catalogs,
retains the exact Snapshot preparation target, defaults to Chinese and supports
English. Missing/wrong-ID summaries show unknown counts without an unbounded fallback.
The page no longer calls legacy `/downstream`; its profile/evidence calls and other
legacy consumers are still unbounded. This is a partial Phase 4 migration, not its exit.

Seven cold SQL queries use count/sum/subqueries without loading child rows or growing
ID arrays. Existing foreign-key indexes suffice; no schema change, head remains
`0017_deployment_actual_version`. Counts can scan many rows and separate READ COMMITTED
queries are not a transactionally consistent receipt or reserved quota. Release UUID
observations do not establish snapshot matches, physical flashing, approval or permission.
All 14 command contracts, exact role/actor binding, retry locks and atomic audits remain
unchanged; public staging stays read-only. Roadmap remains 34/44 (77%), Phase 6 3/5.

Verification: 17 new summary/scope tests passed within the complete Python 3.12 backend suite: **750 passed, 3915 warnings, no skips**, including **104 real PostgreSQL 16.15 tests**. The new migrated-PostgreSQL test verifies aggregates, mismatch-preserving catalog scope and no audit writes; the existing real lock/retry/quota/rollback tests also passed. Frontend: **292 passed, no skips**; final Next/OpenNext Cloudflare production build passed. Eight local SSR verification groups passed for Chinese/English full totals and exact links, empty/unavailable/wrong-ID summaries, three catalogs preserving the scope through API/filter/first-next/kind links and no legacy downstream fallback. Single Alembic head 0017 and PostgreSQL SQL generation passed. No migration.

Next package: bound ASR frozen-manifest / current-snapshot DVP evidence consumers,
then remaining SSR/profile consumers. Approved OIDC/session, controlled target,
authenticated submission/recovery/results, broader corrections and production operations
remain. Planning range stays 8–12 focused packages to controlled internal use and
16–24 total to production-ready review, conditional on provider/environment/policy approvals.
Online verification after feature commit `338a3231315a7a7623086f0ca347ddbccd265282`: Render deployment `dep-davjddgjo6nc738ln230` is live for that commit (finished 2026-10-02T04:45:42Z). Health returned 200, API 0.18.4, database revision 0017_deployment_actual_version; independent read-only Render SQL confirmed that revision. Exact ASR 2.3.4 summary returned six counts of 1, actual same/different/unreported 1/0/0 and batch same/different 1/0. Three authorization_release_id catalogs returned total 1 and exact linked record UUIDs. Missing summary returned 404; malformed authorization_release_id returned 422. Empty Snapshot and exact Deployment Batch POST probes returned 403 read_only_mode. Cloudflare live Chinese summary, English switching, six scoped links, exact Snapshot preparation UUID, English persistence through catalog navigation, Batch filter submit and cross-kind Changeover navigation preserving scope were verified in the browser. The sample has only one row per scope, so next-page behavior is local SSR/test evidence, not live multi-page evidence. No business write was submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live new feature behavior is frontend evidence. Initial browser navigation/frame-tree probes timed out; the same browser's documented tab/DOM API recovered without changing site or network settings. Public staging remains read-only.

## ASR pinned evidence pagination — 2026-10-02

Developed from GitHub main `1e82bd83bf16145393fec2b228f19b3db6d3f4ee`. API 0.18.5 adds fixed
`evidence-summary` and bounded `evidence/artifacts` / `evidence/executions` reads.
The summary selects the latest Snapshot or an explicit snapshot_id. Pages require
that exact UUID and reject snapshots of other releases. The ASR page no longer calls
legacy `/evidence`; it selects one snapshot then paginates both tables independently.
First/next links retain evidence_snapshot_id, evidence_limit and the other table's
offset. Invalid/array parameters show unavailable/unknown rather than resetting scope
or falling back. No-snapshot is explicitly separate from unavailable summary.

DVP executions rank by execution_no descending (then timestamp/UUID) within each
item UUID on the exact release/snapshot. Higher numbers on other snapshots/releases
do not replace selected evidence. Different plans with the same item_no remain
separate; missing DVP metadata retains execution/item UUIDs with an explicit marker.
Artifact order is component/filename/UUID; execution order is item number (null last),
item UUID/execution UUID. No storage_reference or actual_result body is selected.
Latest execution evidence is not required-DVP coverage, readiness or approval.

Migration `0018_asr_evidence_index` adds one non-unique B-tree index on
`dvp_executions(release_id, snapshot_id, dvp_item_id, execution_no)`, with matching ORM
metadata. No business data/constraints/history are changed. The required health schema
and staging checker advance to 0018. Existing Snapshot artifact index already suffices.
Bounded payload/query count does not mean constant database work: totals/window sorting
may scan many rows; offset pages and multi-query counts are READ COMMITTED observations,
not a consistent write receipt. Pinning prevents snapshot drift, not concurrent DVP
history shifts within that snapshot. The release overview may refer to a newer Snapshot.

All new UI strings support default Chinese/selectable English. Exact preparation UUID,
request-ID semantics, all 14 command scopes/actors/locks and atomic audits remain;
public staging stays read-only. Legacy evidence and ASR profile coverage/SSR/other
compatibility consumers are still unbounded. Roadmap remains 34/44 (77%), Phase 6 3/5.

Verification: 20 new evidence tests passed within the complete Python 3.12 backend suite: **770 passed, 4281 warnings, no skips**, including **105 real PostgreSQL 16.15 tests**. Coverage includes exact/sibling/wrong-type scope, missing/empty snapshots, stable duplicate ordering, newest execution per item UUID on only the selected release/snapshot, duplicate item numbers across plans, missing metadata retention, pinned pagination after a newer Snapshot and 105-row growth with unchanged SQL query count, bounded row projections and no private payload columns. Real PostgreSQL verifies the window query, no audit write, index columns and downgrade/upgrade without lost execution rows; existing concurrency/replay/quota/rollback tests also passed. Frontend **293 passed, no skips**, final Next/OpenNext production build passed. Seven local SSR groups passed across Chinese/English for full counts, missing metadata, independent first/next offsets with pinned snapshot and exact command UUID, historical pin, beyond-end/invalid-array pages, unavailable/no-snapshot summary stopping page reads and no legacy evidence request. Single Alembic head, PostgreSQL full upgrade SQL and 0018-to-0017 downgrade SQL passed.

Next: bound ASR profile coverage and remaining SSR/component/policy/snapshot consumers;
then approved OIDC/session/controlled target, submission/recovery/results, append-only
correction/revocation and production operations. Estimate remains 8–12 focused packages
to controlled internal use, 16–24 total to production-ready review, conditional on approvals.
Online verification after feature commit `26a170653e3892654ea23391cb95a0a41525585c`: Render deployment `dep-davjra8473hc73f79r90` is live for that commit (finished 2026-10-02T05:15:15Z). Health returned 200 / API 0.18.5 / 0018_asr_evidence_index. Independent read-only Render SQL confirmed both Alembic revision 0018 and the exact non-unique B-tree index columns. Exact ASR 2.3.4 summary returned SNAP-008 UUID c6f38c25-c42e-4bdb-8327-e16f7e85dd7b, 4 artifacts, 3 latest item executions and 1 other-snapshot execution. Two one-item pages for each collection returned distinct UUIDs with unchanged full totals and no private storage/result fields. Malformed snapshot/oversized limit returned 422; another release with this snapshot returned 404. Harmless empty Snapshot and exact Deployment Batch POSTs returned 403 read_only_mode. Cloudflare live Chinese evidence summary and one-item pages were verified: artifact second page retained DVP first page, then DVP second page retained artifact second page and exact snapshot; English switching retained both offsets, UUID, totals and raw hashes; Chinese restored for the final proof. Exact Snapshot preparation target remained the release UUID. No business write was submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live new feature behavior is frontend evidence. Public staging remains read-only. The initial combined read-only SQL probe was rejected because the connector accepts one prepared statement; two separate read-only queries succeeded without database mutation.

## Release coverage SQL aggregates — 2026-10-02

Developed from GitHub main `a06b54ef6edaccc84ee585fd252369a85f6def45`. API 0.18.6
replaces TraceabilityService's materialized SCR/ChangePoint/issue/link IDs and full
DVP history with relational CTE scopes and one aggregate result. Latest Snapshot
selection now has SQL LIMIT 1. All consumers of this service benefit, including ASR
profiles, SSR/passport coverage and readiness; their other reads are not thereby bounded.

Scope and response fields are unchanged: software SCRs, plus exact project or global
project-null SCRs when APPLICATION detail exists; legacy missing detail still includes
all SCR projects on that software. Change points, linked issues and required DVP UUIDs
retain distinct/set-union semantics. No Issue/DVP metadata join hides recorded bindings.
Execution counts use only the exact release and selected Snapshot and required DVPs.
An item with any PASS on that Snapshot remains passed even if a later execution fails;
this coverage contract differs from the evidence table's latest-result ranking. Explicit
missing/foreign snapshots do not fall back; missing release and empty denominator
behavior remain unchanged. Coverage counts execution presence, not approval or permission.

No migration: the existing tables, association primary keys and 0018 release/snapshot
execution index support the query; Alembic head and required schema stay
`0018_asr_evidence_index`. Fixed result size/query count bounds application transfer
and child ORM loading, not database scan cost. The aggregate statement has one database
statement snapshot; separately selected parent/Snapshot metadata and other profile reads
remain READ COMMITTED observations, not a consistent command receipt or quota reservation.
All 14 command contracts, scopes, actors, retry locks and business/audit atomicity remain.
Public staging stays read-only; UI remains default Chinese/selectable English.

Verification: 14 new coverage tests passed within the full Python 3.12 backend suite: **784 passed, 4873 warnings, no skips**, including **106 real PostgreSQL 16.15 tests**. Tests cover union/distinct/any-PASS semantics, exact release/snapshot exclusion, old/empty/invalid/missing selection, software/project/missing-detail scope, recorded missing metadata, 120-item growth with fixed three cold STANDARD queries and no child ORM/private text, migrated PostgreSQL aggregate results and no audit write. Existing real retry/concurrency/quota/rollback/authorization regressions passed. Frontend **293 passed, no skips**; final Next/OpenNext Cloudflare production build passed. Single Alembic head and PostgreSQL full upgrade SQL generation passed; no new migration.

This is another partial Phase 4 migration, not its exit. Roadmap stays 34/44 (77%),
Phase 6 3/5 (60%). Next: remaining SSR/component/policy/snapshot/history consumers;
then approved OIDC/session/controlled target, submission/recovery/results, append-only
correction/revocation and production operations. Planning remains 8–12 focused packages
to controlled internal use and 16–24 total to production-ready review, conditional on approvals.

Online verification after feature commit `81e4e59b284b5ac6e75527d816278937089c35ad`: Render deployment
`dep-davk6l6q1p3s73dcp5p0` is live for this commit (finished
2026-10-02T05:39:20.750158Z). Health returned 200 / API 0.18.6 /
0018_asr_evidence_index; independent read-only Render SQL confirmed the revision.
Exact ASR 2.3.4 `/coverage` and application profile coverage were compared field by
field with the saved API 0.18.5 baseline and matched: SNAP-008 UUID
c6f38c25-c42e-4bdb-8327-e16f7e85dd7b, change points 2/2, issues 1/1,
required DVPs 3, executed 2, passed 2, coverage 100/100/67 and snapshot_match=true.
Missing-release coverage returned 404. Harmless empty Snapshot and exact Deployment
Batch POST probes returned 403 read_only_mode. Cloudflare browser refresh after the
backend went live showed those same cards; English switching retained counts, exact
preparation UUID, pinned snapshot and both table offsets, then Chinese was restored.
No frontend source changed or separate frontend rollout was needed. Cloudflare provider
commit/deployment metadata was not inspected; this is live availability/compatibility
evidence. No public business write was submitted; staging remains read-only.

## Bounded SSR detail collections — 2026-10-02

Developed from GitHub main `44dceb069fcd651c8f1343d41d3b50379cecd4fe`. API 0.18.7 adds
`/api/v1/releases/standard/id/{release_id}/summary`, `/components` and `/applications`.
The SSR page replaces its legacy all-child profile request with parent metadata/full
counts and two independently paginated projections. Exact STANDARD UUID parents are
required; missing/wrong-type parents return 404. Pagination defaults to limit 50,
accepts 1–100 and offset 0–100000, rejects unknown filters/malformed UUIDs with 422.
The summary accepts no query fields. Existing legacy profile shape remains unchanged.

Components retain stored release UUID membership and UUID ascending order; missing
component definitions remain visible with null code/name. Applications follow only
ApplicationReleaseDetail.standard_base_release_id, join their stored Release UUIDs,
retain all statuses/software associations and order timestamp descending/null-last,
then UUID descending. No version/name inference or new project/customer/status filters.
Missing referenced releases remain excluded as in the old profile. Declaration/baseline
membership is not frozen Snapshot evidence, approval or authorization.

Frontend `release_limit`, `component_offset`, `application_offset` keep the other
collection's offset through first/next links. Invalid/array parameters are forwarded
as invalid, not reset. Failed/wrong-UUID summaries stop child reads; failed/wrong-parent
pages show unavailable while the other table remains readable, with no legacy fallback.
All new labels are bilingual, default Chinese; raw IDs, commits and preparation target
remain exact. Empty/beyond-end pages retain full counts. Counts/pages are separate
READ COMMITTED observations; concurrent additions can shift offset pages. Parent notes
remain a single potentially large field; fixed child rows are not a total-byte or
constant-time query guarantee.

No migration; existing tables/keys suffice for these projections, required revision
and sole Alembic head stay `0018_asr_evidence_index`. Legacy foreign-key indexing is
unchanged; database scans/counts/sorts may grow and measured plans should guide indexes.
All 14 write scopes, trusted actors, request-ID retry locks and atomic audits stay.
Public staging stays read-only. Unrelated activity/page 2.tsx is absent and untouched.

Verification: 16 new backend cases passed within the full Python 3.12 suite: **800 passed, 5180 warnings, no skips**, including **107 real PostgreSQL 16.15 tests**. Coverage includes legacy metadata/count parity, exact/sibling/same-version scopes, stable duplicate ordering and beyond-end totals, missing component metadata retention/missing referenced release exclusion, empty/optional metadata, strict HTTP limits/unknown filters/read-only denial and 120-row growth with fixed SQL shape/count, bounded projections and no child ORM. Real PostgreSQL checks totals against the pre-existing legacy fixture plus 120 new bindings, distinct one-row pages and no audit write; existing lock/replay/quota/rollback/actor/authorization tests pass. Frontend **300 passed**; final Next/OpenNext Cloudflare production build passed. Seven local production SSR groups passed: Chinese/English full totals, independent first/next links and exact preparation UUID, unavailable/foreign summaries stopping child reads, invalid array offset preserving the other table, beyond-end pages and foreign child scope rejection. Single Alembic head and PostgreSQL full upgrade SQL generation passed; no new migration.

Partial Phase 4 migration only; roadmap stays 34/44 (77%), Phase 4 8/9 and Phase 6 3/5.
Next: ASR component/baseline declarations and remaining policy/snapshot/history/passport
consumers, then approved OIDC/session/controlled target, authenticated submission/
recovery/results, append-only corrections/revocations and production operations.
Estimate remains 8–12 focused packages to controlled internal use, 16–24 total to
production-ready review, dependent on approvals and scope.

Online verification after feature commit `419d1481b9a03d56ec5d273ebaef48176688e07b`: Render deployment
`dep-davqgvbm8hqs73cbqj90` is live for this commit (finished
2026-10-02T12:51:00.344602Z). Health returned 200 / API 0.18.7 /
0018_asr_evidence_index; read-only Render SQL independently confirmed revision 0018.
SSR 5.1.12 UUID 66f12b8f-9efd-4482-977b-549bb0cf7f50 summary metadata matched the saved
legacy profile field by field, with full counts 0 components and 2 applications.
Two one-row ASR pages returned distinct stored UUIDs/statuses with total 2; the set and
fields matched legacy records. Component empty page retained total 0. Unknown summary
filter and limit 101 returned 422; an APPLICATION parent summary returned 404.
Harmless empty SSR Snapshot and exact Deployment Batch POSTs returned 403 read_only_mode.
Cloudflare live new SSR UI was verified in Chinese: full counts 0/2 and first ASR page;
next ASR page changed 2.3.3 to 2.3.4 while preserving release_limit=1 and component_offset=1.
English switching preserved count, both offsets, exact preparation UUID and raw source
commit demo512; Chinese restored for the final proof. The sample has no SSR components,
so component multi-page behavior is local/real PostgreSQL test evidence, not a live claim.
No public business write was submitted. Cloudflare provider commit/deployment metadata
was unavailable; live new behavior is frontend rollout evidence. Public staging remains
read-only. One PostgreSQL test expectation initially missed a pre-existing fixture
component; it was corrected against the legacy baseline and the full rerun passed.

## ASR component/baseline consumer migration — 2026-10-02

Developed from GitHub main `ec4f0ec308a6a982b91fd03842425f86a2caa99f`. API 0.18.8 adds
an exact APPLICATION parent summary and independent bounded declaration/unlinked-base
pages. The old bare components endpoint remains unchanged for compatibility. Full
counts use SQL aggregates; projections use LIMIT/OFFSET and stable component UUID
ascending order, with no child ORM loading or growing Python ID collections.

A valid baseline link requires the recorded base component UUID to belong to the
resolved stored baseline Release and have the same component definition UUID. Null
base versions remain valid links. Foreign/mismatched/orphan pointers remain INVALID;
missing pointers remain NOT_RECORDED. Inactive/missing definition metadata is retained.
Unlinked baseline membership uses a scoped NOT EXISTS across every ASR declaration:
links on later pages count, duplicate valid links hide a baseline row once, invalid
links and other ASR declarations cannot hide it. No name/version/delta inference and
no new inheritance, snapshot, approval or authorization capability is introduced.
Missing detail/base preserves legacy null-base semantics; stored base associations
are not newly filtered by type, software or status.

The bilingual component page now reads only summary and two paginated APIs, preserves
component_limit/declaration_offset/unlinked_offset independently, forwards invalid
parameters, shows full counts and per-table unavailable/empty states, and never falls
back to the unbounded endpoint. Summary failure/wrong release stops child reads;
release_id and base_release_id must match the summary context on each child response.
This detects a changed baseline but does not pin a transaction or consistent read
receipt: READ COMMITTED counts/pages can change between requests. Counts/sorts and the
anti-join can still scan growing data; constant SQL shape/bounded transfer do not prove
constant database cost. Future indexing requires measured PostgreSQL query plans.

No migration; required head stays 0018_asr_evidence_index. All 14 command contracts,
request-ID replay/conflict, locks, exact authorization, authenticated actor binding and
atomic business/audit writes are unchanged. Public staging remains read-only. Roadmap
stays 34/44 (77%), Phase 4 8/9 and Phase 6 3/5; remaining policy/snapshot/history/passport
consumers prevent declaring the compatibility migration complete. Next address those
remaining consumers, then approved identity/session and controlled submission/recovery.
Estimates remain conditional: 8–12 focused packages for controlled internal use;
16–24 total for production acceptance, including operations and policy/provider inputs.

Verification: 19 new backend cases passed in the complete Python 3.12 suite:
**819 passed, 5263 warnings, no skips**, including **108 real PostgreSQL 16.15 tests**.
Tests cover legacy parity, null-version/inactive-definition links, duplicate valid links,
foreign/wrong-definition/orphan pointers, same-version sibling scope, missing detail/base,
legacy wrong-base-type semantics, exact parent rejection, stable independent pages,
beyond-end totals, strict HTTP bounds/unknown fields/read-only rejection, and 120-row
SQL growth with identical statements and bounded projections/no component ORM loads.
Real migrated PostgreSQL proves global anti-association membership across pages, exact
stored links, fixture-aware totals and no audit writes; existing concurrency/retry/
quota/rollback/actor/grant regressions all pass. Frontend **307 passed**; final Next/
OpenNext production build passed. Seven actual local production SSR groups passed:
Chinese/English counts and independent links, unavailable/foreign summary stopping child
reads, array offset rejection preserving the other table, empty pages, and changed
baseline response rejection. Single Alembic head and full PostgreSQL upgrade SQL
succeeded, without a new migration. Existing warnings are deprecations/collection notices.

Online verification after feature commit `6a48e36141530efc2787087f964abfcb893e816e`:
Render deployment `dep-davrl92vcj2c738jvnk0` is live for that commit (finished
2026-10-02T14:08:35.737105Z). Health returned HTTP 200 / API 0.18.8 /
0018_asr_evidence_index; independent read-only Render SQL confirmed that revision.
ASR 2.3.4 UUID 271334c3-9a99-4dc0-a7dc-75ba5754377b summary matched saved legacy
metadata/counts (2 declarations, 0 unlinked baseline components). Two one-row declaration
pages were distinct, in legacy UUID order, with identical fields/statuses. Empty and
beyond-end pages retained full totals; unknown summary filter/limit 101 returned 422,
STANDARD parent returned 404. Harmless empty Snapshot and exact Deployment Batch POSTs
both returned HTTP 403 read_only_mode. No business record was submitted.
Cloudflare live component UI was verified in Chinese with full counts 2/0; next page
changed Main Application to Calibration/CAL-32 and retained component_limit=1 plus
unlinked_offset=1. English switching retained both offsets, counts, raw versions and
link state; Chinese was restored. Baseline has zero components in this sample, so
unlinked-baseline multi-page/link exclusion behavior is supported by local and real
PostgreSQL tests, not a live multi-row baseline claim. Cloudflare provider deployment
ID/commit metadata was unavailable; visible live feature behavior is frontend evidence.
Working tree is clean, main push succeeded, unrelated duplicate activity file untouched.

## Bounded ASR frozen policy consumer — 2026-10-03

Developed from GitHub main `e9a2b911d38ebce07af0a1aad2870c69eeb3e90c`, in Codex mode.
API 0.18.9 adds exact APPLICATION policy summary, artifact projections and separate
recipient-rule pages. Legacy bare snapshot-policy remains unchanged. Summary defaults
to the highest snapshot_number (all stored statuses, preserving legacy selection), or
an explicitly selected snapshot UUID belonging to that exact Release. Child reads
require the snapshot UUID; optional rule artifact UUID must belong to that snapshot.
No version/name lookup, storage-reference exposure or write service changes.

Full recording counts are SQL aggregates: non-empty SHA strings (including whitespace
as before); policy recorded for INTERNAL_ONLY or any stored rule, regardless of rule
decision. These are recording indicators, not hash validation, complete policy review,
permission or approval. Rule totals count stored rows, including duplicate null-recipient
rules; internal-only files stay externally denied even with a recorded ALLOW rule.
Artifact pages return per-artifact rule_count without embedded growing rule arrays.
Rules use exact snapshot/artifact joins; orphan and foreign-snapshot rows cannot leak.
Stable ordering uses component/filename/artifact UUID then recipient/purpose/coalesced
recipient code/decision/rule UUID. Strict limits, unknown-query rejection and empty
beyond-end pages retain totals. Counts and projections remain READ COMMITTED observations.

The Chinese-default/English page pins every artifact/rule/navigation request to the
summary Snapshot UUID. Artifact and rule offsets are independent; selecting/clearing
an artifact resets only the rule offset, preserving the artifact offset. All-snapshot
rule counts and filtered matching counts are distinct. Requested summary pin, child
release/snapshot and rule-filter context mismatches are rejected; failures never fall
back to legacy bulk reads or become fabricated zero counts. A newer snapshot does not
move pinned pages; Read latest policy clears selection. No consistent write receipt,
authenticated submission or distribution authorization is added.

No migration: snapshot artifact and rule foreign-key indexes already exist, required
head 0018_asr_evidence_index stays unchanged. Full SQL totals/sorts can still scan growing
data; fixed statement count and bounded transfer do not establish constant DB cost.
All 14 write contracts, replay/conflicts, PostgreSQL locks, exact role checks, trusted
actor and atomic domain/audit writes are unchanged. Public staging remains read-only.

Verification: **839 backend tests passed**, **5320 existing warnings**, no skips, under
Python 3.12, including **111 real PostgreSQL 16.15 tests**. Twenty new backend cases
cover recording parity, null/empty/whitespace values, INTERNAL_ONLY/ALLOW observations,
duplicate null-recipient rules, exact release/snapshot/artifact rejection, pinned pages
across a newer snapshot, stable ordering, empty/no-snapshot/invalid selections, HTTP
bounds, orphan exclusion and 120-artifact/360-rule growth with identical SQL statements,
bounded projections and no child ORM loads. Real migrated PostgreSQL verifies recording
counts, null rule ordering, exact filtered totals, cross-snapshot artifact denial and
no audit writes; existing lock/replay/quota/rollback/actor/grant regressions pass.
Frontend **316 tests passed**; final Next/OpenNext Cloudflare production build passed.
Ten local actual production SSR groups passed for both languages/full counts/external
internal-only denial, independent pinned links, summary failure/scope/pin, no snapshot,
invalid rules pagination/filter, empty pages, foreign child context and historical pin.
Single Alembic head and complete PostgreSQL upgrade SQL generation passed, no migration.

Roadmap remains 34/44 (77%), Phase 4 8/9, Phase 6 3/5. Snapshot history already has
bounded cursor pagination; remaining exact manifest/comparison, other policy/rich-profile,
legacy catalogs and passport consumers keep compatibility migration incomplete. Next
bound exact frozen manifests/rules, then passport consumers; approved OIDC/session,
controlled submission/recovery/corrections and operations remain. Estimates remain
conditional: 8–12 focused internal-use packages, 16–24 total production-review packages.

Online verification after feature commit `a6c09a2cab8e7c178e52eb897f24150b3cbbf479`:
Render deployment `dep-db005snf3r2c73ailutg` is live for that commit (finished
2026-10-02T19:16:52.024429Z UTC / 2026-10-03 Asia/Shanghai). Health returned HTTP 200 /
API 0.18.9 / 0018_asr_evidence_index; independent read-only PostgreSQL SQL confirmed
that revision. Exact ASR 271334c3-9a99-4dc0-a7dc-75ba5754377b selected SNAP-008 UUID
c6f38c25-c42e-4bdb-8327-e16f7e85dd7b. Counts 4 artifacts/4 SHA recorded/4 policy
recorded/3 rules matched the saved legacy response; four distinct one-row artifact
pages and three distinct one-row rule pages matched every legacy metadata/rule field.
Selected artifact rule totals and empty no-rule artifact passed; foreign artifact 404,
missing pin 422, invalid/unknown filters 422, wrong parent 404 and beyond-end total
retention passed. Explicit pinned summary matched default summary. Snapshot and exact
Deployment Batch empty POST probes both returned HTTP 403 read_only_mode. No business
write was submitted. Recent Render error logs after rollout were empty.

Cloudflare live new Chinese UI showed counts 4/4/4/3 and pinned Snapshot UUID/hash.
Artifact next changed CustomerA_BMS.a2l to BMS.elf while retaining rule_offset=1;
BMS.elf retained external distribution denial. Rule next changed HEX to DBC while
retaining artifact_offset=1 and the same Snapshot. English switching preserved all
counts, raw identifiers/hashes/files and both offsets. Exact ELF UUID selection reset
only rule_offset to 0, preserved artifact_offset=1 and displayed 0 matching rules.
Clearing the filter restored total 3 on the same snapshot/artifact page; Chinese restored
for the final screenshot. Cloudflare provider deploy ID/commit metadata unavailable;
visible new behavior is frontend rollout evidence. A newer snapshot/pinned historical
read is demonstrated locally and in tests, not by creating staging records.
Main push succeeded, working tree clean, unrelated duplicate activity file untouched.

## Exact Snapshot detail development — 2026-10-03 (Asia/Shanghai)

Developed from GitHub main 27ce7b773f759fb8c6fd69f35395ab488fb7a8c1 using Codex.
API 0.18.10 adds exact Snapshot summary, independently bounded artifact/rule pages and
validated exact file filtering shared with existing ASR SQL projections. UI preserves
full hashes, historical/current identity and immutable preparation/resource/history/
compare links. Search now selects the exact frozen artifact before its retained anchor;
selection/clear resets both offsets, normal paging preserves the other. Parent/name/
UUID/filter mismatch fails closed, no bulk fallback. Chinese remains default and all
new content supports English. Bare legacy detail/comparison remain compatible.

No migration; single head 0018_asr_evidence_index, complete PostgreSQL upgrade SQL
validated. Full backend: 850 passed, 5367 existing warnings, no skips; 110 real
PostgreSQL 16.15 tests, 65 backend modules. Eleven new exact scope/count/order/growth/
HTTP/committed-newer-Snapshot cases. Frontend 327 passed; Next/OpenNext production
build and 10 actual production SSR groups passed. All write request-ID/scope/trusted
actor/locking/atomic audit contracts remain unchanged. Unrelated duplicate activity
file was neither recreated, adopted nor removed.

Progress: ROADMAP acceptance items remain 34/44 (77%), Phase 4 8/9 and Phase 6 3/5.
New docs/read-consumer-migration.md identifies 17 named consumer scope groups, with
11/17 already complete at the reviewed baseline and 12/17 (71%) now complete. This
new fine-grained counter explains consumer progress without prematurely checking the
remaining broad Phase 4 item. Five pending groups: comparison, ASR passport, readiness/
compatibility policy, release catalogs/resolver, other rich profiles/domain catalogs.
Next comparison, then passport and remaining reads; identity/session/submission/
recovery/corrections/ops follow. Conditional ranges 8–12 focused internal-use packages,
16–24 total production-review packages; no commitment or staging write enablement.

Online verification after feature commit `608f3f3905d6fda88ff9137a01f2617afc0a88b8`:
Render `dep-db00hi5g1s2s7388gj7g` is live for that commit, finished
2026-10-02T19:41:50.556123Z UTC / 2026-10-03 Asia/Shanghai. Health HTTP 200,
API 0.18.10 and schema 0018_asr_evidence_index; independent read-only database query
confirmed the same head. SNAP-008 UUID c6f38c25-c42e-4bdb-8327-e16f7e85dd7b retained
all saved legacy identity fields, four files and three rules. Four distinct one-row
file pages and three one-row rule pages matched every legacy public metadata/rule
field. All four exact file selections, no-rule ELF, missing/foreign pins/artifacts,
unknown/invalid queries and beyond-end totals passed. Snapshot and Deployment Batch
empty POST probes returned HTTP 403 read_only_mode; no business write submitted.

Cloudflare live new default Chinese exact page showed full Snapshot/file hashes,
four-file/three-rule totals and bounded tables. File next A2L→ELF retained rule offset
0, exact Snapshot UUID and internal-only external denial; rule next A2L→HEX retained
file offset 1 and the same Snapshot. English switching retained all raw identities/
full hashes and both offsets. Exact ELF selection reset both offsets, showed one file
and zero matching rules. Clearing restored all files/rules on the same Snapshot;
Chinese restored for final screenshot. Provider frontend deployment ID/commit metadata
was unavailable; observed new UI behavior is frontend rollout evidence. A new Snapshot
committed between reads is tested in local PostgreSQL, not created in staging.
Feature and verification documentation pushed to main; working tree clean. Unrelated
duplicate activity file untouched. Comparison and other ledger gaps remain pending.

## Snapshot comparison migration — 2026-10-03 (Asia/Shanghai)

Developed with Codex from GitHub main 2f34a9aae5ac8685464555a73f48026d8e441c65.
API 0.18.11 adds exact same-release comparison summaries and required-pair-UUID bounded
file pages. SQL rejects duplicate file identities anywhere, compares frozen fields and
counted recipient-rule multisets, and filters/pages file differences. Rule UUID/order
are ignored, NULL/empty codes and duplicate counts preserved; this avoids the legacy
helper's tied NULL/empty sorting ambiguity, while the legacy API remains unchanged.
No private references/nested rule arrays/full child ORM collections. UI keeps full
hashes, metadata/status and complete summary counts, defaults Chinese, supports English,
pins both Snapshot identities on navigation and links per-side exact paginated rules.
Failed/mismatched file pages retain summary without substituting data.

Complete backend Python 3.12 tests: 875 passed, 5456 existing warnings, no skips,
including 111 real PostgreSQL 16.15 tests; 66 backend test modules. Twenty-five new
field/policy/duplicate/scope/pin/count/growth/HTTP/PostgreSQL cases. Frontend 339 passed;
final Next/OpenNext production build and 11 actual Next SSR groups passed. Single
Alembic head 0018_asr_evidence_index and full PostgreSQL upgrade SQL passed; no migration.
Write request-ID/scope/trusted actor/number/quota/atomic audit contracts unchanged.
Unrelated frontend/app/activity/page 2.tsx was not rebuilt, adopted or removed.

Fine-grained read migration 12/17 (71%) → 13/17 (76%); top-level ROADMAP 34/44 (77%)
remains because passport, readiness/compatibility policy, release catalogs/resolver and
other rich profiles/domain catalogs still need migration. Next passport, then remaining
reads; approved identity/session/submission/recovery/corrections/operations follow.
Remaining conditional planning estimate 7–11 internal-use packages, 15–23 total toward
production review. Public staging stays read-only.

Online verification after feature commit `78eeceb6ec874829472da40bb6d38e6deb79d9b8`:
Render `dep-db00s3g473hc73fn5hi0` is live for that commit, finished
2026-10-02T20:04:20.460688Z UTC / 2026-10-03 Asia/Shanghai. Health HTTP 200 /
API 0.18.11 / 0018_asr_evidence_index; independent read-only SQL confirmed the schema.
SNAP-007 UUID ce782633-9f46-49aa-8853-322672d4df98 → SNAP-008 UUID
c6f38c25-c42e-4bdb-8327-e16f7e85dd7b matched saved legacy identity, metadata/hash-match
and full counts (4 added, 0 removed/modified/unchanged). Four distinct one-row file
pages matched every public field and per-file rule count; no nested policy rules or
private reference. Reverse produced 4 removed; SNAP-008 self-comparison 4 unchanged
and an empty changes page. Strict/missing/wrong-pin/unknown/filter/beyond-end checks
passed. Exact ELF side lookup returned one frozen file and zero rules. Snapshot and
Deployment Batch empty POST probes returned HTTP 403 read_only_mode. No business write.

Cloudflare new Chinese comparison showed complete counts/identities/full hashes with
one file on compare_limit=1. Next A2L→ELF retained both names/UUID pins, show=all and
limit=1; ELF showed zero stored rules and external denial. English switching preserved
all raw identities/hashes, counts and offset=1. The exact side link opened only the
SNAP-008 ELF UUID and zero-rule page. Submitting changed-files filter reset cursors and
returned the first page of that same pair. Original pinned one-row view and Chinese
restored for the final screenshot. Cloudflare provider deployment/commit metadata was
not exposed; observed new behavior establishes frontend rollout, not a provider ID.
Whole-manifest duplicate and nullable duplicate-rule/newer-commit behaviors are proven
locally in real PostgreSQL, without modifying staging. Fine ledger 13/17, ROADMAP 34/44.
Feature/verification docs pushed to main, working tree clean, unrelated duplicate file
untouched. Next ASR passport and the other three pending read groups.

## ASR passport bounded development package — 2026-10-03

Mode: Codex. Developed from GitHub main f63862a45b0b2e4c945f2252cc8f74d0ac25d769,
verified against repository handoff/status/roadmap/architecture/API/database/security/
changelog/write contracts, code, tests and latest commits. API 0.18.12 adds a fixed
passport identity/decision summary with SQL counts and four independently bounded
histories. Paired Snapshot/decision UUIDs or explicit `none` persist across pagination;
summary recomputes current/latest indicators. Decision deliveries use the exact Snapshot
FK even when metadata is missing; approval joins validate all release/Snapshot bindings.
Historical RELEASE cannot override a newer HOLD or release current content. Release-wide
distributions/authorizations are labeled separately. Chinese default/English, full hashes,
raw identities, metadata, reason/actor/time, exact revision links and full counts remain.
Individual failed pages do not turn into false zero totals or trigger bulk fallback.
Compatibility APIs retained; no writes or schema changes. Existing request-ID retries,
conflicts, Snapshot/quota locks, exact authorization/trusted actor/atomic audit unchanged.

Validation: full backend Python 3.12, 904 passed, 5769 existing/deprecation warnings,
no skips; includes 115 real PostgreSQL 16.15 cases, 67 backend modules. Twenty-nine
new scope/pin/count/history/growth/strict HTTP/PostgreSQL cases. Frontend 357 passed;
final Next/OpenNext production build and 12 actual Next SSR groups passed. PostgreSQL
second-session commit preserves Snapshot pin and current/historical semantics; no audit
writes. Single Alembic head 0018_asr_evidence_index and PostgreSQL upgrade SQL verified.
No migration required. Unrelated frontend/app/activity/page 2.tsx not rebuilt/adopted/
removed. Offset pages and mutable metadata remain live observations, not a frozen view.
Fine read ledger 13/17 (76%) → 14/17 (82%); ROADMAP 34/44 (77%) unchanged. Pending
readiness/compatibility policy, release catalogs/resolver, rich profiles/domain catalogs;
then approved identity/session, authenticated submission/recovery/corrections, operations.
Conditional remaining estimate 6–10 internal-use packages, 14–22 total production review.
Public staging remains read-only; rollout verification will be recorded after push.

Online verification after feature commit `8ab38722f62b7221fe8cdf90e9c3c70cb07d935d`:
Render deploy `dep-db03ajff3r2c73ampbrg` is live for that commit, finished
2026-10-02T22:51:42.199751Z UTC / 2026-10-03 Asia/Shanghai. Health HTTP 200 /
API 0.18.12 / schema 0018_asr_evidence_index; independent read-only SQL confirmed head.
Saved legacy profile/decision/history/downstream and new summary agree on exact release
271334c3-9a99-4dc0-a7dc-75ba5754377b, SNAP-008
c6f38c25-c42e-4bdb-8327-e16f7e85dd7b, full hash, decision RD-0081 UUID
f1f06f98-62a8-4a10-9fcd-f904c62702b5, APR-0121, actor/notes/time and four full counts
(1 each). One-row pages matched every passport-used field; authorization batch_limit
is intentionally omitted from this passport projection and remains in compatibility/
authorization APIs. Beyond-end/invalid/missing-pin/unknown-field/foreign-pin checks
passed. Explicit none pins returned no selected snapshot/decision. Empty Snapshot and
Deployment Batch POST probes both returned HTTP 403 read_only_mode; no business write.

Chinese Cloudflare passport showed complete counts, exact UUID selection/full hashes,
notes/actor/time and all three outbound groups with limit=1. English retained all raw
identities/hashes/counts. First-page navigation retained both pins, limit and independent
cursors. Invalid delivery cursor showed unavailable/page count unknown while full count,
decision/distribution/authorization stayed visible; repaired original Chinese view.
Three lifecycle badge translations were added in
`03892f7637e92a2f402118c0d4dcfb351baaf838` and revalidated: frontend 357 passed, final
Next/OpenNext build and 12 actual SSR groups including default Chinese badge passed.
Live reload showed Chinese 已正式发布, establishing frontend correction rollout.
Cloudflare provider deployment/commit metadata was not exposed; no provider ID claim.
Final screenshot retained exact history hash, counts and links. New-commit/historical/
wrong-binding/growth scenarios are proven locally with real PostgreSQL where appropriate,
without staging seed/mutation. Fine read ledger 14/17 (82%), ROADMAP 34/44 (77%).
Next readiness/compatibility policy, release catalogs/resolver and other rich reads.
Feature, translation and verification records pushed to main; unrelated duplicate file
untouched. Public staging remains read-only. Conditional estimate 6–10 internal-use
packages, 14–22 total toward production review.

## Bounded readiness development package — 2026-10-03

Mode: Codex. Developed from GitHub main 2a4dd835659effeefcabdd1845efdbc5e18c4eac,
with current repository documents/code/migrations/tests/recent commits as source.
API 0.18.13 adds fixed current-readiness summary and bounded approved-exception pages.
Shared policy summary now uses SQL CASE/EXISTS instead of all artifacts/rules and
ID arrays. Eight raw/effective gates, evidence strings, percentages/rounding and
eligibility match legacy; only the existing verification exception code affects that
effective gate. Hard SHA/policy/frozen/match failures remain. Live declarations remain
live (not replaced by frozen file policy); stored SHA/rules are recording indicators.
INTERNAL_ONLY override, nullable SHA/level, empty/whitespace SHA and duplicate nullable
rules preserve previous semantics. Summary has complete exception count and no array;
exact owned Snapshot exception pages allow 1..100 rows. Current summary pin is rejected
with 409 after a newer Snapshot; foreign/missing pin gets 404. Explicit none does not
reselect. Default Chinese/English preserve full UUID/hash, reason/control, gates and
totals. Failed pages do not replace complete count with zero; latest refresh is explicit.
Legacy readiness/artifact array APIs and evaluate remain, not claimed retired; current
frontend does not use these bulk reads. Reads are observations, not grants or receipts.

Validation: full Python 3.12 backend 932 passed, 6024 deprecation/existing warnings,
no skips; includes 119 real PostgreSQL 16.15 tests and 68 backend test modules.
Twenty-eight new parity/scope/count/exception/hard-gate/growth/strict HTTP/PostgreSQL
cases; second-session newer Snapshot invalidates summary pin but keeps exact old page.
Frontend 369 passed; final Next/OpenNext build and 10 actual Next SSR groups passed.
Single Alembic head 0018_asr_evidence_index and PostgreSQL upgrade SQL passed; no
migration. Existing exact authorization, trusted actor, keyed retries/conflicts,
Snapshot/Batch locking and business/audit atomicity remain unchanged and tested.
Unrelated frontend/app/activity/page 2.tsx not recreated, adopted or removed.

Fine consumer ledger 14/17 (82%) → 15/17 (88%), under unchanged 17-group scope;
compatibility arrays/evaluate remain with their original contracts. ROADMAP remains
34/44 (77%), Phase 4 8/9, Phase 6 3/5; release catalogs/resolver and rich profiles/domain
catalogs remain. Next release catalogs/exact legacy resolver, then other rich reads;
approved identity/session, authenticated submission/recovery/corrections and operations
follow. Conditional estimate 5–9 internal-use packages, 13–21 total production review.
Public staging remains read-only; online verification will be recorded after push.

## Release catalogs and exact legacy resolution — 2026-10-03

Mode: Codex cloud. Developed from GitHub main `12660a160750218e0997ecd322d652d6c36f1ea2`.
API 0.18.14 adds `/api/v1/release-catalog/application` and `/standard`, with
strict q/status/software_id/limit/offset filters, complete filtered counts and
stable created_at/UUID ordering. Page size is 1..100 (default 50), offset
0..100000. ASR latest Snapshot is a single SQL scalar projection; no growing
Snapshot/child arrays or ORM graph are fetched. Stored optional references are
outer joined and release rows survive missing metadata. The two frontend release
directories use these pages, keep filters in navigation, distinguish beyond-end
from unavailable, and retain default Chinese/selectable English and exact links.

`/api/v1/release-catalog/application/resolve?identifier=...` queries at most two
exact APPLICATION UUID-or-version matches. It returns unique/ambiguous/missing;
only unique supplies a release. UUID/version collisions stay ambiguous, without
UUID precedence or arbitrary selection. This fixes old links beyond the former
200-row directory cutoff; demo and unavailable/ambiguous fallbacks remain the
application directory. Legacy list APIs remain for compatibility, not retired.

No migration or write change; head remains `0018_asr_evidence_index`. Offset/count
reads are live observations, not a frozen cross-request dataset, authorization,
readiness or proof of release. Public staging remains read-only. Read consumer
ledger advances 15/17 (88%) to 16/17 (94%); ROADMAP remains 34/44 (77%) because
rich profiles/domain catalogs remain in group 17. Next review those consumers,
then approved OIDC/session, controlled submission/outcome recovery, broader
correction/revocation and operations. CI PR #1 (`438a663`) remains open and is
not counted as merged CI. Conditional planning: 4–8 focused packages toward
internal use, 12–20 total toward production review; group 17 may span packages.

Validation for this package: complete Python 3.12 backend **948 passed**,
**7665 warnings**, no skips; includes **120 real PostgreSQL 16.15 tests** in
disposable migrated schemas. Sixteen new backend cases cover legacy row parity,
complete pagination, beyond-end, missing metadata, literal filters, ambiguity,
strict HTTP input, >200 release growth and >120 Snapshot growth with fixed
scalar query shape/no ORM child graph, plus no audit writes. Frontend **378
passed**, no skips, including eight new catalog/resolver/actual Chinese-English
SSR rendering cases. Next.js and OpenNext Cloudflare production build passed.
Single Alembic head 0018 and generated PostgreSQL upgrade SQL passed. Existing
write safety suites pass unchanged. Public rollout verification passed; see the dated rollout record below.

## Release catalog rollout verified — 2026-10-03

Feature commit `347cd541e05e70967b8c15b14e4a3cd51b86d4cb` is on GitHub main.
The uploaded 19 file blob hashes and full Git tree match the local tested commit.
Cloudflare check `Workers Builds: softwarelifecycle` completed successfully for
that exact commit. Live API health returned HTTP 200, version 0.18.14 and revision
0018_asr_evidence_index. Both catalogs passed one-row/full-count/beyond-end checks
and rejected invalid limit/offset/unknown-field filters with 422. Exact UUID
resolution and missing resolution passed; legacy version passport redirected to
the exact ASR UUID. Snapshot and Deployment POST probes returned 403
read_only_mode; no business data was written. Live Chinese pages passed normal,
beyond-end and invalid-filter states; slc_language=en served English directories
with HTTP 200. Public environment remains sample-only/read-only. No Render
provider deployment ID or exact provider commit metadata was exposed in this
verification; the API version/behavior is independently verified over HTTPS.
CI PR #1 remains open. Verification-only documentation follows the feature commit.

## Bounded SCR and Issue directories — 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from GitHub main `665c0335d278125b748a4aa05e16ea0a5e60d9e2`.
API 0.18.15 adds strict bounded change-request and Issue catalogs. Both frontend
directories now retain filter context, complete totals, first/next links and explicit
beyond-end/unavailable states, with default Chinese/selectable English. SCR
verification/ready cards are SQL aggregates over the entire filtered set, preserving
previous case-sensitive status substring display semantics rather than redefining
release readiness. Exact UUID software/customer/project filters select stored SCR
fields only; Issue filters do not infer ownership/impact from version text. Literal
search escapes wildcard characters. Directory rows do not transfer Issue descriptions
or rich child histories; descriptions remain on exact profiles. Two scalar SQL
queries supply totals and a bounded window without growing ORM graphs/ID arrays.

No migration or write change; schema head stays `0018_asr_evidence_index`.
Legacy bulk `/changes` and `/issues` APIs and rich profiles remain compatible.
Offset pages/counts are mutable observations, not frozen evidence or write grants.
Public staging stays read-only. ROADMAP remains 34/44 (77%), read ledger 16/17
(94%): this package advances two directory consumers inside still-open group 17,
not that whole group's completion. Remaining: SCR details, Issue details/impact
evidence, supplier/customer/project directories and rich profiles, manufacturing
directories/profiles; then approved identity/session, controlled submission/recovery,
broader corrections/revocations and operations. CI PR #1 remains open. The prior
conditional package estimate is not reduced merely for finishing this partial group;
remaining rich reads need decomposition before a reliable new estimate.

Validation: full Python 3.12 backend **965 passed**, **7717 warnings**, no skips,
including **121 real PostgreSQL 16.15 tests** on disposable migrated schemas.
Seventeen focused new backend cases cover row projection parity, complete filtered
counts, case-sensitive TEST/READY statistics, exact stored scopes, escaped search,
tied ordering, >200 row growth with two fixed scalar queries/no ORM graph, strict
HTTP fields and unchanged read-only rejection; PostgreSQL reads add no audit event.
Frontend **385 passed**, no skips, including six new directory/render tests plus
localization coverage for the new component. Actual Chinese/English SSR retains
original titles, numbers and links. Next.js/OpenNext Cloudflare production build,
single Alembic head and generated PostgreSQL upgrade SQL passed. Head stays 0018.
Existing write/authentication/atomic-audit suites pass unchanged. Rollout passed independent HTTPS checks; see the dated verification below.

## SCR/Issue directory rollout verified — 2026-10-04 (Asia/Shanghai)

Feature commit `e7e86211cf89cae09ccdb824993f5ba6b72fb409` is on GitHub main;
uploaded Git tree matches the tested local commit. Cloudflare Workers Builds
completed successfully for this exact feature commit. Live API health returned
HTTP 200 / version 0.18.15 / schema 0018_asr_evidence_index. Both catalogs passed
one-row/full-total/beyond-end/no-match and strict invalid-filter checks. Public
sample legacy rows matched complete counts, and SCR status statistics matched
case-sensitive TEST/READY markers across the full legacy sample. Issue directory
omits descriptions as documented. Chinese and English directory pages, beyond-end
and invalid-filter states passed. Snapshot and Deployment POST probes returned
403 read_only_mode; no domain records were written. Public staging remains
sample-only/read-only. Render provider deployment ID/commit metadata was not
exposed; HTTPS independently verifies API version and behavior. CI PR #1 remains
open. Overall 34/44 (77%), read groups 16/17 (94%); only the two directory
consumers inside group 17 completed in this package.

## Bounded SCR detail — API 0.18.16, 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from GitHub main `bc28abe5f5f8d7e73b6b75b3c923268e0e2e7281`.
SCR detail now reads a scalar parent summary plus independently bounded acceptance
criteria, Issue relations, change points and DVP plans. Selecting a point or plan
loads its items by exact owned UUID, rather than loading every nested test item.
Complete counts remain visible on beyond-end or failed child pages; each cursor and
selection preserves the others. Default Chinese and selectable English remain.
Parent metadata, raw business text, materials UUID and coverage links are preserved.

The required change_id binds each child request to the resolved SCR UUID. Point/plan
UUIDs must belong to that SCR. These pins select live identity, not a frozen Snapshot
or cross-request transaction. Scalar SQL counts and bounded rows avoid growing ORM
graphs/ID lists. Duplicate display numbers and multiple Issue relation types are
preserved. Missing referenced Issues/DVP items are excluded as in the legacy profile;
real cross-plan DVP assignments remain visible. Point assignment counts count bindings,
not distinct tests, executions or passing results. Legacy rich APIs remain compatible.

No migration or write-contract change; head `0018_asr_evidence_index`, 14 command
contracts and public read-only mode remain. ROADMAP stays 34/44 (77%), read ledger
16/17 (94%): group 17 is still partial. Next inspect SCR coverage, Issue detail/impact,
organization and manufacturing reads; then approved identity/session, controlled
submission/recovery/corrections and operations. CI PR #1 remains unmerged. Conditional
estimates (4–8 packages toward internal use, 12–20 toward production review) remain
unchanged until the remaining rich-read scope is decomposed.

Verification: full Python 3.12 backend **983 passed**, **7774 warnings**, no skips,
including **122 real PostgreSQL 16.15 tests** on migrated disposable schemas. New
cases cover scalar full counts, duplicate display numbers, multiple Issue relation
types, cross-plan/orphan semantics, ownership pins, beyond-end pages, strict HTTP
validation/read-only denial, fixed SQL shapes after 120-child growth and no audit
writes. Existing command concurrency/replay/rollback regressions passed. Frontend
**394 passed**, no skips; final Next/OpenNext Cloudflare production build passed.
Six actual production Next SSR groups passed (default Chinese/English, metadata,
beyond-end, selected UUID items, independently invalid page, foreign parent summary).
Single Alembic head and PostgreSQL full upgrade SQL generation passed; no migration.
Cloud rollout is pending at this feature commit and must be verified independently.

## SCR detail cloud rollout verified — 2026-10-04 (Asia/Shanghai)

Feature commit `53bb1f9188fd0a9b2647a2525e6fd0b39dfdbfd2` is pushed to main.
GitHub's `Workers Builds: softwarelifecycle` check completed successfully for that
exact commit at 2026-10-03T16:38:05Z. Render HTTPS health/live and health/ready return
200, API 0.18.16 and schema 0018_asr_evidence_index. Provider-side Render deployment
ID/commit metadata was not inspected; API version and behavior are live evidence.

SCR-142 UUID `8c923022-b24c-4358-b808-74d484285881` retains parent metadata and
complete counts: 1 criterion, 1 Issue relation, 2 points, 1 plan, 3 point assignments
and 4 owned-plan DVP items. Six collection/selected-child routes were checked with
limit 1, beyond-end/full totals, invalid/missing pins/limits and foreign child UUIDs.
Cloudflare Chinese/English SCR detail, exact selected point/plan item links, beyond-end
criteria and an independently invalid repeated criterion cursor passed. Empty
Deployment and Snapshot POST probes return 403 read_only_mode without business
writes. No migration, provider/grant configuration or public-write enablement.

Next package: bound SCR coverage while preserving release/frozen-Snapshot selection,
then Issue detail/impact (linked SCR relations, candidate releases and full judgment
history). Inspect organization/manufacturing consumers after those. Progress remains
34/44 (77%), read ledger 16/17 (94%); CI PR #1 remains unmerged.

## Bounded SCR coverage — API 0.18.17, 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from main `79e5f767d74c818d2642aee8408d47c5ec733717`.
SCR coverage now separates a fixed SQL summary/full counts from paged candidate
releases, gaps, criteria, points, distinct Issues and owned-plan test items. Selecting
a group UUID loads its exact summary and bounded assigned tests; selected criteria
also expose bounded formal assignment history and the existing preparation link.
No page downloads all nested test/assignment histories. Full parent counts persist
on beyond-end or failed pages, and unrelated cursors/selection remain independent.
Default Chinese and selectable English are retained. Candidate pages replace the
first-100 dropdown; direct exact UUID selection remains possible beyond any page.

Coverage preserves legacy semantics: Issues are distinct despite multiple relations;
valid tests belong to this SCR's plans, foreign/missing links are excluded and counted
as gaps, latest execution_no on the exact release/FROZEN Snapshot wins, any latest
FAIL/ERROR/CANCELLED yields FAILED, all assigned latest PASS yields PASSED, otherwise
PENDING. Unassigned/no-context/no-freeze remain distinct. Assignment percent retains
Python rounding and null for empty groups. Formal criterion records remain visible
even when their test references are excluded. Unicode whitespace matches Python
strip for blank acceptance text. SCR detail still shows real cross-plan assignments;
coverage intentionally excludes them, as it did before this migration.

Page pins require exact change_id plus release_id/snapshot_id UUID or literal none.
Historical frozen execution pins survive newer freezes. A previously missing freeze
that now exists rejects stale none context with 409 instead of silently substituting
evidence. Current SCR definitions/assignments remain live: these pins do not freeze
definitions, confer incorporation, authorize release, or grant write permission.
Legacy report/assignment APIs, all 14 command contracts and schema head
0018_asr_evidence_index remain. Public staging stays sample-only/read-only.

Progress remains ROADMAP 34/44 (77%) and read groups 16/17 (94%); broad group 17 is
still partial. Next Issue detail/impact (linked SCRs, candidates and judgment history),
then organization/manufacturing reads; approved identity/session, controlled
submission/recovery/corrections and operations follow. CI PR #1 is unmerged.
Conditional estimates remain 4–8 focused packages toward internal use and 12–20
total toward production review, pending decomposition/provider decisions.

Verification: final Python 3.12 backend **1007 passed**, **8004 warnings**, no skips,
including **123 real PostgreSQL 16.15 tests**. New coverage cases verify legacy full
summary/gap/group parity, exact latest PASS/FAIL/ERROR/CANCELLED/pending states,
software/customer/project scope, distinct Issues, foreign/orphan assignments, Unicode
blank text, complete candidates beyond 100, historical/stale-none context pins,
strict HTTP identity/pagination, fixed SQL shapes after 120-child growth, bounded
selected histories and no audit writes. Existing real lock/replay/rollback suites pass.
An early local temporary PostgreSQL data-directory read error caused fixture failures;
a newly initialized isolated instance resolved that infrastructure problem and the
final full suite passed. Online databases were not changed for regression testing.
Frontend **405 passed**, no skips; final Next/OpenNext Cloudflare build passed. Seven
actual production Next SSR groups passed across Chinese/English, selected criterion
history/preparation UUID, pinned execution context, beyond-end full counts, independent
invalid cursor, blank-form assignments-only and foreign parent summary stopping reads.
Single Alembic head and PostgreSQL full upgrade SQL generation pass; no migration.
Cloud rollout is pending at this feature commit and requires independent verification.

## SCR coverage cloud rollout verified — 2026-10-04 (Asia/Shanghai)

Feature `317780bb23b1b4b79ba1af3db305593c5e1d7d94` is pushed to main. GitHub
Workers Builds: softwarelifecycle completed successfully for that exact commit
at 2026-10-04T06:30:40Z. Render HTTPS readiness returns 200, API 0.18.17, schema
0018_asr_evidence_index. Render provider deployment ID/commit metadata was not
inspected; HTTPS version/feature behavior is the API rollout evidence.

SCR-142 UUID 8c923022-b24c-4358-b808-74d484285881 has 3 complete candidate releases.
ASR 2.3.3 (2bac628d-4335-43f6-90a5-efcdd490eaf8) has no frozen Snapshot: coverage
shows 1 criterion/0 assigned, 2 points/2 assigned, 1 distinct Issue/1 assigned,
4 owned-plan items and 2 gaps; execution totals remain unknown, matching legacy.
Six collections passed limit-1/full-count/beyond-end/invalid-limit checks; exact
selected criterion summary/items/history and foreign SCR/group rejection passed.
Chinese/English selected criterion pages, beyond-end gaps and independently invalid
repeated gap cursors passed. Empty Deployment POST returns 403 read_only_mode;
no business writes were performed.

Frozen context: ASR 2.3.4 UUID 271334c3-9a99-4dc0-a7dc-75ba5754377b, SNAP-008
UUID c6f38c25-c42e-4bdb-8327-e16f7e85dd7b / freeze 8. Full summary matches legacy:
4 items, 3 executed, 3 latest PASS; 1 of 2 assigned points passed and 1 Issue passed.
All four limit-1 item pages preserve exact execution_no/result/observation/time with
no missing/duplicate item UUID; selected point items also match. Chinese/English
actual first/next pages retain that same frozen UUID and group selection.

No migration, provider/grant configuration or public-write enablement. CI PR #1
was independently checked open/unmerged. Next Issue detail/impact, then remaining
organization/manufacturing reads. ROADMAP 34/44 (77%), read ledger 16/17 (94%).

## Bounded Issue detail and impact evidence — API 0.18.18, 2026-10-04

Mode: Codex cloud. Developed from main `a248b1ab79578a960260f2e14f0d1abb80b06c4b`.
Issue detail now has a scalar parent summary/full counts plus independent linked
SCR relation, candidate release and complete judgment-history pages. Exact impact
review has a scalar context/latest judgment summary and independent distinct frozen
component and linked DVP verification pages. Both default-Chinese/English pages
retain complete counts on beyond-end/failed child reads and preserve unrelated
cursors. Materials, release/customer/project/Snapshot/item UUID links and exact
impact-preparation targets remain. Historical judgment links select their recorded
Snapshot UUID instead of silently showing the newest freeze.

Candidate scope preserves the prior software-product relationship via linked SCRs;
it does not infer impact or require the SCR's customer/project scope. Directory rows
retain the legacy real-product metadata visibility rule, full actual-release deployment
and batch counts, newest FROZEN Snapshot and newest judgment for that exact Snapshot.
Multiple relation types remain separate records; candidate releases are not duplicated.
History retains exact formal records when optional release/Snapshot display metadata
is missing. Distinct component code/version pairs normalize null versions to empty
strings. Verification includes real Issue-linked items across plans, selects latest
execution_no only for the exact release/Snapshot, and excludes missing DVP references.
A PASS is execution evidence, not an impact decision. Current Issue links and newest
judgments remain live; historical pins freeze execution selection, not definitions.

Required page issue_id binds the business number to the exact Issue UUID. Impact
pages additionally pin release path and Snapshot UUID/none. A historical FROZEN
UUID remains valid after newer freezes; stale none that now has a freeze returns
409. No migration, command contract/provider/grant changes; head
0018_asr_evidence_index and 14 commands remain. Public staging stays sample-only
read-only. Legacy rich APIs remain for compatibility.

ROADMAP remains 34/44 (77%) and read groups 16/17 (94%). Group 17 is still partial:
SCR/Issue detail/coverage/impact consumers are migrated, organization and manufacturing
catalogs/profiles remain. Next bound those reads, then approved identity/session,
controlled submission/recovery/correction/revocation and operational acceptance.
CI PR #1 remains unmerged. Conditional estimates remain 4–8 focused packages toward
internal use, 12–20 toward production review pending remaining scope/provider decisions.

Verification: full Python 3.12 backend **1025 passed**, **8617 warnings**, no skips,
including **124 real PostgreSQL 16.15 tests** on newly initialized disposable
instances/migrated schemas. New cases cover legacy parent/candidate/history/evidence
parity, multiple SCR relation types, full candidate counts beyond 200, normalized
distinct component pairs, latest exact execution scope/failure, historical/stale-none
Snapshot selection, orphan history metadata retention, strict pins/pagination/read-only
denial and 120-child growth with fixed SQL shapes/no ORM graph. Real PostgreSQL
verifies candidate windows, frozen components, newer FAIL precedence and no audit
writes. Existing command concurrency/replay/rollback/actor/scope suites pass.
Frontend **416 passed**, no skips; final Next/OpenNext Cloudflare production build
passed. Eight actual production Next SSR groups passed: Issue Chinese/English,
impact Chinese/English with exact preparation UUID, complete beyond-end history,
independently invalid component cursor, no-freeze without preparation, foreign Issue
summary stopping child reads. Single Alembic head and full PostgreSQL upgrade SQL
generation pass; no migration. Cloud rollout pending at this feature commit.


## 2026-10-04 — Verified Issue detail cloud rollout

Feature commit `121e7ac10674ea0868d499ac10143e7def4464ab` is on main.
Cloudflare Workers Builds for that exact commit succeeded at
2026-10-04T07:00:22Z. Live HTTPS verification completed on 2026-10-04:
Render `/health/ready` returned 200, API **0.18.18**, schema
`0018_asr_evidence_index`. Provider deployment metadata was not inspected;
API rollout evidence is the live version and behavior, not a claimed Render deploy ID.

Sample Issue #310 (`e9aea1f4-26cf-4a4d-97b1-b63ef3c1cddb`) has one linked
SCR relation, three candidates and zero manual judgments. New complete counts
match legacy reads. Limit-one pages, beyond-end empty pages, invalid limits,
foreign Issue pins and unknown Issue selection behaved as specified.
Selected ASR 2.3.4 (`271334c3-9a99-4dc0-a7dc-75ba5754377b`) uses FROZEN
SNAP-008 (`c6f38c25-c42e-4bdb-8327-e16f7e85dd7b`), hash
`ed7e8188c12661c328110366b0c17cc2299cc6faa37cea2e04130dc3d166cc21`.
Its two distinct frozen component pairs and one verification item match legacy
components and latest exact execution result/observation/time. Latest manual
judgment is absent in this sample; nonempty judgment/history behavior is covered
by local regression and production SSR fixtures. Invalid Snapshot selection
returns 409. No storage reference is exposed by component pages.

Cloudflare Chinese/English Issue and impact pages preserve complete counts,
selected Snapshot UUID and exact preparation target. Beyond-end history stays
empty with its full count; repeated component cursor fails only that collection.
An empty impact-assessment POST returns 403 `read_only_mode`. Public staging
remains sample-only read-only. No migration, grant or command contract change.
Full verification remains backend 1025 passed (124 real PostgreSQL), frontend
416 passed, production build and eight production SSR groups passed.

ROADMAP remains **34/44 (77%)**, read groups **16/17 (94%)**. Organization and
manufacturing catalogs/profiles remain in partial group 17. CI PR #1 remains
open/unmerged and is not counted as operational acceptance. Next continue those
bounded consumers, then approved identity/session and controlled submission,
recovery/correction/revocation, followed by operational acceptance.


## Bounded organization directories and profiles — API 0.18.19, 2026-10-04

Mode: Codex cloud. Developed from verified GitHub main `b3a621975d174d79444bf360ad978eec353ef30b`.
All six supplier/customer/project directory/profile consumers now use
`organization_views.py`, `organization-catalog.tsx` and `organization-profile.tsx`.
Directories fetch bounded scalar rows and full filtered counts instead of every
software/project/site name and release array. Open a profile to browse related
records. Profiles retain exact metadata/materials UUID, supplier introduction,
customer region/release-history link and project customer/platform/latest release.
Software portfolio, customer projects/current software and project sites each have
owned bounded pages. Project site links use the stored unique site code accepted by the existing
manufacturing profile route; the API retains each exact site UUID. Supplier
product links select its exact software UUID; latest
SSR and ASR links target the stored release UUID, not a version string.

Search treats wildcard characters literally; status/country/customer UUID filters
are exact. Region includes null-only UNASSIGNED; blank region selects all. Limits
are 1..100 (default 50), offsets 0..100000; unknown/kind-inappropriate fields fail
422. Stable code/UUID ordering avoids duplicate display-code pagination. Project
UUID selection retains precedence over code; duplicate codes return 409 and
canonical/uppercase/compact UUID links select the same project. Required
organization_id pins each collection to the resolved parent; a foreign pin is 404.
No parent or child rich-array fallback is used. Failed/beyond-end child pages keep
full parent counts; missing optional customer display metadata retains project UUID.

Counts preserve existing relationships: supplier products by supplier UUID;
customer projects by stored customer UUID; projects with current software require
real Release/detail membership matching both project and customer. Project latest
release uses detail project UUID alone, preserving legacy scope even when detail
customer differs. Supplier latest selects STANDARD releases only. Latest is
created_at DESC NULLS LAST then release UUID DESC. These are live context/count
observations, not release approval, impact, frozen evidence or access grants.

No migration, head `0018_asr_evidence_index`; all 14 write contracts unchanged.
Public staging stays sample-only/read-only, default Chinese/selectable English.
Legacy organization APIs remain compatible. Release matrix already has bounded
reads and is unchanged. The remaining group-17 consumers are manufacturing site
directory/detail and their line/current-deployment context; organization reads
are migrated. ROADMAP stays **34/44 (77%)**, read groups **16/17 (94%)**;
Phase 4 remains 8/9 until the entire open read acceptance item is verified.
Next manufacturing reads, then approved identity/session, controlled submission,
uncertain-result recovery/correction/revocation and operational acceptance.
CI PR #1 remains open/unmerged. Conditional estimates remain 4–8 focused packages
toward internal use and 12–20 toward production review, pending provider decisions.

Validation: full Python 3.12 backend **1048 passed**, **8687 warnings**, no skips,
including **125 real PostgreSQL 16.15 tests** on disposable migrated schemas.
23 new backend cases cover legacy parent/child/latest parity, exact cross-customer
release semantics, 205-parent and 120-child growth with constant scalar SQL/no ORM
identity graph, literal filters/null region, duplicate project-code identity,
missing metadata, owned pins and public-write rejection. PostgreSQL verifies
complete totals beyond 200, deterministic latest release ties and read audit purity.
Frontend **435 passed**, no skips; final Next/OpenNext production build passed.
**24 actual production Next SSR groups** verify six Chinese/English views, full
beyond-end totals, invalid owned pages, repeated catalog filters, exact related/
materials/release links and missing/foreign parents stopping child reads.
Single Alembic head/full upgrade SQL generation pass. Cloud rollout pending
at this feature commit; verified rollout will be recorded separately.


## 2026-10-04 — Verified organization cloud rollout

Main contains feature `4620a35b06c92736a2076c1e6d856c1afe2f0dfd` and site-link
compatibility correction `50140be3ea8fef84653fc667d7e35f98c848e2cb`.
Cloudflare Workers Builds succeeded for the feature at 2026-10-04T09:01:40Z
and for the correction at **2026-10-04T09:11:26Z**. Live HTTPS readiness is
200, API **0.18.19**, schema `0018_asr_evidence_index`. Render provider deployment
metadata was not inspected; the API version/behavior is live rollout evidence.

Public sample has one supplier, one customer and one project. New full counts,
owned collection totals and latest versions match the legacy reads. Supplier
SUP-001 UUID `46fbde85-314c-440b-a3b8-df5be03a28a4` has one product; customer
CUS-001 UUID `a2b8a98d-bb2d-4581-bf7b-451bbc0d731e` has one project; project
PRJ-X UUID `c6448937-7b6e-4324-91cf-050177a0f0bc` has one site. Limit-one,
beyond-end counts/empty items, invalid/unknown filters and foreign parent pins
behave correctly. The larger parent/child windows and next-page transitions
are covered by local SQLite/PostgreSQL and production SSR fixtures; this single-row
live sample does not claim multi-page traversal.

All six Cloudflare views pass Chinese/English checks, retain exact materials UUIDs
and preserve parent context on invalid child cursors. Project site link uses the
stored unique code `/manufacturing/sites/FACTORY-A`, resolving the exact linked
site UUID `935fa56f-30e7-4f3a-b809-b6fd0ea3bd27`. Actual project HTML contains
that link; the site frontend returns HTTP 200 with Factory A and the legacy site
API returns the same UUID. This corrects an initial UUID URL incompatible with
the existing code-based site route. Final frontend 435 tests, production build
and 24 production SSR groups passed again after correction; backend remains
1048 passed (125 real PostgreSQL), no backend/schema change in the correction.
Empty deployment POST returns 403 `read_only_mode`. No business writes occurred.

ROADMAP **34/44 (77%)**, read groups **16/17 (94%)** remain; organization migration
is complete for six consumers, manufacturing site/line context remains. All 14
commands, schema 0018, sample-only public read-only mode and unmerged CI PR #1
remain unchanged. Next manufacturing reads, then approved identity/session,
controlled submission/recovery/corrections and operational acceptance.


## Bounded manufacturing consumers — API 0.18.20, 2026-10-04

Mode: Codex cloud. Developed from verified main `4fc79aa4e04885465cc15a582cee101f235bc670`.
Manufacturing site directory now uses a scalar catalog with full filtered totals;
site detail uses a scalar summary and one owned bounded line page. Neither consumer
loads all sites, all lines or every latest-deployment changeover/batch history.
Stored metadata, full line/deployed/MATCH/attention/approved-authorization counts,
first-line context, recorded batch context and precise line command targets remain.
Detailed deployment history opens the existing bounded deployment profile/catalog.
Default Chinese/selectable English, independent failed/empty page states and full
parent counts remain. Directory now links exact site UUID; existing site-code links
from projects/production still work through the new resolver.

Latest deployment is per-line created_at DESC NULLS LAST then deployment UUID DESC.
MATCH/attention counts preserve stored deployment status, not rederived actual UUID
matches. Approved authorization counts use real current authorization status on
latest deployments; they count lines, not unique authorizations. No deployment is
not an attention state. All-MATCH requires at least one line. Summary first context
uses line name/UUID ordering. Recorded batch remains the earliest started_at/UUID
batch on the first name/UUID-ordered line with batches on its latest deployment,
regardless of batch status; it is not a claim of active production. Changeover
context is earliest changed_at/UUID on the first line's latest deployment. Null
history times sort last, matching production PostgreSQL ASC behavior. A new latest
deployment can remove an older batch/changeover context. Foreign-site/older-deployment
history cannot leak into these selections. Optional metadata remains null while
stored UUIDs survive. No arbitrary release/version substitute is shown.

New summary accepts exact site code or UUID (LIMIT 2); a UUID/code collision is
409, missing site 404. Required site_id binds each line request to its resolved
parent UUID; wrong pin is 404. Catalog supports literal q and exact status/region/
customer_id/project_id filters; limit 1..100/default 50, offset 0..100000/default 0,
extra/invalid fields 422. Stable site name/UUID and line name/UUID ordering.
Encoded site-code separators are supported by suffix path routes. Links preserve
actual existing route contracts: deployment/authorization/batch use stored unique
numbers; release uses UUID and type; Snapshot uses number plus manifest_snapshot_id
UUID; line expectation preparation carries exact line UUID. No bulk fallback.

No migration; head `0018_asr_evidence_index`; all 14 write contracts unchanged.
Public staging stays sample-only/read-only. Identified read-consumer ledger now
**17/17 (100%)**, previously 16/17: group 17's final two consumers are migrated.
This is consumer completion, not removal of compatibility APIs. ROADMAP remains
**34/44 (77%)**, Phase 4 **8/9 (89%)**: its literal remaining acceptance item asks
to retire or bound old compatibility reads after migration. Those endpoints still
exist with rich arrays; caller review and retirement/bounds are unfinished. The
criterion and denominator are not rewritten to claim earned completion. See
`docs/compatibility-read-retirement.md` for the concrete follow-up inventory.
Next complete that compatibility contract review, then approved identity/session,
controlled submission/outcome recovery, broader corrections/revocations and operations.
CI PR #1 remains open/unmerged. Conditional package ranges stay 4–8 internal-use /
12–20 production-review pending remaining contract/provider scope; no automatic reduction.

Validation: full Python 3.12 backend **1069 passed**, **9112 warnings**, no skips,
including **126 real PostgreSQL 16.15 tests** on disposable migrated schemas.
21 new backend cases cover legacy counts/latest/context parity, complete bounded
line windows, tied latest UUID selection, exact filters/pins, empty/foreign context,
missing metadata, encoded site code and ambiguous identifier, read-only denial and
120-site/line/deployment growth with constant SQL shapes and no ORM identity graph.
PostgreSQL verifies 209-line totals, latest MISMATCH precedence, missing current batch
and no audit writes. Frontend **448 passed**, no skips; production Next/OpenNext
build passed. **9 actual production Next SSR groups** verify catalog/profile zh/en,
full beyond-end context, failed/repeated pagination, empty-site CHECK, parent identity
stopping child reads and exact supported links/preparation UUID. Single Alembic head
and full PostgreSQL upgrade SQL generation pass. Cloud rollout pending at feature
commit; successful live verification is recorded separately afterward.


## 2026-10-04 — Verified manufacturing cloud rollout

Feature main commit `1d4cfed98fed3ec961f7da89b44b8c06b88d683e` has successful
Cloudflare Workers Builds, completed **2026-10-04T12:28:32Z**. Live HTTPS
`/health/ready` returns 200, API **0.18.20**, schema
`0018_asr_evidence_index`. Render provider deployment metadata was not inspected;
this is live API version/behavior evidence, not a claimed provider deployment ID.

Public sample FACTORY-A UUID `935fa56f-30e7-4f3a-b809-b6fd0ea3bd27` is one site
with one line, one latest deployment, one stored MATCH, zero attention lines and
one current APPROVED-authorization line. Latest deployment UUID is
`7c8338a6-9070-4090-9f74-999d845be058`; recorded batch UUID is
`beb73c74-f10e-4ac7-a22a-02090ed1160f`. New scalar counts, latest line/authorization/
expected Snapshot projection, first-line context, first changeover and recorded
batch match legacy reads. UUID and legacy site-code summaries resolve identical
site context. Limit-one/beyond-end pages preserve full totals; invalid/unknown
fields and foreign site pins reject as specified. The one-line public sample does
not demonstrate real next-page traversal; local growth, PostgreSQL 209-line windows
and SSR fixtures cover larger pagination/tie cases.

Cloudflare catalog/profile pass default Chinese and selected English. Directory
links exact site UUID; old FACTORY-A links still open the same profile. Rendered
line expectation preparation carries exact line UUID, deployment/authorization
links use the stored unique numbers accepted by their existing profiles, Snapshot
link carries manifest_snapshot_id. Invalid/beyond-end line pages preserve parent
context/counts. Empty deployment POST returns 403 `read_only_mode`; verification
requests wrote no business data. No migration or command/grant/provider change.
Backend 1069 passed (126 real PostgreSQL), frontend 448 passed, final production
build and nine production SSR groups passed; schema head remains 0018.

Read-consumer ledger now **17/17 (100%)** under its original denominator. ROADMAP
remains **34/44 (77%)**, Phase 4 **8/9 (89%)**, because its separate literal endpoint
acceptance requires retirement/bounds on retained compatibility APIs. Their caller/
contract review remains pending, documented in compatibility-read-retirement.md.
CI PR #1 remains open/unmerged. Next compatibility endpoint review/transition,
approved identity/session, controlled submission/recovery/corrections and operations.

## 2026-10-04 — First compatibility read retirement / API 0.18.21

Eight reviewed legacy supplier/customer/project and manufacturing site GET routes
now return 410 `legacy_read_retired` with safely encoded successor URLs, required
child UUID pin and summary-first migration instructions. Tombstones have no DB
dependency and never invoke old rich serializers; nonexistent parents and invalid
query fields still return the same retirement contract. OpenAPI marks exactly these
GET paths deprecated. Internal comparison helpers remain callable. Release-matrix,
bounded consumers, all 14 commands, identity settings and schema are unchanged.
This deliberately breaks legacy HTTP response contracts; unknown external callers
must migrate. Concrete paths and repository caller evidence are documented in
docs/compatibility-read-retirement.md.

Full backend: **1086 passed**, **9112 warnings**, no skips, including **126 real
PostgreSQL 16.15 tests**. Seventeen new cases verify eight paths with normal/invalid
queries, no DB/helper work, encoded identifiers, precise replacement pins, no
route shadowing and retained commands. Frontend: **448 passed**, no skips; final
Next/OpenNext production build passed. Alembic single head remains
`0018_asr_evidence_index`, full offline upgrade SQL passed. Production SSR passed 33 groups (24 organization + 9 manufacturing), covering
all eight bilingual consumers, invalid/empty windows, parent pins and exact links.
Cloud rollout evidence is recorded after verification below.

Read consumers remain 17/17, ROADMAP 34/44 (77%), Phase 4 8/9 (89%); other rich
compatibility families still require retirement/bounds. The new Chinese plan in
docs/development-plan.md lists ordered packages, acceptance gates and provider/
environment dependencies. Next remaining compatibility reads and CI review; then
approved OIDC/session, controlled submission/recovery, broad corrections and
operations/company migration. Public staging stays sample-only and read-only.

## Verified cloud rollout — API 0.18.21

Feature commit: `f28553c6aad27a6a39b8c140b2af606362d83e6a`; tree
`9c4a668dfa4d20528c841efd9243e0f5e7bcd5dc`. Cloudflare Workers Builds for this
exact commit completed success at `2026-10-04T13:04:30Z`. Live smoke completed
before this record at `2026-10-04T13:06:45+00:00`. Render provider deployment metadata was not
inspected; HTTPS readiness and runtime behavior establish observed API version,
not an asserted provider deployment ID or exact Render commit.

HTTPS ready returns API **0.18.21**, schema **0018_asr_evidence_index**. All eight
retired organization/manufacturing GET paths return 410 with successor instructions,
Link and no-store headers; invalid legacy query fields also return 410. All four
bounded catalogs, summaries and owned child pages remain usable; release-matrix
still returns 200. Live default-Chinese/selected-English checks pass for eight
consumers (16 rendered views). Strict extra filters reject 422, foreign site pin
rejects 404, beyond-end owned line window preserves total with empty items.

Supplier/customer/project each retain one owned record. FACTORY-A remains one
line, one deployed line, one stored MATCH, zero attention, one approved-authorization
line. Exact first deployment and recorded batch UUIDs match the previous verified
sample. UUID and old site-code links resolve the same bounded summary. Public
empty deployment POST rejects 403 `read_only_mode`; smoke creates no business data.
Small sample checks do not establish large next-page behavior; regression growth/PG
and 33 production SSR groups provide that evidence.

Final verified tests: backend 1086 (126 real PostgreSQL), frontend 448, no skips;
production build, 33 production SSR groups, single migration head and upgrade SQL
pass. Existing datetime.utcnow deprecation warnings (9112) remain. CI PR #1 was
checked open/unmerged this turn and is not counted complete. ROADMAP remains
34/44; next packages and acceptance/dependencies are in docs/development-plan.md.

## 2026-10-04 — Production/distribution retirement / API 0.18.22

Eleven additional legacy production/distribution GET routes now return 410 with
encoded successor URLs and explicit exact-scope instructions; cumulative retired
HTTP reads: **19**. Four production routes (deployment list/detail/provenance and
batch list) and seven distribution routes (delivery list/latest detail/exact rich
revision, distribution list/detail, authorization list/detail) are reviewed. Exact
Batch, bounded catalogs/profile/artifacts, shared helpers and all 14 POST commands
remain. Internal comparison fixtures retain direct legacy helper calls. Unknown
external HTTP consumers must migrate; this is an intentional contract break.

Delivery selection is explicit by stored number/revision/UUID, not automatic latest
or q substring identity. Deployment decision-history scope is the delivered pair
from provenance.delivery, not actual software; missing delivery infers no decision
scope. Retirement performs no DB read, graph loading or old validation, even for
unknown parents/invalid old revision values. Named parameters are encoded separately.
No migration, provider/identity/grant change or public-write enablement.

Full backend **1111 passed**, **9112 existing deprecation warnings**, no skips,
including **126 real PostgreSQL 16.15 tests**. Twenty-five added cases cover new
paths with normal/invalid queries, encoded numbers/revisions, no DB/helper work,
unchanged registered successors/commands and exact provenance instructions.
Targeted retirement/catalog/profile/command regression: 140 passed. Frontend
**448 passed**, no skips. Single Alembic head remains `0018_asr_evidence_index`;
full offline upgrade SQL passes. Final production Next/OpenNext build passes.
24 actual production Next SSR groups pass: 11 views zh/en, sibling revision and
exact deployment history/command links against a real backend SQLite fixture;
no retired API requests occur. Cloud rollout is recorded after verification below.

Progress remains ROADMAP **34/44 (77%)**, Phase 4 **8/9 (89%)**, identified read
consumers **17/17**. Other compatibility families remain; no approved overall
retirement denominator exists. CI PR #1 was checked open/unmerged and is not counted.
Next remaining SCR/Issue/release/governance/audit contract review, then CI, approved
identity/session, submission/recovery, broader corrections and operations.

The plan now answers the completion question explicitly: seven work groups mean
current-version scope, not seven turns. All acceptance gates plus 44/44 evidenced
roadmap items establish development completion. Actual company target identity,
permissions, recovery, network/data/operations review and release acceptance are
required for deployment approval. VIN/additional features and maintenance remain
separate later scope. Public sample continues read-only. See development-plan.md.

## Verified cloud rollout — API 0.18.22

Feature commit: `b3b90e7c723001f8ffdd31ff7a1094a59b81b42d`; tree
`3f7498a54a599f442e25964ebccc79145b048b6c`. Cloudflare Workers Builds for this
exact commit completed success at `2026-10-04T13:37:54Z`. Live smoke completed
before this record at `2026-10-04T13:41:16+00:00`. Render provider metadata was not inspected;
HTTPS version and behavior are runtime evidence, not an asserted provider deployment
ID or exact Render commit.

API ready reports **0.18.22**, schema **0018_asr_evidence_index**. All **19**
reviewed tombstones return 410 with encoded successor URLs, Link and no-store
headers, including unknown parents, malformed query and invalid old revision.
Six bounded production/distribution catalogs and exact delivery revision profile/
artifacts, distribution/authorization/deployment profiles and exact Batch pass.
**22 live bilingual views** (11 views, Chinese default/selected English) pass.
Each of six exact history filters matches its profile full count: delivery
distributions, distribution authorizations, authorization deployments/batches,
deployment batches/changeovers each equals one in the current sample. The delivered
release/Snapshot decision scope passes. Beyond-end history keeps total with empty
items; invalid limit rejects 422. Release-matrix remains 200. Five empty POSTs
(deployment, actual report, delivery, distribution, authorization) all reject
403 `read_only_mode`; no business data is created. Small live samples do not prove
large pagination; backend growth/PG and production SSR fixtures cover those cases.

Final verified checks: backend **1111 passed** including **126 real PostgreSQL**;
frontend **448 passed**, no skips. Production Next/OpenNext build completes;
**24 production Next SSR groups** against real backend fixtures pass. Alembic has
one head and full upgrade SQL passes. Existing 9112 datetime deprecation warnings
remain. CI PR #1 remains open/unmerged at this turn's check. Progress stays
**34/44 (77%)**, read consumers **17/17**; first work group is still incomplete.
See development-plan.md for remaining order, dependencies and completion gates.

## 2026-10-04 — SCR/Issue retirement and seven-plan reporting / API 0.18.23

Eight reviewed SCR/Issue GET routes retire with explicit 410 and exact summary/
child/historical-Snapshot migration instructions; cumulative tombstones: 27.
Internal comparison helpers, all bounded successors and all 14 commands remain.
The old bounded-but-truncated assessment head is retired in favor of navigable
complete history; not every route in the slice was unbounded. No DB/graph work or
old query/UUID validation occurs before retirement. Unknown external callers must
migrate; no redirect, historical-query forwarding or latest Snapshot substitution.
No schema, identity/provider/grant or public-write change.

Full backend **1132 passed**, **9112 existing deprecation warnings**, no skips,
including **126 real PostgreSQL 16.15 tests**. Eighteen added retirement cases
verify eight paths with normal/invalid queries and historical-selection instructions.
Three reporting checks enforce fixed scope/evidence, all 27 tombstones in the
53-candidate ledger, no unresolved completed family and no stale plan table.
Frontend **448 passed**, no skips; final production Next/OpenNext build passes.
**21 actual production Next SSR groups** pass (6 SCR, 7 coverage, 8 Issue/impact),
including bilingual views, independent invalid/empty pages, frozen UUID preparation
and foreign-parent rejection. Single migration head and full offline upgrade SQL
pass; schema remains 0018. Cloud evidence is recorded after verification below.

Seven independent work-group milestone progress rows are now mandatory in every
completion report and reproducible from docs/development-plan-progress.json using
scripts/report_development_plan_progress.py. Plans 1–7: **50%, 0%, 20%, 33%,
40%, 20%, 0%**. Plan 1 advances **40% → 50%** after SCR/Issue family completion;
other values include existing verified preparation/backend safety foundations,
not new provider-backed submission. Nine compatibility families plus one closure
gate fix that plan's denominator at 10; remaining release/ASR, Snapshot, DVP,
governance/audit and inventory acceptance prevent completion. Denominator changes
require explicit scope explanation. These are equal milestone counts, not effort
or production-readiness estimates; do not average them into ROADMAP progress.

ROADMAP remains **34/44 (77%)**, Phase 4 **8/9**, read consumers **17/17**.
CI PR #1 was checked open/unmerged. Next remaining compatibility families and
closure, CI, approved identity/session, submission/recovery, corrections and
operations. Public staging stays sample-only/read-only.

## Verified cloud rollout and mandatory plan report — API 0.18.23

Feature commit: `0e7366f49f52a4683f934c18eb4960adb05ae451`; tree
`1f58b554abb338de25f5df5da8f43ca4e01bc489`. Cloudflare Workers Builds for this
exact commit completed success at `2026-10-04T14:02:48Z`. Live checks completed
before this record at `2026-10-04T14:12:05+00:00`. Render provider metadata was not inspected;
HTTPS version/behavior is observed runtime evidence, not a provider deployment ID
or asserted exact Render commit.

Ready reports **0.18.23**, schema **0018_asr_evidence_index**. All **27** reviewed
legacy GETs return 410 with successor/Link/no-store, even invalid old identities/
queries. Two bounded catalogs, SCR/Issue summaries and all owned collections pass.
**14 initial bilingual page checks** plus **2 explicit historical SCR checks**
pass. The initial smoke had compared a translated Chinese title to English API
text; the rule was corrected to use localized/HTML-escaped text and the full smoke
rerun passed. This required no product change.

SCR-142 retains one criterion, one linked Issue, two change points and one plan.
Issue 310 retains one linked SCR, three candidate releases and zero judgments.
Issue impact selects exact ASR `271334c3-9a99-4dc0-a7dc-75ba5754377b` and frozen
Snapshot `c6f38c25-c42e-4bdb-8327-e16f7e85dd7b` (SNAP-008). Initial SCR selection
used a candidate without a freeze, preserving none. A separate explicit historical
SCR check selects that ASR/SNAP-008: snapshot-number selection equals UUID selection;
owned group/item pages and Chinese/English coverage retain exact pins; beyond-end
items preserve complete total. Foreign Issue pins reject 404, invalid limits 422.
Three empty POSTs (SCR assignment, Issue judgment, Deployment) all reject 403
read_only_mode; no business data is created. Small samples do not establish large
page traversal; backend growth/PG and SSR fixtures cover those cases.

Final verification: backend **1132 passed** (126 real PostgreSQL), frontend **448
passed**, no skips; production build, **21 production SSR groups**, single migration
head and upgrade SQL pass. Three final reporting checks were rerun after allowing
explicit bounded_evidence for retained active paths and removing hardcoded current
percentage assertions, so later legitimate progress can advance. Existing 9112
datetime deprecation warnings remain. CI PR #1 is open/unmerged at this turn's check.

### Seven-plan milestone report (include in every completion)

| 计划 | 已完成 / 验收里程碑 | 完成度 |
| --- | ---: | ---: |
| 1. 其余兼容读取治理 | 5/10 | **50%** |
| 2. 持续集成 | 0/4 | **0%** |
| 3. 身份、权限管理及会话 | 1/5 | **20%** |
| 4. 首批受控提交 | 2/6 | **33%** |
| 5. 覆盖全部 14 项命令 | 2/5 | **40%** |
| 6. 追加式更正和撤销 | 1/5 | **20%** |
| 7. 生产运营与公司迁移 | 0/6 | **0%** |

Plan 1 advances 40% → 50%; other rows establish fixed accounting of already
implemented foundations. Percentages are completed/equal acceptance milestones,
not effort, real-provider acceptance or production-readiness estimates. Retained
bounded paths require per-route code/test evidence; candidate inventory is 53 paths,
not a claim that all are unbounded. Roadmap/module progress stays **34/44 (77%)**:
100/100-demo/100-demo/89/89/60/0 by Phases 1–7. Read consumers stay **17/17**.
Next release/ASR, Snapshot, DVP, governance/audit families and inventory closure,
then CI, approved identity/session, submission/recovery, corrections and operations.

## 2026-10-04 — API 0.18.24 exact Snapshot retirement

Codex cloud continued from main 43bbe138e2e99942e541dbc48c0394d0ff1067af.
Two legacy Snapshot GET routes retire with DB-free HTTP410 and encoded successor
URLs. Exact manifests require snapshot_id; comparison files require source_id and
target_id. Internal legacy helpers remain comparison fixtures. Reviewed tombstones
27 → 29; all 14 commands remain. No migration or public-write enablement.

Validation: full backend 1137 passed, zero skipped, including 126 real PostgreSQL
regressions (16.15); existing 9112 datetime/deprecation warnings remain. Frontend
448 passed, zero skipped; OpenNext/Cloudflare build complete. Eight production Next
SSR groups pass against actual backend fixtures: historical/current manifests,
paired comparison, Chinese/English, empty windows, exact pins and no retired calls.
Alembic head remains 0018_asr_evidence_index; offline upgrade SQL passes.

Seven plans: compatibility 6/10=60% (50% → 60%), CI 0/4=0%, identity/session
1/5=20%, first controlled submit 2/6=33%, all14 commands 2/5=40%, corrections
1/5=20%, operations/company migration 0/6=0%. Denominators stay fixed; these are
acceptance milestones, not effort or production readiness. ROADMAP 34/44=77%; phase
percentages 100/100-demo/100-demo/89/89/60/0; read consumers 17/17.

DVP catalog/history are bounded, but replacement dvp_profile has unbounded linked
criteria/change-point/Issue arrays. Do not mark the DVP family complete or retire
its old GETs until these owned relations are paginated and the frontend migrated.
Next: DVP relation pages, then release/ASR, governance/audit, full inventory closure.
CI PR1 remains open/unmerged. Approved provider/session, real writes/recovery,
corrections and operations remain incomplete. Public staging remains read-only.
Cloud rollout evidence is recorded after publishing and live verification.

### Verified cloud rollout — Snapshot API 0.18.24

Feature commit ce57ab523ed610aa3f8da20fcf8e1e69ae87c089 (tree
c60515bfff14d9058d5d5c4f5b8c5eddb0a57002) is published to GitHub main.
Cloudflare Workers Builds: softwarelifecycle reports success for this exact commit,
completed 2026-10-04T14:31:30Z. HTTPS /health/ready reports API0.18.24 and exact
schema0018_asr_evidence_index; this is runtime behavior/version evidence, not a
claim about Render provider deployment identifiers or an exact Render commit.

Live checks: all 29 retired routes return HTTP410 with malformed old query fields;
SNAP-008 exact summary and artifact/rule pages preserve UUIDs/full counts, one-row
limits and empty end windows. Missing Snapshot pin returns422; wrong pin404.
Self-comparison summary/files carry both source_id/target_id; missing pair422 and
empty end window preserved. Four zh/en manifest/comparison views load successfully;
DVP bounded catalog remains200. Public empty snapshot POST returns403 read_only_mode.
The sample's small counts do not prove growth; SQL growth, historical comparison,
same-release, ambiguous identity and PostgreSQL regressions provide that evidence.

Plan delta: compatibility 50% → 60%; other plans remain 0/20/33/40/20/0%.
Next prioritize DVP owned relation pagination and consumer migration before retiring
its directory/detail. Then release/ASR, governance/audit and the 53-path closure.
ROADMAP remains34/44=77%, phase progress100/100-demo/100-demo/89/89/60/0;
read consumers17/17. Seven-plan report is reproducible with the reporting script.

## 2026-10-04 — API 0.18.25 DVP relations and legacy retirement

Codex cloud continued from main f4f9f786ef46ba13c9c6b652ba44b5b76d7922a1.
DVP profile replaces three full linked arrays with complete SQL relation_counts.
Independent criteria/points/issues pages require exact dvp_item_id, strict limits,
complete totals and stable display-number/UUID order. Frontend consumes these pages,
preserves independent offsets and historical execution filters, fails closed for
wrong parent and isolates unavailable children. History adds item_id; selected
Snapshot lookup now uses LIMIT1. Chinese default/English selectable remain.

Legacy DVP directory/detail GETs now return410 without DB work; cumulative reviewed
retirements29→31. Internal helper functions and all14 commands remain. External
profile array clients must migrate to counts and relation pages. No migration,
provider/grant change or public-write enablement.

Validation: backend1146 passed, zero skipped, including127 real PostgreSQL tests;
9141 existing/model deprecation and collection warnings remain. Frontend457 passed,
zero skipped; OpenNext/Cloudflare build succeeds. Ten production Next SSR groups
pass with real backend fixture: zh/en, independent pages, empty end windows,
historical OLD execution selection, invalid one-page isolation, stale parent fail
closed and no retired API requests. Growth covers105 records per relation,
nonunique criterion/change-point numbers, complete navigation, stable read-query
count and sibling isolation in SQLite/PostgreSQL. Read audit count stays unchanged.
Schema head0018_asr_evidence_index and full offline upgrade SQL pass.

Seven plans: compatibility7/10=70% (60%→70%); CI0/4=0%; identity/session1/5=20%;
first controlled submit2/6=33%; all14 commands2/5=40%; corrections1/5=20%;
operations/company migration0/6=0%. Fixed acceptance milestones are not effort or
production readiness. ROADMAP34/44=77%; phases100/100-demo/100-demo/89/89/60/0;
read consumers17/17. Release/ASR, governance/audit and full53-path closure remain.
Next review governance/audit callers and scoped bounded successors, then release/ASR
and full closure; CI, approved identity/session, real submissions/recovery,
corrections and operational/company acceptance remain. Public staging read-only.
Cloud rollout evidence is recorded after publishing and live verification.

### Verified cloud rollout — DVP API0.18.25

Feature commit7e5ed80a57a7a11f1c64aed663442d73b7d34d72 (tree
3f67f2b7ade4286b2b043e012fb04155b07c30df) is published to GitHub main.
Cloudflare Workers Builds: softwarelifecycle success for this exact commit,
completed2026-10-04T14:52:20Z. HTTPS health reports API0.18.25/schema0018.
This verifies runtime behavior/version; no exact Render provider commit/deployment
identifier is claimed. Final followup changes documentation only.

Live: all31 tombstones return410 with malformed old queries. DVP catalog and exact
profile return200; independent relation pages preserve item UUID, complete total,
one-row limits and empty end windows. Missing owned pins422, wrong owned pins404.
Execution history preserves item_id and original release/Snapshot context; explicit
recorded historical Snapshot selection succeeds. Six zh/en catalog/detail/empty-page
views pass. Empty public deployment POST remains403 read_only_mode. Small sample
counts do not prove growth;105-record SQLite/PostgreSQL regression supplies it.

Seven-plan report70/0/20/33/40/20/0%: plan1 advances60→70%; other rows unchanged.
ROADMAP34/44=77%, phases100/100-demo/100-demo/89/89/60/0, consumers17/17.
CI PR1 is still open/unmerged. Governance/audit, release/ASR and53-path closure
remain; then CI, approved identity/session, controlled command submissions/recovery,
corrections/revocation and operational/company acceptance. Public staging read-only.

## 2026-10-05 — API0.18.26 complete governance steps and legacy retirement

Codex cloud continued from maina18cc71816b89472f02e2b6a61fec50f5faed9a1.
Approval detail now uses scalar original-target summary, owned paged steps and
independent action history. Complete totals and exact approval UUIDs preserve
navigation beyond200 steps. Cursors/action filters preserve each other; wrong parent
fails closed, invalid child is isolated. Visible pending-step preparation retains
its exact UUID without inferring execution authority. Existing bounded200-step
profile remains compatible; internal legacy helpers and all14 commands remain.
Three legacy approval/audit GETs retire with DB-free410; total31→34. Exact event
payloads/actor identities and bounded audit catalog remain. No migration, provider,
grant or public-write change. Chinese default/English selectable preserved.

Validation: backend1155 passed, zero skipped (128 real PostgreSQL regressions);
9168 existing model/deprecation/collection warnings. Frontend465 passed, zero skipped;
OpenNext/Cloudflare build complete. Sixteen production Next SSR groups pass:
zh/en catalogs/exact records,205-step navigation, empty window, invalid one-child
isolation, stale-parent failure and no retired HTTP calls. SQL growth tests verify
complete traversal and constant read query count; PostgreSQL reads leave audit count
unchanged. Alembic head0018_asr_evidence_index and offline full upgrade SQL pass.

Seven plans: compatibility8/10=80% (70→80); CI0/4=0%; identity/session1/5=20%;
first submit2/6=33%; all14 commands2/5=40%; corrections1/5=20%; ops/company0/6=0%.
Fixed acceptance milestones are not effort/production readiness. ROADMAP34/44=77%,
phases100/100-demo/100-demo/89/89/60/0; read consumers17/17. Fixed53 candidate paths
remain. Next release/ASR family review and full-inventory closure; then CI, approved
identity/session, real submissions/recovery, corrections and operational acceptance.
Public staging read-only. Cloud rollout evidence follows publication/verification.

### Verified cloud rollout — governance/audit API0.18.26

Feature commitf21a81a97dff0336693de703af862b892ddde6a7 (tree
e96281b446457473b133abee1c40691b42b944b4) is published to GitHub main.
Cloudflare Workers Builds: softwarelifecycle succeeds for this exact commit,
completed2026-10-04T21:20:38Z (2026-10-05 Asia/Shanghai). HTTPS health confirms
API0.18.26 and schema0018_asr_evidence_index. This is runtime behavior/version
verification, not an exact Render provider deployment/commit claim.

Live: all34 tombstones return410 with malformed old queries; scalar approval summary
preserves exact original binding/full counts. Steps/actions preserve approval UUID/no,
one-row limit and empty end windows; wrong pins404, missing required step pin422.
Bounded decision/audit catalogs remain200; exact event payload and principal-identity
fields remain accessible. Ten zh/en approval/decision/audit directory/detail/empty-page
views pass. Empty public approval-action POST remains403 read_only_mode.
Small sample counts are not growth evidence;205-step SQLite/PostgreSQL regression
verifies navigation beyond the retained legacy bounded200-step preview.

Seven plans80/0/20/33/40/20/0%: compatibility advances70→80, others unchanged.
ROADMAP34/44=77%, phase percentages100/100-demo/100-demo/89/89/60/0; consumers17/17.
CI PR1 remains open/unmerged. Next release/ASR candidate review with per-route bounded
proof or explicit retirement, then full53-path closure. Approved identity/session,
real controlled command submissions/recovery, corrections and operations remain.
Public sample remains read-only. Final followup changes documentation only.

## 2026-10-05 — Release/ASR retirement and fixed-candidate closure, API0.18.27

The 19 release-family candidates are resolved: 16 legacy GETs now return HTTP410
without database access; three active scalar reads remain: exact ASR profile,
ASR downstream-summary and release coverage. Retained reads use full SQL counts,
no growing child arrays or child ORM graph, and preserve stored UUID/Snapshot scope.
SQLite growth checks compare fixed read-query count before/after120 records;
PostgreSQL verifies complete aggregates and no audit mutation. Existing downstream
summary tests cover the fixed seven count queries and exact recorded parent chain.

Retired paths are the combined/standard/application directories, rich exact SSR,
ASR decision/decisions/components/evidence/snapshot-policy/downstream/readiness,
and five version-only overview/verification/artifacts/readiness/decision reads.
Bounded summaries/catalogs/children remain. Version consumers first use exact
release-catalog/application/resolve and explicitly handle unique/ambiguous/missing;
no arbitrary release or UUID is inferred. SSR/components pages use the UUID path
and returned identity, not unsupported query pins. Evidence/frozen policy pages
pin selected Snapshot; passport children pin Snapshot/decision together. Current
readiness fails closed on stale selection. Working artifact/policy aggregates
and frozen Snapshot manifests/rules remain different scopes. Coverage preserves
any-PASS semantics; this slice does not infer latest-result semantics or approval.

Fixed53 candidates now equal50 retired +3 audited bounded, disjoint and exact.
All nine families and full closure pass: plan1 10/10=100% (80→100).
The corresponding ROADMAP endpoint acceptance item completes: Phase4 9/9=100%,
overall35/44=80%. Consumers remain17/17. Other plans remain0/20/33/40/20/0;
phase percentages100/100-demo/100-demo/100/89/60/0. This completes the fixed
compatibility scope, not authenticated submissions, CI or production readiness.

Validation:1191 backend tests pass with no skips, including129 real PostgreSQL
checks;465 frontend tests; Cloudflare/OpenNext build;18 production Next SSR
checks across nine views in Chinese/English; single migration head0018 and full
upgrade SQL. Existing warnings are deprecations/collection notices (9661).
No schema, provider, credentials or grant change; all14 POSTs and shared command
helpers remain. Public sample remains read-only. Cloud rollout still requires
independent feature-commit build and live API/page checks recorded below.

### Verified cloud rollout — release closure API0.18.27

Feature commit `cb41bac08a45d527c1001aeb6a49db8a69e592de` is on GitHub main.
Its exact Cloudflare Workers Builds check completed success at2026-10-04T21:37:58Z.
Live Render ready endpoint returns HTTP200, version0.18.27 and schema0018.
Render provider deployment ID/commit metadata is unavailable; this is independent
runtime version/behavior evidence, not a claim of verified provider commit identity.

Live checks pass all50 tombstones (including unknown identifiers and invalid old
query fields), three retained scalar reads, ten summaries/resolver responses,
15 bounded first/end page pairs with complete stable totals, wrong/missing Snapshot
pins, stale readiness and unsupported component-query pins. A newer catalog sample
has no Snapshot; evidence/page checks explicitly use the2.3.4 frozen sample rather
than assuming every release is frozen. Directory responses need not echo limit;
requested row bounds, totals and end windows are checked per actual contract.

All nine release directory/SSR/ASR/components/policy/passport/readiness/history
views pass online in default Chinese and selectable English (18 checks). Empty
Snapshot-create and Deployment POSTs return403 read_only_mode; no business mutation
is submitted. No provider/credential/grant/company-target setup occurred.

Final progress: plans100/0/20/33/40/20/0; fixed denominators10/4/5/6/5/5/6.
ROADMAP35/44=80%; phases100/100-demo/100-demo/100/89/60/0; consumers17/17.
Next package: CI PR#1 is still open/unmerged; reconcile it with current main,
validate backend/PostgreSQL/migrations/frontend and establish mainline gates.
Then approved identity/session and controlled submissions, broader append-only
correction/revocation and production operations remain. The project is incomplete.

## 2026-10-05 — CI integrated and verified on main

Mode: Codex cloud. Started from a18cc71816b89472f02e2b6a61fec50f5faed9a1.
PR#1 was reconciled with current main without restoring old API0.18.13 documents
or undoing the fixed53 compatibility closure. Updated feature c156d1e01fa41ea8062f05c899bdeb47d95df5da
passed PR run37248117693. Merge 479e0a292e921b1f325985038903d71edafa7a8c passed main push run37248330054.
See https://github.com/Wang106/SoftwareLifeCycle/actions/runs/37248330054.

Python3.12/PostgreSQL16 backend1204 passed, no skips (1191 existing +13 CI gate/
target-guard tests);129 real PostgreSQL cases are retained, including ordinary
module database fixtures. The report gate's named _postgres count is a narrower
classification, not the total real-database count. Single0018 head, full upgrade
and head downgrade SQL, isolated upgrade/downgrade/re-upgrade, report gate and
artifact upload pass. Node22 frontend465 passed and OpenNext production build pass.
The stable CI acceptance job requires both validations to succeed. Local execution
of all16 success/failure/skipped/cancelled dependency combinations allows only
both-success; process regressions reject malformed/missing/empty/failed/error/
skipped/no-PostgreSQL reports and prevent remote/company database connection.

Actions run on main push, PR and manual dispatch, with SHA-pinned actions,
read-only repository token, no persisted checkout credentials and disposable
PostgreSQL data. No deployment/OIDC/company credentials or grants were introduced.
This does not install branch protection or make independent Render/Cloudflare
automatic deployment wait for CI. CI failures make the workflow/check red;
merge/deployment enforcement and recovery remain separate operations work.

CI plan2 now4/4=100% (0→100); plans100/100/20/33/40/20/0 retain fixed denominators.
The ROADMAP CI item completes:36/44=82%, phases100/100-demo/100-demo/100/89/60/17.
Plan7 still0/6 because its fixed environment/restore/monitor/release/network/data
milestones are broader than adding CI. Read consumers17/17 and53=50+3 remain.
API0.18.27/schema0018 and public sample read-only remain; deployment health and
Cloudflare build evidence are recorded separately below.

Next: approved OIDC provider/controlled target configuration, browser session and
audited grant administration, then first authenticated submissions/recovery/results;
all14 commands, broader append-only corrections and operational acceptance follow.
No approved provider or company target is inferred from CI success. Backup/restore,
monitoring, environment separation, gated deploy/rollback and company network/data
acceptance are still incomplete. This is not a production-ready certificate.

### Deployment/runtime evidence after CI merge

Merged-main Cloudflare Workers Builds completed success at2026-10-05T00:40:34Z
for479e0a292e921b1f325985038903d71edafa7a8c. Live API ready200 reports0.18.27
and0018_asr_evidence_index; no API or schema change. Default Chinese and English
release directory pages return200. Empty Deployment POST returns403 read_only_mode;
no business mutation is submitted. Render provider commit/deployment metadata was
not obtained; runtime health/version is the evidence. Follow-up is documentation/
fixed-ledger only. The successful main Actions run is37248330054.

## 2026-10-05 — Cloudflare Preview failure triage, unresolved provider log

Mode: Codex cloud; starting main91ad0b55. The user mail refers to c156d1e PR#1
Preview failure a3ca5368, not a current production failure. Main479e0a2 and91ad0b5
Cloudflare builds succeeded;91ad0b5 CI37248690400 succeeded. Fresh live checks pass
Chinese/English release catalog200, API0.18.27/schema0018 ready200 and empty
Deployment POST403 read_only_mode, without business mutation.

Draft PR#2 /40e23fe fixes a verified missing Worker Previews block and explicit
sample API binding, adds Wrangler configuration preflight and four regressions.
CI37249193295 passes backend1204/no skips, frontend469/no skips, preflight and
OpenNext build. Its Cloudflare Preview44a78aac still fails; no Preview URL exists.
This configuration fix is not a verified remote failure resolution and is unmerged.
Cloudflare log access requires login; the cloud browser verification fails even
after one reload. No error lines or actual Preview command were obtained.

See docs/cloudflare-preview-incident.md. Next obtain the first provider ERROR and
its surrounding log/command, fix based on evidence, verify a new Preview URL, then
merge. Current main includes incident documentation only; public settings remain.
Then approved identity/session/controlled submissions, corrections and operations
remain. Plans100/100/20/33/40/20/0; ROADMAP36/44=82%; module percentages
100/100-demo/100-demo/100/89/60/17, read consumers17/17 and53=50+3 unchanged.
No milestone is awarded for the unmerged Preview patch.

## 2026-10-05 — Work conversation continuation and explicit Preview URL activation

Mode: Codex. Engineering baseline main `4ec8dcf3395e719590749bc7dd125b1d856dbda1`;
continued existing draft PR#2 at `3a349b2bf29dbc11bb6597521c1256d78641bdad`.
Personal-context retrieval returned selected summaries from SoftwareLifeCycle_CodeX,
including the latest continuation request and interrupted push. It did not return
an exact ten-message transcript; no ten-message analysis is claimed. The Library
API/database guide was read; its older schema0010 instructions do not supersede
current API0.18.27/schema0018 repository state. Source inventory and evidence are
recorded in docs/work-conversation-continuation.md.

The remote update had completed: Actions37304274627 succeeded and Cloudflare's
PR comment reports Preview deployment794eff35-0645-4262-a9a4-d0bee4fbf185 successful
for3a349b2 at2026-10-05T11:40:05Z, but explicitly says No Preview URL / Enable.
This supersedes the earlier pending/failed status for40e23fe; an inaccessible URL
is not a failed build. Both root and frontend now explicitly set preview_urls=true.
Preflight rejects absent, false and non-boolean settings; existing explicit sample
API bindings and OpenNext configuration remain checked.

Cloudflare documents that the host switch is applied by wrangler deploy, so an
initial main deployment is needed before expecting accessible branch URLs. Merge
requires successful current CI/Preview build; URL/page verification follows that
activation deployment. Do not infer a URL or claim runtime validation from build
success. Local frontend471 tests pass, no skips; final OpenNext and remote CI/build
results are recorded in a subsequent follow-up. No backend/schema change.
ROADMAP36/44=82%; modules100/100-demo/100-demo/100/89/60/17; seven plans
100/100/20/33/40/20/0 unchanged. Next complete activation/runtime verification,
then provider/session, controlled submissions/recovery, correction and operations.

### Verified publication and main deployment — 2026-10-05

Feature commit7e6cc65063dbfb7036c878365c84297ee17fdbdd passed Actions37314835622:
backend1204/no skips, PostgreSQL/migration evidence, frontend471/no skips,
Wrangler preflight and OpenNext build. Cloudflare Preview build7a047640 succeeded;
deployment824250e1-18fc-4924-ad95-377b6ca1319f still reported No Preview URL / Enable.
PR#2 merged as7738bd9b6db43c773f88bb3c88522927eb0cfd91. All four exact-main checks
(CI acceptance, backend, frontend, Workers Builds) completed success. Production
Cloudflare builde072f852-331d-44ab-bf73-d47fbe00b577 completed2026-10-05T13:17:51Z.
The explicit Preview host configuration is now deployed; actual returned branch
URL verification remains outstanding. No accessible Preview URL was obtained.

Fresh sample API health returns200/version0.18.27/schema0018_asr_evidence_index.
An empty Deployment POST returns403 {"detail":"read_only_mode"} with no mutation.
This execution environment's HTTPS requests to the Chinese and English production
release pages both return403, so bilingual live-page acceptance is not claimed.
The cause of those403 responses is not established; do not assume an application
failure or a particular provider rule. Render provider commit identity was not
checked. Local471 tests/build and exact-main remote checks are independent evidence.

The Git CLI initially hit approval review; verified repository1392323013 owner,
public visibility and admin/push permission allowed a retry, which failed for absent
CLI credentials. Publication used the connected GitHub service with non-force
branch updates. This final follow-up changes documentation only.
ROADMAP36/44=82%; seven plans100/100/20/33/40/20/0; module percentages unchanged.
Next obtain returned Preview URL/page-access evidence, then the approved identity/
session and controlled-write development sequence described above.

## 2026-10-05 — Current identity and bounded own-grant reads, API0.18.28

Mode: Codex. Starting main9f39932ee5501c06150295e931a1b67f1a8f7631.
Added authenticated GET /api/v1/security/me and /grants for future browser-session
integration. OIDC signature/issuer/audience/time and ACTIVE local identity checks
are reused; exact local identity is rechecked before reading grant counts/pages.
Only self UUID/type/display name is returned, with read-only status and complete
active counts. No issuer/subject/email/token is exposed. Own GLOBAL/PROJECT/SOFTWARE
grants use required scope, strict query fields, max100 rows and full totals; suspended
memberships and other principals are excluded. Responses are private/no-store and
vary on Authorization, including auth/query denials. Public/auth-disabled deployments
return401, not demo identity. Existing14 write contracts and schema0018 remain.

SQLite and real migrated PostgreSQL regression cover signed token rejection,
self isolation, suspended/disabled identity, mid-request disable recheck, SERVICE/no
roles, strict queries, privacy/cache controls and106-grant complete pagination with
constant query count. Local targeted checks pass; complete cloud CI/PG and rollout
are recorded after publication. No provider, real browser session or grant-admin
mutation is configured. ROADMAP36/44=82%; modules100/100-demo/100-demo/100/89/60/17;
seven plans100/100/20/33/40/20/0 unchanged: this extends an already-complete identity
foundation milestone, not provider/session acceptance. Next approved provider/target
configuration and browser session, then authenticated submission/recovery remain.

### Verified identity API rollout and Preview mail — 2026-10-05

Feature6ec12bc56dc5308cd124c6d563e2424e3aebd79e passed PR Actions37317778657:
backend1250/no skips, frontend471/no skips, PostgreSQL/migration round trip and
OpenNext build. New self-read tests add46 cases:23 SQLite and23 real migrated
PostgreSQL. PR#3 merged as013d7abd0be28dc4645745bd455a95c75553aa16. Its exact-main
Actions37318388790 and all four checks succeeded (acceptance at13:42:24Z).
Cloudflare production buildd25323eb-8e2a-4fa7-bc77-2415223622b4, completed13:40:24Z, Version ID
327ce510-ca0e-4558-b24c-0017e00fcd87.

The user's Cloudflare email matches PR#3's provider comment: commit6ec12bc,
Preview deploymentc0aa288e-f92a-4bab-83b6-39fe34bf0832 at13:37:23Z,
Build Success and Deployment Success. The actual returned Preview URL is
https://codex-current-identity-20261005-softwarelifecycle.whf969.workers.dev
and immutable deployment URLhttps://c0aa288e-softwarelifecycle.whf969.workers.dev.
This confirms the earlier explicit preview_urls switch is now effective; the mail
is a success notification, not the previous missing-previews failure.

Fresh Render runtime ready returns200/version0.18.28/schema0018_asr_evidence_index.
GET /security/me and /grants return401 oidc_not_enabled in public auth-disabled
staging, with private,no-store, Vary Authorization and Bearer challenge. Empty
Deployment POST remains403 read_only_mode. No business mutation was submitted.
Render provider deployment/commit identity was not obtained; runtime version and
behavior are verified separately.

Preview release-page requests with slc_language=zh and=en both returned403 and
body error code1010 from this execution environment. Cloudflare documents1010 as
a browser-signature access rejection:
https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/
No exact security rule was inspected or changed. An actual URL and successful
deployment are verified; bilingual live page access is not. Local/remote frontend
tests and production build pass independently of that runtime-access limitation.

Final follow-up is documentation only. ROADMAP36/44=82%; modules
100/100-demo/100-demo/100/89/60/17; seven plans100/100/20/33/40/20/0 unchanged.
Own-identity reads extend the existing foundation; provider/browser-session/grant
administration and controlled submissions remain incomplete. Next provider/controlled
target configuration and browser login/logout/expiration, followed by submission/
recovery, all14 commands, corrections and operational/company acceptance.
