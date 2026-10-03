# Architecture

## System context

```text
User / reviewer
      |
      v
Next.js 15 + React 19
Cloudflare Worker (OpenNext) or local web container
      |
      | server-side HTTP, API_BASE_URL
      v
FastAPI 0.18.9
OIDC identity + scoped write authorization + read-only guard
      |
      | SQLAlchemy 2 + Alembic
      v
PostgreSQL 16
formal lifecycle records + append-only history
```

GitHub `main` is the engineering source of truth. Cloudflare and Render are deployment targets; their live state must be checked independently of repository configuration.

## Repository boundaries

| Area | Responsibility |
| --- | --- |
| `frontend/app` | Next.js App Router pages and server-side API reads |
| `frontend/lib`, `frontend/components` | API clients, shared types and catalog presentation |
| `backend/app/api` | HTTP contracts, request validation and response shaping |
| `backend/app/services` | Domain rules, state transitions, readiness/trace calculations and audit coordination |
| `backend/app/models` | SQLAlchemy persistence model |
| `backend/alembic` | Ordered PostgreSQL schema history |
| `backend/tests` | Domain, API-query and transaction behavior checks |
| `docs` | Deployment/operator notes supplementary to the root project documents |

## Core lifecycle

```text
Organization / software
        |
        v
SCR -- criteria/change points/issues -- DVP plan/items/executions
        |                                  |
        +---------------> Release <--------+
                              |
                       frozen Snapshot
                              |
                    readiness + approval
                              |
                       Release Decision
                              |
               Delivery revision -> Distribution
                              |
                  Production Authorization
                              |
             Deployment -> Changeover -> Batch
```

All readiness, impact and downstream claims should be scoped to exact UUIDs and, where relevant, the exact frozen snapshot. Matching names or versions are navigation aids, not proof.

## Important design rules

### Frozen evidence

A release snapshot freezes artifact metadata and recipient rules. Later source-record changes must not silently rewrite the historical snapshot. Snapshot comparison is metadata/manifest comparison, not binary content inspection.

### Append-only formal history

PostgreSQL rejects update/delete operations for audit events, issue impact assessments, acceptance-to-DVP links and resource links. Corrections are new records. Every current command service creates its domain change and audit event in one transaction so both commit or both roll back.

### Read models versus command paths

Most UI pages use read-only catalog/profile endpoints. Newer catalogs are bounded, filterable and return totals independently of the current page. Existing command APIs remain available for controlled/local use, but the public test service is guarded by `READ_ONLY_MODE=true`.

### Trust boundary

The database has provider-neutral user/service principals and scoped grants; configurable OIDC mode validates write-request identity and enforces exact active project/software roles on all current write routes. Scope is derived through stored release, SCR, distribution, authorization and deployment relationships. Every current command binds its audit actor to the authenticated principal and preserves any request declaration separately. CORS is browser policy, not authorization. Until an approved provider is configured and retry/concurrency controls pass their acceptance gates, public deployment must contain sample data only and remain read-only.

### Failure behavior

Frontend data pages prefer explicit unavailable/empty states over fabricated fallback lifecycle records. `/health/live` reports process liveness; `/health/ready` additionally verifies database connectivity and the exact required Alembic revision.

## Runtime configurations

- CI: GitHub Actions uses disposable hosted runners, Python 3.12/PostgreSQL 16 and Node 22. Backend tests and isolated migration round trips run alongside frontend tests/Next.js/OpenNext builds; no deployment credentials or public data are used. See `docs/ci.md`.
- Local: Docker Compose runs PostgreSQL, FastAPI and Next.js; API startup migrates and optionally seeds.
- Public demo: Cloudflare Worker serves the frontend and calls the Render FastAPI service; Render uses managed PostgreSQL and should set `READ_ONLY_MODE=true`.
- Future company environment: requires a fresh database, `SEED_ON_STARTUP=false`, authentication/authorization and an approved frontend-to-API network path.

## Change discipline

- API contract changes update `API.md` and tests.
- Schema/model changes require an ordered Alembic migration and an update to `DATABASE.md`.
- New state transitions define authorization, idempotency, concurrency and audit behavior before public exposure.
- Deployment claims are verified with health/smoke checks and recorded in `PROJECT_STATUS.md`; configuration alone is not proof of a successful deployment.

## First Phase 6 command-safety slice

