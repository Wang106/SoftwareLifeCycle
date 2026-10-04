# SoftwareLifeCycle Development Handoff

## Handoff identity

- Date: 2026-10-04 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Verified starting baseline: `79e5f767d74c818d2642aee8408d47c5ec733717`
- Developed from: `79e5f767d74c818d2642aee8408d47c5ec733717`
- Baseline subject: `docs: record verified SCR detail cloud rollout`
- Source of truth: GitHub `main`, followed by code, migrations, tests and live health checks

Before continuing, fetch `origin/main`, confirm the branch/working tree and read this file together with `PROJECT_STATUS.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `API.md`, `DATABASE.md`, `SECURITY.md` and `docs/write-contracts.md`. Do not infer completion from a prior chat.

## Product and solution summary

SoftwareLifeCycle is an automotive BMS/ECU software-lifecycle governance platform. Its implemented trace chain is:

```text
SCR → DVP → Snapshot → Readiness → Approval → Release Decision
    → Delivery → Distribution → Production Authorization
    → Deployment → Changeover → Batch
```

The solution is evidence-oriented:

- formal relationships use stored UUIDs rather than matching display names or versions;
- release evidence is pinned to an exact frozen Snapshot;
- formal judgments and links are append-only where the schema provides protection;
- every current command writes its domain change and audit event in one transaction;
- OIDC mode resolves an ACTIVE local principal and exact software/project role before a write;
- the public environment contains demo data only and remains read-only.

## Architecture and deployment

| Layer | Current implementation | Current state |
| --- | --- | --- |
| Frontend | Next.js 15 / React 19, Cloudflare Worker through OpenNext | `https://softwarelifecycle.whf969.com`, browser User-Agent HTTP 200; Python User-Agent 403/1010 |
| API | FastAPI + SQLAlchemy services | Render API 0.18.16 starting baseline; 0.18.17 rollout pending |
| Database | PostgreSQL (Render 18; local tests 16) + Alembic | Required/verified revision `0018_asr_evidence_index` |
| Identity | Provider-neutral principals and scoped global/software/project roles | Implemented in code; approved OIDC provider not configured |
| Public-write protection | `READ_ONLY_MODE=true` | Verified write rejection: HTTP 403 `read_only_mode` |
| Engineering source | GitHub `main` | Baseline above was pushed successfully |

Runtime flow:

```text
Browser
  → Cloudflare-hosted Next.js
  → Render FastAPI
  → PostgreSQL
```

The frontend performs read-oriented catalog/profile workflows. Write APIs exist for controlled development, but no public write UI or non-read-only public target is approved.

## Development progress

Progress is the count of checked items in `ROADMAP.md`. It is a roadmap-completion measure, not a production-readiness certificate.

| Phase | Completed | Progress | Status |
| --- | ---: | ---: | --- |
| Phase 1 — Domain foundation | 5 / 5 | 100% | Complete |
| Phase 2 — Release governance | 5 / 5 | 100% | Complete for demo scope |
| Phase 3 — Distribution and production trace | 5 / 5 | 100% | Complete for demo scope |
| Phase 4 — Evidence, review and auditability | 8 / 9 | 89% | Compatibility-list migration remains |
| Phase 5 — Identity and authorization | 8 / 9 | 89% | Approved OIDC provider configuration remains |
| Phase 6 — Controlled write experience | 3 / 5 | 60% | Safety slices and UI priorities implemented; submission/correction/result items partial |
| Phase 7 — Production operations | 0 / 6 | 0% | Not started |
| **Overall** | **34 / 44** | **77%** | Demo lifecycle is coherent; controlled writes and operations remain |

## Completed capabilities

- End-to-end release, governance, distribution and production trace with exact stored relationships.
- SSR/ASR profiles, component deltas, frozen manifests, snapshot history/comparison, release matrix and software passport.
- SCR, Issue and DVP catalogs; snapshot-scoped coverage, impact evidence and append-only judgments.
- Approval actions, release decisions, delivery revisions, distributions, production authorizations, deployments, changeovers and batches.
- Bounded/filterable DVP, distribution, production, governance and audit catalogs.
- PostgreSQL append-only protection for audit events, impact assessments, acceptance-to-DVP links and resource links.
- Explicit security/consistency contracts for all 14 write routes.
- OIDC validation and exact scoped authorization for all 14 write routes when OIDC mode is enabled.
- Trusted authenticated-actor binding and atomic audit events for all 14 current write routes.
- Snapshot and production-command rollback tests proving that an audit failure leaves no domain change.
- Starting baseline full regression: 983 backend tests under Python 3.12, including 122 real PostgreSQL tests without skips. Current verification is recorded below.
- Optional request-ID replay and PostgreSQL serialization for Snapshot numbering, shared Production Batch quotas, Approval Action and Release Decision, without a new migration.

