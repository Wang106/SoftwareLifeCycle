# Changelog

## 2026-10-02 — Shared release coverage SQL aggregates

- Replaced full child/history loading and Python ID arrays with relational CTE scopes and one aggregate result; latest Snapshot selection uses LIMIT 1.
- Preserved exact software/project/release/Snapshot scope, distinct binding union, any-PASS semantics and all response fields; other profile reads still need migration.
- API 0.18.6; no migration, head remains 0018_asr_evidence_index. All command contracts/security/atomic audits stay; staging remains read-only. Roadmap stays 34/44.
- Verification: 14 new coverage tests passed within the full Python 3.12 backend suite: **784 passed, 4873 warnings, no skips**, including **106 real PostgreSQL 16.15 tests**. Tests cover union/distinct/any-PASS semantics, exact release/snapshot exclusion, old/empty/invalid/missing selection, software/project/missing-detail scope, recorded missing metadata, 120-item growth with fixed three cold STANDARD queries and no child ORM/private text, migrated PostgreSQL aggregate results and no audit write. Existing real retry/concurrency/quota/rollback/authorization regressions passed. Frontend **293 passed, no skips**; final Next/OpenNext Cloudflare production build passed. Single Alembic head and PostgreSQL full upgrade SQL generation passed; no new migration.

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

## 2026-10-02 — ASR pinned evidence pagination

- Added exact snapshot summary, paginated frozen artifacts and latest DVP execution per item UUID; mismatched scope is rejected and missing metadata remains visible.
- Migrated ASR evidence consumer to independently paginated tables with stable snapshot scope, bilingual labels and no unbounded fallback. Legacy API shape stays; profile coverage and other consumers remain unbounded.
- API 0.18.5; new index-only migration 0018_asr_evidence_index, no domain-history or command/security change. Staging remains read-only; roadmap stays 34/44.
- Verification: 20 new evidence tests passed within the complete Python 3.12 backend suite: **770 passed, 4281 warnings, no skips**, including **105 real PostgreSQL 16.15 tests**. Coverage includes exact/sibling/wrong-type scope, missing/empty snapshots, stable duplicate ordering, newest execution per item UUID on only the selected release/snapshot, duplicate item numbers across plans, missing metadata retention, pinned pagination after a newer Snapshot and 105-row growth with unchanged SQL query count, bounded row projections and no private payload columns. Real PostgreSQL verifies the window query, no audit write, index columns and downgrade/upgrade without lost execution rows; existing concurrency/replay/quota/rollback tests also passed. Frontend **293 passed, no skips**, final Next/OpenNext production build passed. Seven local SSR groups passed across Chinese/English for full counts, missing metadata, independent first/next offsets with pinned snapshot and exact command UUID, historical pin, beyond-end/invalid-array pages, unavailable/no-snapshot summary stopping page reads and no legacy evidence request. Single Alembic head, PostgreSQL full upgrade SQL and 0018-to-0017 downgrade SQL passed.

Online verification after feature commit `26a170653e3892654ea23391cb95a0a41525585c`: Render deployment `dep-davjra8473hc73f79r90` is live for that commit (finished 2026-10-02T05:15:15Z). Health returned 200 / API 0.18.5 / 0018_asr_evidence_index. Independent read-only Render SQL confirmed both Alembic revision 0018 and the exact non-unique B-tree index columns. Exact ASR 2.3.4 summary returned SNAP-008 UUID c6f38c25-c42e-4bdb-8327-e16f7e85dd7b, 4 artifacts, 3 latest item executions and 1 other-snapshot execution. Two one-item pages for each collection returned distinct UUIDs with unchanged full totals and no private storage/result fields. Malformed snapshot/oversized limit returned 422; another release with this snapshot returned 404. Harmless empty Snapshot and exact Deployment Batch POSTs returned 403 read_only_mode. Cloudflare live Chinese evidence summary and one-item pages were verified: artifact second page retained DVP first page, then DVP second page retained artifact second page and exact snapshot; English switching retained both offsets, UUID, totals and raw hashes; Chinese restored for the final proof. Exact Snapshot preparation target remained the release UUID. No business write was submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live new feature behavior is frontend evidence. Public staging remains read-only. The initial combined read-only SQL probe was rejected because the connector accepts one prepared statement; two separate read-only queries succeeded without database mutation.

## 2026-10-02 — ASR downstream fixed summary and scoped history