Snapshot and Production Batch accept optional request UUIDs without changing the
schema: the UUID identifies the business row and the atomic audit payload stores
its request evidence. Snapshot locks Release before retry/number lookup; Batch
locks Deployment then shared Authorization before retry/quota evaluation. Both
refresh previously loaded ORM rows and retain locks through commit under PostgreSQL
READ COMMITTED. Errors roll back the complete command. No-key clients keep legacy
behavior, while exact authorized replays create neither a record nor an audit event.
Other command transitions still need their own concurrency/idempotency controls.

## Approval command serialization

Approval actions and release decisions share the ApprovalRequest row as their
PostgreSQL transaction lock. Actions also refresh/lock current and next step rows.
Keyed actions require the exact expected step, so competing requests cannot silently
advance two steps. The action UUID plus atomic audit request evidence supports
replay; a frozen response value reads original after-status without changing a
cached workflow object. Decisions use the same UUID/audit mechanism and retain
existing distinct-number history semantics. Constraint, audit and commit failures
roll back the entire command. Current HTTP scope and actor resolution precede replay.

## Distribution chain serialization (0.16.0)

Delivery, Distribution and Production Authorization reuse domain UUIDs and atomic
audit request evidence for optional-key replay. Their command wrappers roll back
validation and domain-child insertion failures as well as audit/commit failures.
Delivery locks Release then ApprovalRequest; Distribution locks exact Package;
Authorization locks Release, Package, Distribution. Release Decision now locks
Release before ApprovalRequest, so new decisions serialize with latest-decision
validation in Delivery/Authorization. Approval Action retains ApprovalRequest/step
locks and never acquires Release afterward. No cyclic reverse acquisition is added.

The tested contract covers supported command paths under READ COMMITTED; arbitrary
SQL edits or future transition routes must implement their own consistent lock order.
Legacy/no-key calls keep duplicate rejection; no full production-readiness claim follows.

## Production command serialization (0.17.0)

Deployment creation uses optional domain UUID/audit request evidence and locks
Authorization, Site, Line in order. Its duplicate-number check is an unlocked read;
it never acquires an existing Deployment after Authorization, avoiding the reverse
of Batch's Deployment -> Authorization order. Unique constraints remain the final
guard for independent-parent UUID/number races.

Changeover creation uses optional UUID/audit evidence and locks Deployment through
commit. Actual reporting now locks/refreshes that same Deployment; Batch already
locks Deployment then Authorization. Actual-before audit values and batch eligibility
therefore follow committed state. That 0.17.0 slice provided row serialization. The 0.18.0 slice below adds actual-report
retry/version protection and audited corrections, using migration 0017.


## Actual report projection and immutable command outcome (0.18.0)

Deployment remains the current actual-software projection. Migration 0017 adds its
non-negative actual_version; zero is a migration baseline without historical inference.
A report locks/refreshes Deployment, checks optional expected_version, increments
version and commits the projection with an append-only audit event. Keyed reports
require the version; replacements also require a correction reason. Batch/Changeover
continue using the same Deployment-first lock.

Existing unique audit event numbers identify actual request UUIDs globally, because
multiple reports cannot reuse the single Deployment primary key. Audit JSONB stores
canonical request, full actor evidence and before/after software/status/time/version.
A frozen service result reads the original after-state on retry, instead of mutating
a cached Deployment or returning its later state. Cross-target key collisions roll
back the losing projection/event. Legacy no-key reports remain weaker. The full
contract and limits are in [docs/write-contracts.md](docs/write-contracts.md).

## Request-preparation frontend

The /commands server page selects bounded initial form context; a client component
uses a transport-free pure helper to validate and freeze a request. Field/target
changes invalidate review; confirmation enables clipboard export with a stable key.
Business requests use only React memory. No token, API-origin input, business-request browser storage, mutation
route or POST transport is introduced. Backend security/atomicity remains authoritative
for later controlled-client execution. See docs/controlled-write-ui.md.

## Governance request preparation

Approval/Decision preparation extends the same pure-helper boundary. Existing governance detail supplies visible step UUIDs for bounded initial context; changing step context remounts the form. The backend remains authoritative for current-step, approved-snapshot binding, trusted actor and atomic audit.

## Evidence/reference request preparation

The same transport-free helper now covers eight preparation forms. Bounded issue/release/snapshot and SCR/criterion context comes from read pages. Context changes remount the workbench. Resource locations stay inert text; no external fetch or filesystem service is introduced. Existing API services remain the business/authorization/atomicity authority.

## Distribution-chain request preparation