## Current limitations and risks

1. No approved OIDC issuer, audience or JWKS endpoint is configured in a target environment.
2. There is no audited principal/grant administration API or browser login/session flow.
3. All 14 current routes support keyed retry; optional legacy/no-key paths retain weaker semantics.
4. Snapshot numbering and shared production batch-limit checks are now serialized with PostgreSQL row locks. Approval actions and release decisions now share transaction locks; Deployment/Changeover now have retry and locks; actual reports now have keyed retry/version checks and audited corrections.
5. Actual software has keyed retry/version/correction protection; legacy no-key reports may still overwrite without a precondition.
6. Some legacy list/history endpoints remain unbounded.
7. CI, backup/restore, monitoring, alerting and incident runbooks are not present.
8. Public reads are suitable only for non-sensitive sample data; CORS is not access control.

## Recommended next development package

The first Phase 6 package below is implemented for Snapshot and Production Batch. The fifth package completes actual-software keyed retry/version/correction; next implement **approved identity/session and controlled submission with outcome recovery** and broader correction/revocation contracts, and keep public staging read-only. The original scope and acceptance criteria remain below for traceability.

### Scope

1. Inspect existing request-ID patterns used by impact assessments, acceptance-to-DVP assignments, test releases and resources; reuse their conflict semantics where appropriate.
2. Design explicit idempotency contracts for snapshot creation and production batch creation without breaking existing controlled-development clients unnecessarily.
3. Serialize Snapshot number allocation using the owning Release row or an equally explicit PostgreSQL locking strategy.
4. Serialize production batch-limit evaluation and creation using the relevant authorization/deployment rows.
5. Decide and document the retry contract for duplicate business numbers versus a client-generated request ID.
6. Add real PostgreSQL concurrency coverage where SQLite cannot demonstrate row-lock behavior.
7. Update the executable write contracts and all affected API/database/security/status documentation.

### Acceptance criteria

- Identical retried requests return the original result without a second domain record or audit event.
- Reusing an idempotency key with different content returns a conflict.
- Two concurrent Snapshot requests cannot allocate the same number.
- Concurrent batch requests cannot exceed a finite authorization batch limit.
- Domain and audit changes remain atomic on every failure path.
- Existing authorization and authenticated-actor guarantees remain intact.
- The complete backend suite passes; migration head and generated PostgreSQL SQL are validated if the schema changes.
- `PROJECT_STATUS.md`, `ROADMAP.md`, `API.md`, `DATABASE.md`, `SECURITY.md`, `docs/write-contracts.md` and `CHANGELOG.md` are synchronized as applicable.
- Changes are committed and pushed to GitHub `main`; public staging remains read-only and is rechecked after deployment.

## Verification commands

Use Python 3.12, matching `backend/Dockerfile`.

```bash
cd backend
pytest -q
```

If dependencies are not installed locally, use the repository requirement files without changing their pins. For a schema change, also verify the single Alembic head and PostgreSQL SQL generation. Run the frontend production build only when frontend code or its contracts change.

After a push, verify:

```text
GET  https://softwarelifecycle-api-test.onrender.com/health/ready
POST https://softwarelifecycle-api-test.onrender.com/api/v1/deployments
GET  https://softwarelifecycle.whf969.com
```

Expected public state after this package deploys: API `0.18.9`, exact required database revision, POST rejected with `403 read_only_mode`, frontend HTTP 200.

## Working-tree caution

At handoff time, `frontend/app/activity/page 2.tsx` is an unrelated untracked duplicate file. It was not used, edited, committed or deleted by the completed work. Preserve it unless ownership is explicitly resolved.

## Completion and handback protocol

At the end of the cloud development task:

1. Review the final diff and exclude unrelated files.
2. Run proportional tests and record exact results/warnings.
3. Update `PROJECT_STATUS.md` and `CHANGELOG.md`, plus contract documents affected by the change.
4. Commit and push the scoped result.
5. Report development mode (Codex or ChatGPT), changed files, behavior, migrations, tests, commit hash, push/deployment state, evidence-based module percentages with unfinished content, and remaining development steps.

Fast handoff commands remain:

- `规划：<目标>` — decide scope and acceptance criteria.
- `开发：<任务>` — implement, test, document, commit and push.
- `检查：<范围>` — evidence-backed review without implicit mutation.
- `汇总：SoftwareLifeCycle 当前状态` — reconstruct status from repository evidence.
- `继续：下一阶段` — resume the highest-priority ready item.


Request preparation for Snapshot, actual software and Batch is available in code at
`/commands`, with validation, immutable confirmation/copy and expected audit links.
It never submits or saves a request. See [UI scope and remaining work](docs/controlled-write-ui.md).
## Phase 6 first-package verification — 2026-10-01