- Added six all-status counts and separate actual/batch release observations, preserving the exact legacy stored-parent chain and mismatched records.
- Added validated production authorization_release_id filter; existing release_id semantics remain. Migrated ASR downstream to summary + six paginated catalog links, retaining scope across paging/filter/kind navigation and bilingual default Chinese.
- Missing/wrong-ID summaries stay unknown without unbounded fallback; other ASR evidence/profile and compatibility consumers remain unbounded.
- API 0.18.4/head 0017, no migration or command/security contract change; staging stays read-only. Roadmap remains 34/44.
- Verification: 17 new summary/scope tests passed within the complete Python 3.12 backend suite: **750 passed, 3915 warnings, no skips**, including **104 real PostgreSQL 16.15 tests**. The new migrated-PostgreSQL test verifies aggregates, mismatch-preserving catalog scope and no audit writes; the existing real lock/retry/quota/rollback tests also passed. Frontend: **292 passed, no skips**; final Next/OpenNext Cloudflare production build passed. Eight local SSR verification groups passed for Chinese/English full totals and exact links, empty/unavailable/wrong-ID summaries, three catalogs preserving the scope through API/filter/first-next/kind links and no legacy downstream fallback. Single Alembic head 0017 and PostgreSQL SQL generation passed. No migration.

Online verification after feature commit `338a3231315a7a7623086f0ca347ddbccd265282`: Render deployment `dep-davjddgjo6nc738ln230` is live for that commit (finished 2026-10-02T04:45:42Z). Health returned 200, API 0.18.4, database revision 0017_deployment_actual_version; independent read-only Render SQL confirmed that revision. Exact ASR 2.3.4 summary returned six counts of 1, actual same/different/unreported 1/0/0 and batch same/different 1/0. Three authorization_release_id catalogs returned total 1 and exact linked record UUIDs. Missing summary returned 404; malformed authorization_release_id returned 422. Empty Snapshot and exact Deployment Batch POST probes returned 403 read_only_mode. Cloudflare live Chinese summary, English switching, six scoped links, exact Snapshot preparation UUID, English persistence through catalog navigation, Batch filter submit and cross-kind Changeover navigation preserving scope were verified in the browser. The sample has only one row per scope, so next-page behavior is local SSR/test evidence, not live multi-page evidence. No business write was submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live new feature behavior is frontend evidence. Initial browser navigation/frame-tree probes timed out; the same browser's documented tab/DOM API recovered without changing site or network settings. Public staging remains read-only.

## 2026-10-02 — Default Chinese / English across the interface

- Added shared locale provider, dictionary/templates and persisted language-only cookie; Chinese is the default on initial SSR and invalid preferences. Switch updates title/lang without remounting forms.
- Localized all 63 current pages, navigation/shared catalogs, 14 preparation forms, validation/status text and error/not-found recovery. Explicit option values preserve raw API tokens. Original customer evidence, IDs, links, code and exported JSON remain unchanged.
- Added localization/AST coverage tests and interface documentation; no backend/API/schema change, API 0.18.3/head 0017, no migration. Public staging remains read-only; roadmap stays 34/44.
- Verification: frontend 292 tests, full backend 733 tests (103 real PostgreSQL), final Cloudflare build; 126 local bilingual SSR checks, invalid cookie fallback and stable raw form values for 14 operations. Live bilingual/persistence/immutable-request checks passed; see rollout evidence below.


## 2026-10-02 — Exact delivery revision bounded reads

- Added exact revision profile with full artifact/distribution totals, fixed policy counts and distinct control count; no embedded child history.
- Added validated artifact pagination, deterministic duplicate-name ordering, visible missing metadata and omitted storage references.
- Migrated the delivery detail to profile/paged manifest and exact-package distribution catalog links; retained preparation/audit UUIDs, legacy reads and all write contracts.
- API 0.18.3/head 0017, no migration; public staging remains read-only. Roadmap stays 34/44 (77%).
- Verification: 19 new delivery profile/artifact tests pass within the complete Python 3.12 backend suite: 733 passed, 3568 warnings, no skips, including 103 real PostgreSQL 16 migrated-schema concurrency/integration tests. Frontend: 214 passed, no skips; final Next/OpenNext Cloudflare production build passed. Eleven local SSR checks passed for full totals, exact UUID/revision links, first/next paging, empty/missing parents, lost metadata, beyond-end page, unavailable/invalid/array pagination, missing profile without fallback, invalid revision without API calls and profile/artifact-only reads. No migration. Online verification after feature commit `1efe0c28e2c5d68a36b00103b540329a38b1df04`: Render deployment `dep-dava0k6417fc73ds081g` is live for that commit (finished 2026-10-01T18:03:49Z). Health returned 200 with API 0.18.3 and revision 0017_deployment_actual_version; read-only PostgreSQL SQL independently confirmed that revision. DP-0226 revision 1 profile returned 200, exact package UUID, counts 3 artifacts/1 distribution, policy counts 2 ALLOW/1 APPROVAL_REQUIRED/0 OTHER and 1 distinct control. Two one-item artifact pages returned distinct exact UUIDs with total 3, next offsets 1/2 and no storage references. Missing exact revision returned 404; limit 101 returned 422. Empty Delivery/Distribution POSTs returned 403 read_only_mode. Cloudflare live detail, first/next artifact paging with unchanged full totals and exact-package distribution catalog were verified in the browser; no business writes were submitted. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is frontend evidence. The first Render log query failed with a provider Loki 502/503; a subsequent query succeeded with no recent error logs, without application changes.