Delivery/Distribution/Authorization forms prepare existing keyed bodies with explicit
revision/artifact UUIDs, exact recipients/purpose and customer/project/site/line scope.
Finite limits and unlimited null require explicit choices; no default quota is inferred.
The backend still selects/validates the approved snapshot and policies under its current
locks; authorization creation stays DRAFT. Distribution creation does not send files or
acknowledge receipt. Existing exact roles, trusted actor binding, retry and atomic audit
remain unchanged. EVT-DP-/EVT-DS-/EVT-PA- links use UUID hex. No API/schema/migration,
transport, login or public-write setting changes; API 0.18.0/head 0017 remain. See
`docs/controlled-write-ui.md` for preparation subsets and remaining submission work.

## Final three request-preparation forms

Test Release, Deployment and Changeover complete 14/14 preparation forms using
existing request bodies, immutable confirmation/copy and exact UUID context.
Test Release remains DRAFT; Deployment remains PENDING; Changeover appends history
without physical flashing or actual-software updates. EVT-TR- retains hyphenated
UUIDs; EVT-DPLOY-/EVT-CO- use UUID hex. No backend/API/schema/migration, role/actor,
retry/transaction, authentication or public-write settings change. Submission and
outcome recovery remain pending. See docs/controlled-write-ui.md for limits.

## Deployment profile read migration — 2026-10-02

The frontend deployment detail now reads the exact `/deployments/{deployment_no}/profile`
(API 0.18.1), which omits unbounded batch/changeover/decision arrays. Existing indexed
`deployment_id` count queries supply full history totals; linked bounded catalogs
review exact deployment history and exact delivered release/snapshot decisions.
Stored status and software-pair observation remain separate; missing context stays
null. Counts are observations, not quotas, authorization or a consistent write receipt.
No migration is needed: existing child foreign-key indexes serve count scope.
Legacy endpoints retain their old shapes. All 14 write contracts, exact scope,
trusted actors, replay/locks and atomic audit are unchanged; public staging remains
read-only and provider-backed submission/other consumer migrations remain pending.

## Authorization/distribution read migration — 2026-10-02

These two frontend details use exact profiles (API 0.18.2) with direct parent
references and COUNT queries instead of loading child histories. Child reviews
open existing paginated catalogs with exact authorization/distribution UUIDs.
Legacy detail responses remain compatible; other consumer migrations remain open.

## Delivery revision read migration — 2026-10-02

The delivery revision frontend uses an exact profile and a paginated artifact endpoint (API 0.18.3). Aggregate counts omit child histories; manifest metadata is joined only for the bounded window, retaining missing references through an outer join. Distribution review uses the exact package UUID catalog. Legacy consumers remain compatible; all write/security boundaries are unchanged.

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

## ASR downstream consumer — API 0.18.4

The ASR page replaces its legacy downstream-list request with a fixed count summary
and six exact-release history links. Production links use authorization_release_id
to retain the stored parent chain when planned/actual/batch releases differ; other
three links use the existing release_id scope. Catalog paging/filter/kind navigation
retain the new UUID scope. Separate release observations compare UUIDs only.
Missing/wrong-ID summaries remain unknown without legacy fallback. Shared localization
covers the new view in both languages, default Chinese; identifiers and request exports
stay unchanged. ASR profile/evidence and other legacy consumers still need migration.

## Pinned ASR evidence consumer — API 0.18.5

The ASR overview reads a fixed summary, then two bounded projections using the selected
Snapshot UUID. Independent pagination preserves the selected UUID, common limit and
other table offset; a newer Snapshot cannot move the selection. Shared localization
covers new content in both languages; IDs/hashes/original evidence remain unchanged.
A historical pin and possible newer overview are explicitly shown. Window ranking
selects latest DVP evidence per item UUID, with missing metadata retained. No private
storage/body fields or unbounded policy arrays are loaded. Legacy evidence stays compatible;
ASR coverage service and other legacy consumers still need migration. READ COMMITTED
and offset semantics do not promise consistent results across concurrent DVP additions.

## Coverage aggregation — API 0.18.6

TraceabilityService uses reusable relational CTEs for software/project SCR scope,
change points, linked distinct issues, association links and a UNION of required DVP
UUIDs. One SELECT returns all coverage counters; its exact-release/snapshot execution
aggregate counts distinct items and any-PASS items. Snapshot selection uses LIMIT 1.
No growing Python ID lists or child ORM rows/private text are loaded. Existing profile,
passport and readiness consumers retain their response contracts and Python rounding.
The aggregate statement is coherent within its database statement, but parent selection
and other profile reads remain separate READ COMMITTED observations. This does not bound
other component/policy/history reads or certify readiness. No migration or frontend change.

## SSR summary and collection consumer — API 0.18.7

