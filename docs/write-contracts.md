# Write contract inventory

This is the reviewed baseline for every non-read FastAPI route. The executable source is `backend/app/write_contracts.py`; `backend/tests/test_write_contracts.py` fails when a write route is added, removed or renamed without updating that inventory.

This inventory is backed by runtime guards. Every current write route has `authentication=OIDC_WHEN_ENABLED`, `authorization=SCOPED_WHEN_OIDC`, `audit=ATOMIC_APPEND` and `actor_binding=AUTHENTICATED_WHEN_OIDC`. When OIDC is enabled, a valid active principal must also hold the exact active role resolved through stored software/project relationships, unless it has the exceptional `PLATFORM_ADMIN` override. The public sample service still keeps `READ_ONLY_MODE=true` because no approved provider is configured and provider-backed acceptance, controlled UI and operations remain unfinished; legacy no-key paths remain weaker.

The enforced scoped roles are recorded in the executable contracts and defined in `SECURITY.md`: snapshot creation uses software-maintainer/project-contributor scope; review actions use reviewer; release decisions use release authority; delivery/distribution use distribution authority; production authorization uses production authority; deployment/changeover/batch use production operator. `PLATFORM_ADMIN` is the only scope-free override.

| Route | Scope | Actor | Audit | Retry | Concurrency | Main gap |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/v1/releases/{release_id}/create-snapshot` | Release | Authenticated | Atomic append | Optional request ID | Release row lock | No-key legacy calls create a new snapshot |
| `POST /api/v1/approvals/{approval_no}/actions` | Approval target/step | Authenticated; declaration retained | Atomic append | Optional request ID + expected step | ApprovalRequest and step row locks | Unkeyed callers act on current step |
| `POST /api/v1/approvals/{approval_no}/release-decision` | Approved release/snapshot | Authenticated; declaration retained | Atomic append | Optional request ID | Release then ApprovalRequest row locks | Distinct decision numbers retain history semantics |
| `POST /api/v1/deliveries` | Release/snapshot/recipient/artifacts | Authenticated; optional declaration retained | Atomic append | Optional request ID | Release then ApprovalRequest row locks | Legacy duplicate number/revision rejection |
| `POST /api/v1/distributions` | Package/recipient | Authenticated | Atomic append | Optional request ID | Package row lock | Legacy duplicate number rejection |
| `POST /api/v1/authorizations` | Distribution/customer/project/site/line | Authenticated | Atomic append | Optional request ID | Release then Package then Distribution row locks | Legacy duplicate number rejection |
| `POST /api/v1/deployments` | Authorization/line | Authenticated | Atomic append | Optional request ID | Authorization then Site then Line row locks | Legacy duplicate number rejection |
| `POST /api/v1/deployments/{deployment_no}/actual` | Deployment/release/snapshot | Authenticated | Atomic append | Optional request ID + required expected version | Deployment lock + version comparison | Legacy no-key writes may overwrite without precondition |
| `POST /api/v1/deployments/{deployment_no}/changeovers` | Deployment/releases | Authenticated | Atomic append | Optional request ID | Deployment row lock | Distinct-number history; no correction/revocation |
| `POST /api/v1/deployments/{deployment_no}/batches` | Deployment/authorization/changeover | Authenticated | Atomic append | Optional request ID | Deployment then shared Authorization row locks | No-key legacy duplicate number returns conflict |
| `POST /api/v1/issues/{issue_no}/impact-assessments` | Issue/release/snapshot | Authenticated; declaration retained | Atomic append | Request ID | Issue row lock | No correction/supersession command |
| `POST /api/v1/changes/{request_no}/acceptance-dvp-links` | SCR/criterion/DVP | Authenticated; declaration retained | Atomic append | Request ID | SCR row lock | No correction/supersession command |
| `POST /api/v1/testing/releases` | Release/snapshot | Authenticated; declaration retained | Atomic append | Request ID | Release row lock | No lifecycle transition commands |
| `POST /api/v1/resources` | Referenced entity | Authenticated; declaration retained | Atomic append | Request ID | Target row lock | Location/access not verified |

## Terms

- **Declared actor** means retained request text. In OIDC mode it never replaces the authenticated actor.
- **Atomic append** means the domain record and audit event share one database transaction.
- **Request ID** means identical retries return the existing result while conflicting reuse is rejected.
- **Row lock** describes the current PostgreSQL serialization target; SQLite tests do not simulate concurrent PostgreSQL sessions.
- **Duplicate rejection** is not idempotency: a retry receives a conflict rather than the original result.

## Review rule

Before a new write route can merge, its contract must state scope, actor source/binding, authentication, authorization, audit, idempotency and concurrency behavior and invoke a runtime authorization guard. Audited routes must resolve a trusted actor. Before any route can be exposed beyond controlled local development, configure an approved OIDC provider, add the required idempotency/concurrency controls and complete provider-backed positive/negative integration tests.

## Phase 6 first package: Snapshot and Production Batch

Both endpoints accept an optional client-generated UUID `request_id`. A supplied ID
is the business row's UUID, following the existing test-release/resource retry
pattern. Its request evidence is stored under `audit_events.payload_json.request`
in the same transaction, with the existing `EVT-SN-{id.hex}` or `EVT-PB-{id.hex}`
event number. No request ledger, schema migration or historical backfill is added.
Keys are global within each of these record types, rather than per URL target.

- Every HTTP call, including a replay, first passes the existing exact-scope guard
  and trusted actor resolution. Replay requires the same audit principal, effective
  name, full display name and retained declaration, including disabled-mode fields.
- Snapshot request content is the exact `release_id`; retry returns the original
  frozen manifest even if source artifacts/version have since changed. A new freeze
  requires a new key. Keys are not derived from content hashes.
- Batch request content is `deployment_no`, `batch_no`, `changeover_id`, `started_at`
  and `note`. Timestamps normalize to UTC (naive timestamps mean UTC); omitted
  timestamps stay null in retry evidence and use a server time only on creation.
  An explicit timestamp differs from omission. Notes and business numbers retain
  their existing exact string semantics.
- Identical replay returns the existing response without another business record,
  audit event or quota consumption. Responses keep the existing HTTP 201 shape
  for compatibility. Different content/actor or legacy rows lacking retry evidence
  produce HTTP 409. A duplicate batch number under another key also produces 409.
- Snapshot locks its owning Release with PostgreSQL `SELECT ... FOR UPDATE` before
  reading the latest number. Batch locks Deployment, then its shared Authorization,
  before counting **all** registered batches and inserting one. Multiple deployments
  sharing one authorization therefore share the same finite quota. A null limit
  stays unlimited; a zero/exhausted limit rejects new work.
- Locked rows refresh earlier ORM identity-map reads. Locks remain held through
  domain writes, audit insertion and commit under PostgreSQL READ COMMITTED.
  Unique UUID/number constraints remain the final conflict guard across targets.
  Validation, insert/constraint, audit and commit failures all roll back and release
  transaction locks. No automatic server-side retry loop is introduced.
- Replay is checked before mutable deployment status/quota validation so an already
  committed request can be recovered after state changes, but never bypasses the
  current HTTP permission check. A fresh request must pass every existing rule.
- Without a key, Snapshot still creates a new freeze and Batch retains duplicate
  business-number rejection. The same row locks and rollback guarantees apply.

Verification: `tests/test_command_retry.py` covers content, actor, legacy, scope and
failure behavior. `tests/test_command_concurrency_postgres.py` uses independent
sessions on uniquely named **migrated** PostgreSQL schemas, verifies actual blocking
with `pg_blocking_pids`, and checks numbering, shared limits, replays, cross-target
conflicts, stale ORM state and rollback. Run it with `TEST_POSTGRES_URL` set to a
throwaway development database that allows schema creation; the fixture drops only
its own schema. Without that variable it is explicitly skipped; SQLite is rejected.

## Phase 6 second package: Approval Action and Release Decision

Both routes accept optional UUID `request_id`, using existing domain IDs and atomic
audit request evidence. A keyed action additionally requires `expected_step_id`;
missing step returns HTTP 422, stale/wrong step returns 409. Unkeyed clients retain
current-step behavior. Canonical action content is approval number, declared actor,
action, comment and expected step; decision content is approval number, decision
number, declared actor, readiness status, decision and notes. Exact strings retain
existing semantics. Keys are global within each record type. Actor/content mismatch
or missing legacy evidence conflicts, and every HTTP replay needs current permission.

- Both lock/refresh the owning ApprovalRequest before retry/validation; actions
  also lock/refresh current and next steps. Locks last through domain/audit commit.
- Same key/content/actor returns the original response without another action,
  decision or audit event. Action after-status comes from the original atomic audit,
  so replay cannot approve the next step or overwrite current workflow state.
- Distinct keyed requests for the same expected step serialize: after the winner
  commits, the loser conflicts. Final action and decision share a lock; decisions
  validate the final committed approval state. Distinct decision numbers retain
  existing append history; duplicate numbers under another key conflict.
- Validation, insert/constraint, audit-after-flush and commit failures fully roll
  back; cross-approval UUID collisions cannot leave a partially advanced step.
- Status/response shapes stay HTTP 200 for action and 201 for decision. No migration,
  historical backfill, automatic server retry, correction or revocation is claimed.

`test_approval_retry.py` covers stable responses, content/actor conflict, expected
steps, no-key compatibility, exact-role denial and transaction failures.
`test_approval_concurrency_postgres.py` uses the migrated-schema independent-session
harness described above, asserts actual blocking and verifies step competition,
final-action/decision ordering, global-key collisions and rollback/lock release.

At the second package, request-ID and row-lock contracts covered 8/14 routes (57%); scope/actor/atomic
audit contracts cover 14/14 (100%). These counts describe reviewed route contracts,
not provider configuration, production readiness or completion of broad Phase 6 items.

## Phase 6 third package: Delivery, Distribution, Production Authorization

Optional UUID `request_id` identifies the existing domain primary key; canonical
request evidence is committed with the domain row/items and audit. Keys are global
within each record type, not per parent. Existing HTTP 201 shapes expose the stored
row (including its current status). There is no frozen response-body ledger.

- Delivery compares release UUID, package number/revision, recipient type/code,
  purpose, declared `created_by` and sorted artifact UUID collection. Reordering
  files is equivalent; duplicates are invalid. Distribution compares exact package
  UUID, distribution number and recipient. Authorization compares release/distribution
  UUIDs, number, customer/project UUIDs, site/line, purpose, limit and restriction note.
- Same key/content/actor reuses the domain row and existing audit; changed fields,
  audit identity or legacy missing evidence conflict. All HTTP retries still require
  current exact permissions. New requests retain every existing business/policy rule.
- Delivery locks/refreshes Release then selected ApprovalRequest; Distribution
  locks/refreshes Package; Authorization locks Release, Package, Distribution.
  Release Decision now locks Release before ApprovalRequest, coordinating latest
  decision checks. No code path acquires Release after ApprovalRequest/Package.
- Replay precedes mutable parent status/latest-decision checks. Fresh commands
  validate committed parent state after locks. All validation, child insert,
  uniqueness, audit-after-flush and commit failures roll back and release locks.
  Independent parents retain unique database constraints as final conflict guards.
- Unkeyed clients retain duplicate rejection (Delivery uses number plus revision).
  No migration/backfill/server retry, correction, revocation, public write UI or
  production certification is added. Future SQL/transition writers must honor locks.

`test_distribution_retry.py` covers content, actor, permission, legacy, policy,
validation/flush/audit/commit rollback and artifact-order semantics.
`test_distribution_concurrency_postgres.py` observes actual blocking for same-parent
and cross-parent races, stale ORM refresh, child/event rollback, lock release, and
new release decisions competing with Delivery/Authorization in both orderings.

At the third package, request-ID/row-lock coverage was **11/14 (79%)**. The remaining routes were
Deployment creation, actual-software reporting and Changeover creation. Scope/actor/
atomic-audit coverage remains 14/14; these counts do not certify an OIDC deployment.

## Phase 6 fourth package: Deployment and Changeover

Optional UUID request_id reuses domain IDs and existing atomic audit request evidence.
Deployment compares number, authorization UUID and line UUID; Changeover compares
deployment/number/source release UUID, UTC-normalized changed_at and exact note.
Naive time means UTC, omitted time differs from explicit time. Keys are global within
each table; matching actor/content returns the existing row (current stored status)
without another domain/event. Conflicting key/legacy evidence/duplicate number returns
409; invalid UUID returns 422. HTTP 201 shapes and unkeyed compatibility are unchanged.
Current scope and trusted actor checks precede every replay.

- Deployment locks/refreshes Authorization -> Site -> Line, validates approved/active
  parents and exact scope, then inserts/audits/commits. Duplicate-number reads do not
  lock an existing Deployment after Authorization; cross-parent unique races roll back.
- Changeover locks/refreshes Deployment. Successful keyed recovery precedes mutable
  source/target validation; new work retains every rule. Distinct numbers remain
  history records, not a newly enforced single-use transition.
- Actual reporting now locks/refreshes Deployment before reading before-state.
  Batch/Changeover use the same first lock, so actual/audit/batch eligibility follow
  committed ordering. Actual remains a mutable overwrite without request-ID/version
  protection, and each successful report still creates a new atomic audit event.
- Validation, constraint, audit-after-flush and commit failures roll back all changes
  and release locks. No migration/backfill/server retry/correction/public writes exist.

`test_production_retry.py` covers retry, fields/actors/legacy, exact active role,
parent validation, UTC semantics and failure rollback. Real independent-session
`test_production_concurrency_postgres.py` verifies actual blocking, independent-parent
UUID/number conflicts, stale parents, rollback/lock release, sequential actual-before
history, actual/Batch ordering and no reversed-lock deadlock.

At the fourth package, request-ID coverage was **13/14 (93%)**; all 14 declare row-lock serialization,
exact scope, trusted actor and atomic audit. Row locking alone does not provide stale
client conflict detection. The subsequent 0.18.0 package below completes actual-software keyed retry/version protection.


## Actual-software retry, version and correction contract (0.18.0)

`POST /api/v1/deployments/{deployment_no}/actual` adds optional UUID `request_id`,
non-negative integer `expected_version` and `correction_reason` (1–2000 characters,
not whitespace-only). A keyed request requires expected_version; invalid JSON fields
return 422. Read the current `actual_version` from deployment detail. HTTP 200 keeps
`deployment_no`/`status` and adds `actual_version`; successful retries return the
original committed status/version, even after a subsequent report changes current state.

The Deployment row is locked and refreshed before evidence/version checks. Identical
key/content/full trusted actor replays the original audit outcome without another
write/event or version increment. Different content/actor/target or legacy evidence
returns 409. Canonical content includes deployment number, release/snapshot UUIDs,
expected version, exact reason and UTC-normalized timestamp. Naive timestamps mean
UTC; omission remains distinct from explicit time and server time is generated once.
The global key namespace for this command uses existing unique audit event numbers
`EVT-DA-{request_id.hex}`; it does not reuse the Deployment ID or add a request table.

Fresh requests compare expected_version under the same lock, then increment exactly
once with the domain/audit transaction. A competing stale request returns 409 with
expected/current versions and no writes. Replacing any existing actual report with a
key requires a correction reason, including migrated rows at baseline version zero.
Corrections append `ACTUAL_CORRECTED` events with reason and full before/after release,
snapshot, status, UTC deployment time and version; the Deployment is the mutable current
projection. Initial reports append ACTUAL_REPORTED. Historical events are never edited.
This is a correction of the reported fact, not rollback of physical flashing, reversal
of existing batches, or a general revocation workflow. Every retry still requires the
current exact active PRODUCTION_OPERATOR grant and matching authenticated actor.

No-key clients keep legacy overwrite behavior, with an optional version precondition;
each successful no-key report increments version and creates an event. They are not
retry-safe without a key and may overwrite without expected_version. Adopt the keyed
contract before multi-user use. Replay is checked before current version/eligibility;
all validation/constraint/audit/commit failures roll back and release locks. Batch and
Changeover continue sharing the Deployment lock. There is no automatic server retry.

Migration `0017_deployment_actual_version` adds non-null Integer actual_version,
server/default zero and a non-negative check. Existing state remains unchanged and
starts at zero; this is a concurrency baseline, not a reconstructed historical count.
No audit history is backfilled. Rollback drops the version column/check and loses
version protection; never roll back a serving writer without coordinating downtime.

`test_actual_retry.py` covers original outcomes, content/actor/legacy conflicts,
versions, correction evidence, UTC input, authorization and failures.
`test_actual_concurrency_postgres.py` applies migrated disposable PostgreSQL schemas,
observes real blocking across sessions, checks stale ORM refresh, competing versions,
global key uniqueness, atomic rollback/lock release and old-state migration preservation.
All 14 routes now declare request-ID, row serialization, exact scope, actor and atomic
audit contracts. Optional legacy paths remain weaker; this is not production readiness.

## Frontend request preparation

Snapshot/actual/Batch /commands forms prepare the reviewed existing command bodies
with a fixed request UUID. Editing invalidates review; confirmation gates export.
The envelope has method/path/body; actual API execution sends only body. Client
checks are syntactic, not permission/business validation. Exact expected audit links
may be unavailable before execution and are not success evidence. No backend route,
submit transport or automatic retry is added; all 14 API contracts remain unchanged.
See [controlled-write-ui.md](controlled-write-ui.md) for scope and pending acceptance.

## Governance request preparation

Approval/Decision forms extend /commands using the same confirmed immutable export. Approval requires an explicit expected_step_id and supported action; exact readiness/decision/actor declarations and comments/notes are retained. Exact business/history and EVT-AP-/EVT-RD- links are expected execution evidence, not success claims. All existing API retry, scope, actor, locking and rollback contracts remain unchanged; no migration is needed.

## Evidence/reference request preparation

Impact/Acceptance-to-DVP/Resource preparation uses the existing required request-ID bodies and text normalization. It requires explicit target UUIDs, judgment/reason, and resource entity/location kinds. Event links use hyphenated EVT-IMPACT-/EVT-AC-/EVT-LK- UUIDs; current bounded history is not proof of this request outcome. Resource locations are never fetched/opened. No command API, permission, actor, transaction, retry or migration behavior changes; full submission/correction remains pending.

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

## Authorization/distribution context reads

API 0.18.2 adds only GET profiles; all 14 executable write contracts are unchanged.
Preparation still uses exact returned UUIDs and requires explicit declarations.
Full history counts do not reserve batch capacity; Batch creation rechecks finite
limits in its existing serialized transaction and atomically commits audit.

## Delivery revision read migration — 2026-10-02

API 0.18.3 adds GET-only exact delivery profile and artifact paging. Distribution preparation keeps the exact package UUID; no recipient/policy permission is inferred from the count or displayed page. Existing Delivery/Distribution authorization, actor, retry, row-lock and atomic-audit contracts remain unchanged. No new write or migration is added.

## Bilingual presentation — 2026-10-02

All 14 forms translate labels, choices and validation display only. Original option
values, request_id, exact scope, actor binding, confirmation and frozen request JSON
remain unchanged. Language switching neither remounts forms nor sends commands.
All executable API contracts/locks and atomic audits remain unchanged; no migration.
Language preference is the only new browser cookie; no request or credential persistence.
See [interface contract](i18n.md).

## ASR read-consumer migration — API 0.18.4 (2026-10-02)

No command route or request-ID contract changed. The new downstream summary and
production authorization_release_id filter expose stored-parent read observations;
they are not authorization checks, reserved batch quota or a consistent write receipt.
The ASR page keeps its exact release Snapshot preparation UUID and immutable export
semantics. Snapshot numbering and Batch finite-limit row locks, authenticated actor
binding, exact scope and business/audit atomicity remain covered by the full backend
suite (750 passed including 104 real PostgreSQL tests). No migration, no submission
flow and no public write enablement; remaining correction/revocation and result flows
are still pending.

## Pinned evidence consumer — API 0.18.5 / schema 0018

No write route/request-ID/scope/actor/audit/serialization contract changes. ASR Snapshot
preparation still uses the exact release UUID. Pinned evidence and latest DVP results
are read observations, not approval or write receipts. Migration 0018 adds only an index,
without rewriting records. Full backend 770 tests including 105 real PostgreSQL tests
passed; existing Snapshot/Batch/replay/quota/rollback/security regressions remain passing.
No submission or public write enablement; correction/revocation/result flows remain pending.

## Coverage read aggregation — API 0.18.6 / schema 0018

No request-ID/payload/scope/actor/transaction/lock contract changes. Snapshot numbering
and Batch finite authorization quotas still serialize on their existing PostgreSQL
locks. Coverage is now a SQL aggregate observation of exact release/Snapshot required
DVPs, retaining any-PASS and execution-presence semantics; it is not a command receipt
or reserved quota. One aggregate statement does not make other profile metadata a
transactionally consistent receipt. No migration or public submission; authenticated
submission/recovery/results and broader append-only corrections remain pending.

## SSR summary/collection migration — API 0.18.7 / schema 0018

No write route/request-ID/payload/scope/actor/lock/atomic-audit contract changed. SSR
Snapshot preparation retains the exact Release UUID. Paginated declaration/baseline
observations are not frozen evidence, approvals, permission, reserved quota or write
receipts. Summary and pages are separate reads and may change during concurrent writes.
All existing concurrency/replay/quota/rollback/authorization tests pass in the complete
real PostgreSQL run. No migration or public submission; remaining authenticated
submission/recovery/results and broader append-only correction flows stay pending.

## ASR component consumer migration — API 0.18.8 / schema 0018

Summary/declaration/unlinked-base GET projections replace the frontend legacy bulk
read. Exact stored links and global anti-association scope are preserved; a different
baseline context is rejected by the page. These observations do not authorize a command
or constitute a snapshot/approval receipt. No changes to any of the 14 request-ID,
conflict/replay, exact grant, trusted actor, lock, correction or atomic audit contracts.
No migration, submission route/UI or public write enablement is introduced. Existing
PostgreSQL concurrency and rollback tests remain required regressions.

## ASR frozen policy read migration — API 0.18.9 / schema 0018

Exact snapshot-pinned summary/artifact/rule GETs replace the ASR policy bulk consumer.
Recording indicators and stored recipient decisions are not command grants, approval
or validated hashes; internal-only external denial is preserved. Selected artifact must
belong to the pinned Snapshot. No changes to any of the 14 request-ID replay/conflict,
role/actor, transaction lock, correction or atomic audit contracts. No migration or
submission capability/public write target is introduced; concurrency and rollback
regressions continue running against real PostgreSQL.

## Exact Snapshot detail read migration — API 0.18.10 / schema 0018

Only read consumers and shared frozen SQL projections change. Summary/file/rule pages
bind exact number/UUID and artifact ownership. Search and immutable request-preparation
links retain target UUIDs; no write or submission capability is added. All 14 command
request-ID/conflict/scope/actor/audit/transaction-lock contracts remain unchanged and
are exercised in the complete real PostgreSQL test run. No migration, staging stays
read-only. Legacy comparison/bare manifest APIs remain; consumer migration is not yet
complete. See read-consumer-migration.md for the 12/17 scope-group breakdown, separate
from unchanged ROADMAP 34/44 acceptance-item accounting.

## Snapshot comparison consumer — API 0.18.11 / schema 0018

This package adds only exact summary/difference GETs and read-only rule-inspection
links. Pair names/UUIDs, same release, duplicate identity checks and bounded SQL policy
comparison never approve a Snapshot or grant distribution/write capability. All 14
request-ID/conflict/exact-scope/trusted-actor/transaction-lock/atomic-audit contracts
remain unchanged, and complete PostgreSQL regressions pass. No migration/submission/
public write enablement. The compatibility comparison still exists; the migrated UI
uses no bulk fallback. Read-consumer scope groups advance 12/17 to 13/17; broad
ROADMAP item remains incomplete at 34/44.

## ASR passport bounded consumer — 2026-10-03

This package adds read-only passport endpoints and changes no command contract.
Snapshot number allocation, quota locks, request-ID replay/conflict, exact scoped
permission checks, authenticated actor binding and business/audit atomicity remain as
specified above. Full real PostgreSQL backend regression must include the existing
concurrent Snapshot/Batch cases. Read pins are observation selection, not write
preconditions or authorization grants; public staging remains read-only.

## Bounded readiness and policy aggregation — 2026-10-03

This read migration does not change write requests, declared readiness fields,
permission scope, authenticated actor binding or commit boundaries. Snapshot allocation,
Batch quota locks, request-ID replay/conflict and business/audit atomicity remain covered
by the full real PostgreSQL regression suite. SQL policy summary records completeness,
not authorization; recipient evaluate and frozen delivery validators are unchanged.
Readiness eligibility is neither a write grant nor a cross-request concurrency token.
No authenticated UI submission, provider configuration or staging writes are enabled.

## Release catalog consumer migration — API 0.18.14

API 0.18.14 adds read routes only. All 14 command contracts, scope/actor binding, keyed retry, row serialization and atomic audit behavior remain unchanged. Catalog or resolver outcomes do not authorize submission; public staging retains read_only_mode.

## SCR/Issue directory migration — API 0.18.15

API 0.18.15 adds only SCR/Issue directory reads. All 14 existing command contracts are unchanged. Catalog status markers and counts confer no approval, scope grant or submission outcome.

## SCR detail read migration — API 0.18.16

Only read endpoints/consumers change. All 14 command contracts, scoped actor binding,
keyed replay, row serialization and atomic business/audit behavior remain. SCR/child
identity pins are not write preconditions or grants. Public writes remain denied.

## SCR coverage read migration — API 0.18.17

All 14 command contracts, exact actor/scope binding, keyed replay, row serialization
and business/audit atomicity are unchanged. Criterion preparation links still target
exact SCR/criterion UUID; new read context pins are neither submission preconditions
nor permission grants. Coverage retains exclusion and latest-execution semantics;
public writes remain denied.

## Issue detail/impact read migration — API 0.18.18

All 14 commands retain actor/scope binding, keyed replay, row serialization and
atomic business/audit behavior. Exact impact-preparation links remain pinned to Issue,
release and frozen Snapshot; new read pins grant no submission permission. Current
judgments and verification results are separate evidence. Public writes remain denied.