## 2026-10-02 — Bounded authorization/distribution details

- Added two exact profiles with full history counts and parent/revision context, omitting unbounded child arrays.
- Migrated both details to scoped paginated history links; retained all-status quota counting and exact command-preparation UUIDs.
- Legacy shapes and all 14 write contracts remain; API 0.18.2/head 0017, no migration, staging read-only.
- Verification: 15 new profile tests passed, including exact/sibling scope, missing context, unchanged legacy shapes, read-only routes and 105 added histories with fixed query counts and no child payload loading. Full Python 3.12 backend suite: 714 passed, 3477 warnings, no skips, including 103 real PostgreSQL 16 tests. Frontend: 214 tests passed; production Next/OpenNext build passed. Seven SSR checks passed for exact links/revision/command UUIDs, all-status counts/zero clamp, unlimited/empty history, missing delivery, both unavailable profiles and profile-only API calls. No migration. Online verification after feature commit `c1348ed445918d5dfac225dd7386a79a83317a9b`: Render deployment `dep-dav9mlvlk1mc73be8h8g` is live for that commit. Health returned 200 with API 0.18.2 and database revision 0017_deployment_actual_version; read-only PostgreSQL SQL independently confirmed that revision. Exact PA-0081 and DIST-0326 profiles returned 200 with counts 1/1 and 1 respectively, exact parent references and no embedded histories; missing profiles returned 404. Harmless empty Authorization and Distribution POSTs both returned 403 read_only_mode. Cloudflare live details and exact-distribution authorization/exact-authorization batch catalog links were verified in the browser; no business write was submitted. Recent Render error logs were empty. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is the frontend evidence.

## 2026-10-02 — Bounded deployment detail reads

- Added exact deployment profile with full history counts and parent chain; omitted unbounded history payloads.
- Migrated deployment detail to profile plus scoped bounded-catalog links; separated stored status from actual UUID-pair observation.
- Preserved legacy read shapes and all 14 write contracts; no migration, API 0.18.1/head 0017, public staging read-only.
- Verification: 11 new deployment-profile tests passed, including exact scope, missing references, legacy shape, stored/observed mismatch, 106/107 history counts without row loading and unchanged SQL query count. Full Python 3.12 backend suite: 699 passed, 3267 warnings, no skips, including 103 real PostgreSQL 16 tests. Frontend: 214 tests passed; production Next/OpenNext build passed. Four SSR checks passed for large history/exact catalog links, empty/missing delivery, unavailable profile and profile-only API calls. No migration. Online verification after feature commit `a3ea30e3bd0b8181c24f37a35289835c0d462626`: Render deployment `dep-dav9frnavr4c7396mtu0` is live for that commit. Health returned 200 with API 0.18.1 and database revision 0017_deployment_actual_version. Exact DEP-0081 profile returned 200, counts 1/1, MATCH observation and actual_version 0 without embedded histories; missing profile returned 404. Harmless empty Deployment and Batch POSTs both returned 403 read_only_mode. Read-only PostgreSQL SQL independently confirmed head 0017. Cloudflare live deployment detail and exact-deployment batch/exact-delivered-snapshot decision catalogs were verified in the browser; no business write was submitted. Recent Render error logs were empty. Cloudflare provider deployment ID/commit metadata was unavailable; live feature behavior is the frontend evidence.

## 2026-10-01 — Phase 6 final request-preparation forms

- Added Test Release, Deployment and Changeover; all 14 current command forms now prepare reviewed keyed exports.
- Added exact frozen snapshot, authorization, line and deployment context entries; no previous version, purpose or active status is inferred.
- Preserved DRAFT/PENDING/history-only business boundaries, explicit UTC/null time semantics and existing TR hyphenated versus DPLOY/CO hex audit numbers.
- No backend/API/schema/migration or public-write changes; API 0.18.0/head 0017 and staging read-only remain. Authenticated submission/result recovery and broader correction/revocation are pending.
- Verification: 214 frontend tests passed (38 added); production Next/OpenNext build passed; seven SSR context/default checks passed; full backend suite passed 688 tests including 103 real PostgreSQL 16 concurrency/integration tests, with no skips. No migration or backend contract change. Online verification after feature commit `210b124e3b2a0b3a04b9ddcb75f913e3a514d2a9`: Cloudflare serves all 14 forms; exact snapshot/authorization/deployment context, explicit purpose/source, UTC conversion, review invalidation and confirmed copy were exercised without business submission. Repeated Deployment copy retained the same body/key. `/health/ready` returned 200 with API 0.18.0 and revision 0017; Test Release, Deployment and Changeover POST probes each returned 403 `{"detail":"read_only_mode"}`. Read-only Render SQL independently confirmed `0017_deployment_actual_version`. Render backend remains live on bbd8a42; no backend redeploy was required. Cloudflare rollout was verified by live page behavior; a provider deployment ID was not available.