standard_release_views.py keeps legacy profile compatibility while projecting exact SSR
components with a left definition join and applications through stored baseline UUIDs.
A parent summary returns metadata and SQL full counts; collection queries use LIMIT/
OFFSET, deterministic UUID tie breakers and fixed projections. Missing definitions stay
visible; missing referenced releases remain excluded. StandardReleaseCollections reads
both pages independently, preserves the other offset and rejects wrong-parent replies.
Missing/foreign summaries stop child reads; no compatibility fallback. Default Chinese/
English covers new states. Parent release notes remain potentially large; no global byte
bound is claimed. READ COMMITTED/count sorting and offsets do not produce consistent
receipts. No command or schema change; other compatibility consumers still remain.

## ASR component consumer — API 0.18.8

The component page requests an exact parent summary then two bounded SQL projection
pages. Baseline validity is a UUID/definition join; unlinked membership is an exact-ASR
correlated NOT EXISTS over all declarations. No growing in-memory ID set or child ORM
collection is materialized. SQL totals and stable UUID pages bound response size, not
DB scan cost. Client release/baseline context checks detect mismatches across reads;
no transactional read receipt or snapshot pinning is added. Legacy read API remains
compatible; business write services, locks and audit transactions are unchanged.

## ASR frozen policy consumer — API 0.18.9

Summary resolves exact ASR/latest-or-selected Snapshot and computes recording indicators
with SQL CASE/EXISTS aggregates. Bounded artifact projections include scalar rule_count;
separate bounded rules join exact snapshot/artifact scope and carry public filename/
distribution context. No nested rule arrays, growing Python ID lists or child ORM loads.
The page pins all navigation to the summary snapshot and independently pages artifacts/
rules; exact artifact drilldown resets only rule offset. Mismatched summary/child/filter
contexts fail closed for presentation. Fixed query shape bounds transfer, not SQL scans.
Legacy bulk routes remain compatible; no command, lock, identity or audit change.

## Exact Snapshot detail consumer — API 0.18.10

Exact Snapshot number summary resolves parent identity without materializing children.
Shared frozen_policy_reads SQL projections provide bounded public metadata and separate
rules. Both page queries require the summary Snapshot UUID, optionally validate and
filter an exact artifact, and return all parent/filter context. The server-rendered
manifest tables page independently, retain full SHA and raw identities and fail each
mismatched child independently. Search links select the exact file before anchoring.
Legacy bare detail/comparison remain compatible; comparison still loads full manifests.
No command/lock/audit architecture change or cross-read transaction guarantee.

## Snapshot comparison consumer — API 0.18.11

Comparison now resolves exact source summary and bounded history suggestions, then
requests SQL pair summary and one bounded difference page. Counted rule tuples and
bidirectional EXCEPT compare recipient/purpose/code/decision with duplicates, independent
of record UUID or insertion order. SQL duplicate validation, frozen-key UNION/joins,
NULL-safe field comparisons and CASE classify every file before SQL filtering/paging.
No complete Python manifest or inline rule collection is loaded. Side rule counts link
to exact bounded detail. Navigation pins both names/UUIDs and returned parent/filter
contexts fail closed. Legacy compatibility comparison remains; fixed query shape does
not guarantee fixed DB runtime or a transactional read receipt. Command architecture
and audit/actor/locking remain unchanged.

## ASR passport bounded consumer — 2026-10-03

`app/api/asr_passport.py` separates fixed identity/decision summary and SQL counts
from four independently bounded histories. First summary selects latest; explicit
paired Snapshot/decision UUIDs (or `none`) persist across navigation. Summary recomputes
current Snapshot/latest decision indicators without changing pinned selections. The
passport frontend consumes only these five endpoints; compatibility APIs remain for
other callers. Typed page envelopes are checked for release and both selection pins.
Historical selection, full counts/full hashes, failed individual pages and latest
refresh links are explicit in Chinese-default/English UI. No write-service changes.

## Bounded readiness and policy aggregation — 2026-10-03

`asr_readiness.py` exposes fixed current summary and bounded approved-exception
projections. The existing dashboard gate builder shares all eight rule calculations;
a bounded option replaces the exception collection with count/presence. Compatibility
callers retain complete exception arrays. Shared ArtifactPolicyService summary now uses
SQL CASE/EXISTS aggregates while public fields and percentage semantics stay unchanged.
The frontend reads current summary first, checks exact release/Snapshot identity, pins
exception navigation and rejects stale current selections. Artifact checks remain based
on live release declarations; DVP/exception checks remain tied to the observed current
Snapshot. New reads do not create permissions, stored readiness receipts or write flows.
