# SoftwareLifeCycle Development Handoff

## Handoff identity

- Date: 2026-10-01 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Verified baseline: `961994af31da607a5b36066ee7998eb3c4ea60bc`
- Baseline subject: `feat: prepare reviewed approval and release decision requests`
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
| API | FastAPI + SQLAlchemy services | Render API version `0.18.0`, health verified ready |
| Database | PostgreSQL 16 + Alembic | Required/verified revision `0017_deployment_actual_version` |
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
- 55 backend test modules; the latest full run passed all 688 tests under Python 3.12, including 103 real PostgreSQL tests without skips.
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

The first Phase 6 package below is implemented for Snapshot and Production Batch. The fifth package completes actual-software keyed retry/version/correction; next extend **Delivery/Distribution/Authorization request preparation**, then approved identity/submission and broader correction/revocation contracts, and keep public staging read-only. The original scope and acceptance criteria remain below for traceability.

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

Expected public state after this package deploys: API `0.18.0`, exact required database revision, POST rejected with `403 read_only_mode`, frontend HTTP 200.

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

Frontend tests: 111 passed, no skips (55 added evidence/reference cases). Next.js production build within OpenNext and Cloudflare Worker bundling passed; existing build/deprecation warnings remain. Complete Python 3.12 backend suite: 688 passed, 3179 warnings, no skips, including 103 real PostgreSQL 16.15 tests in a new isolated /tmp cluster. Six local SSR cases passed: impact/assignment/resource context, invalid entity type, oversized release UUID, ignored location prefill and Create entry. No migration or backend code change. Online verification follows the scoped push.