## 2026-10-01 — Phase 6 distribution-chain request preparation

- Added Delivery/Distribution/Authorization to /commands: eleven of 14 forms now prepare confirmed immutable keyed exports.
- Added exact revision/package/distribution context entries and visible artifact/customer/project/release UUIDs. No file or recipient is auto-selected.
- Delivery canonicalizes a distinct frozen-artifact set; explicit revision and finite quota enforce PostgreSQL integer bounds. Unlimited is an explicit choice. Exact policy/declaration text is retained.
- Authorization creation remains DRAFT; preparation does not send files, acknowledge receipt, authenticate or submit.
- No backend/API/schema/migration changes; API 0.18.0/head 0017 and public read-only protection remain.
- Frontend tests: 176 passed, no skips (65 added distribution-chain cases). Final Next.js/OpenNext Cloudflare Worker production build passed. Complete Python 3.12 backend suite: 688 passed, 3179 warnings, no skips, including 103 real PostgreSQL 16.15 tests in a fresh isolated /tmp cluster. Six local SSR checks passed for all three exact UUID targets, empty explicit defaults/ignored recipient-artifact-limit query prefill, missing/array targets and Create entry. Initial local next start hit the workspace networkInterfaces limitation; explicit 127.0.0.1 host resolved it without application changes. No migration. Feature commit `a8f299afddc5da23d8a5b00d53cb316b8519e46c` is pushed to main. Live Cloudflare UI verified eleven choices; exact release/package/distribution UUID entry links and visible frozen artifact/customer/project UUIDs; duplicate Delivery file rejection, review confirmation and stable copy after asynchronous clipboard completion; Distribution recipient edit invalidation; zero-limit rejection, finite export and explicit unlimited null only after clearing the limit; Authorization confirmation/copy. No business submission was made. Cloudflare live behavior is verified, but a provider deployment ID/commit binding is unavailable. Render connector confirms unchanged backend deployment dep-dav0vf0473hc73a8vl10 remains live at bbd8a42b567c4f5b2c83017c570e47039442f3af (API code 0.18.0). Current Render logs show GET /health/ready 200 at 2026-10-01T14:29:00Z. A read-only Render PostgreSQL query directly returned 0017_deployment_actual_version; provider inventory reports PostgreSQL 18, while local concurrency tests use 16.15. Direct API health-body and the three delivery/distribution/authorization 403 read_only_mode probes were blocked by workspace network policy, so fresh direct responses are not claimed. Public read-only configuration/code were unchanged; prior direct 403 evidence remains historical.


## Evidence/reference request preparation — 2026-10-01

- Codex adds Impact, Acceptance-to-DVP and Resource preparation: explicit UUIDs/judgments/reasons, canonical text, immutable confirmation/copy and expected record/audit links.
- Evidence/coverage pages expose exact UUIDs and context entries; missing snapshots/items are not invented. Resource URL/path text is validated without fetching/opening/uploading.
- Eight of 14 forms prepare requests (57% of forms); login/submission/result recovery and six forms remain. Overall roadmap remains 34/44 (77%), Phase 6 3/5 (60%).
- No backend/schema/API change or migration; API 0.18.0/head 0017 and public read-only settings remain.


- Verification: frontend 111 passed; Next.js/OpenNext builds; complete backend 688 passed, no skips, including 103 real PostgreSQL tests; six local SSR context/input cases passed. Feature commit `5c95c961fb1907bf473dbec012adc4e1b66bf431` is pushed to main. Live Cloudflare UI verified all eight choices, exact Issue/release/snapshot and SCR/criterion prefill, explicit DVP selection, review confirmation, stable Impact copy, credential-URL rejection, inert local-path Resource preparation/copy and edit invalidation. No business submission was made. Health returned 200 with API 0.18.0 and database revision 0017_deployment_actual_version; Impact, Acceptance-to-DVP and Resource write probes each returned 403 read_only_mode. Unchanged Render backend deployment dep-dav0vf0473hc73a8vl10 remains live at bbd8a42b567c4f5b2c83017c570e47039442f3af. Cloudflare live behavior is verified; a provider deployment ID/commit binding was not available.

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