Starting main: `a5db39eccb0a5a73ea3232f455a9167f1af835a4`. API code is `0.14.0`;
schema remains `0016_authenticated_audit_actors`. Complete backend run: 421 passed,
1384 warnings, no skips; 13 tests use real PostgreSQL 16.15 migrated schemas and
independent sessions. Single Alembic head and PostgreSQL SQL generation passed.
No frontend change/build and no schema migration were needed. Optional-key/no-key,
actor/scope and transaction details are in `docs/write-contracts.md`. Deployment
verification: Render `dep-dauvf1m417fc73fq13dg` is live for commit
`3968f9f007e2a00a7268074e5e66cc1a0a8db2cc`; API health returned 200 / `0.14.0` /
`0016_authenticated_audit_actors`, harmless deployment POST returned
403 `read_only_mode`, and frontend returned HTTP 200 with a rendered Dashboard.
The unrelated duplicate frontend file was absent in this checkout and untouched.

## Phase 6 second package — development report

Development mode: **Codex**. API code is `0.15.0`; schema head remains
`0016_authenticated_audit_actors`, with no migration. Approval Action supports
optional request UUID plus required exact expected step for keyed calls. Release
Decision supports optional request UUID. Shared ApprovalRequest locks serialize
step transitions and decisions, and atomic audit evidence preserves original replay
results. No-key clients and distinct decision-number history stay compatible.

Use the current-progress section of ROADMAP.md for module percentages and unfinished
steps. Request-ID/row-lock coverage is 8/14 (57%); exact scope, actor and atomic audit
coverage is 14/14 (100%). Broad roadmap progress stays 31/44 (70%), not production
readiness. Complete test and deployment evidence is recorded below.

Second-package verification: Python 3.12 full backend run **477 passed, 1646 warnings, no skips**, including **31 real PostgreSQL 16.15 tests**. Single Alembic head `0016_authenticated_audit_actors` and PostgreSQL SQL generation passed. No new migration or frontend change/build. Render deployment `dep-dav00btg1s2s73d4nqo0` is live for `fbb66ae9a2c1833a05ee2032595eb2613d1d3a50` (2026-10-01 06:40:39 UTC). Health returned 200 / API `0.15.0` / database `0016_authenticated_audit_actors`; harmless deployment and Snapshot POSTs returned 403 `read_only_mode`. Frontend returned 200 with Dashboard HTML. No frontend change or separate frontend deployment was needed.

Staging smoke note: the stock 10-second check timed out on `/api/v1/activity` after the first three reads passed. Repeating all four reads and the harmless Snapshot write with a 45-second timeout passed; the separate deployment write also returned 403 `read_only_mode`. No smoke-check timeout or public setting was changed.

## Phase 6 third package — development report

Development mode: **Codex**. Starting GitHub main is
`a131d2f931e240d17b5c9f59d00e43a2061716bf`. API code is `0.16.0`;
schema remains `0016_authenticated_audit_actors`, with no migration.
Delivery, Distribution and Authorization support optional request-ID replay and
atomic rollback. Release Decision also acquires Release before ApprovalRequest,
coordinating latest-decision validation. Current route safety coverage is 11/14
(79%); overall checked roadmap remains 31/44 (70%), with Phase 6 broad items partial.
Next: Deployment/Changeover retry and actual-software concurrency/correction.
Full Python 3.12 suite: **573 passed, 2326 warnings, no skips**, including **63 real PostgreSQL 16.15 tests**. This package adds 64 unit/route cases and 32 PostgreSQL cases. Single Alembic head and PostgreSQL SQL generation passed (850 lines). No frontend code/build was changed. Render deployment `dep-dav0af5g1s2s73d55420` is **live** for feature commit
`42e32e9b0519a2f9f2112cd5b8cae5b92aea73c5` (finished 2026-10-01 15:02:05 Asia/Shanghai).
Post-deploy health returned HTTP 200, API `0.16.0` and database revision
`0016_authenticated_audit_actors`. Release/application, issue-impact and activity
reads returned 200. Harmless Deployment and Snapshot writes returned 403
`read_only_mode`; the three new retry routes also retained that rejection.
Frontend returned HTTP 200 with Dashboard HTML. No frontend code or separate
frontend deployment was required.

Test environment note: the first full run had 63 PostgreSQL connection errors because the disposable local server retained a stale shutdown PID file. The test runtime was restarted with clean shutdown/wait handling; the complete rerun above passed. No application or staging database was altered to resolve this.

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
Python 3.12, including **109 real PostgreSQL 16.15 tests**. Twenty new backend cases
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
