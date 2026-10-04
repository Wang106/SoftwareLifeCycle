# Database

## Current baseline

- Engine: PostgreSQL 16 in the local Compose environment; current Render inventory reports PostgreSQL 18. The local real-concurrency regression uses 16.15.
- ORM: SQLAlchemy 2.
- Migration tool: Alembic.
- Required schema revision: `0018_asr_evidence_index`.
- Local demo startup: migrations, optional idempotent Seed, then API.
- Production/company rule: use a fresh database and `SEED_ON_STARTUP=false`.

SQLite is used by isolated tests where supported, but it does not validate PostgreSQL JSONB, database triggers or row-lock concurrency. PostgreSQL is required for schema and append-only-rule verification.

## Table groups

| Domain | Main tables |
| --- | --- |
| Organization/software | `suppliers`, `customers`, `projects`, `software_products` |
| Release definition | `releases`, `standard_release_details`, `application_release_details`, `component_definitions`, `release_components`, `artifacts` |
| Change/issue | `software_change_requests`, `acceptance_criteria`, `change_points`, `issues`, `issue_change_request_relations` |
| Verification | `dvp_plans`, `dvp_items`, `change_point_dvp_items`, `issue_dvp_items`, `test_releases`, `dvp_executions`, `acceptance_dvp_links` |
| Frozen evidence/policy | `release_snapshots`, `snapshot_artifacts`, `artifact_distribution_rules`, `snapshot_artifact_distribution_rules`, `policy_exceptions`, `issue_impact_assessments`, `resource_links` |
| Governance | `approval_requests`, `approval_steps`, `approval_actions`, `release_decisions`, `audit_events` |
| Distribution | `delivery_packages`, `delivery_package_items`, `distributions`, `software_authorizations` |
| Production | `manufacturing_sites`, `production_lines`, `deployments`, `software_changeovers`, `production_batches` |
| Identity/authorization foundation | `security_principals`, `global_role_assignments`, `software_memberships`, `project_memberships` |

## Key relationship path

```text
Supplier -> SoftwareProduct -> Release
Customer -> Project -> ApplicationReleaseDetail -> Release
Release -> ReleaseComponent -> Artifact
Release -> ReleaseSnapshot -> SnapshotArtifact

SoftwareChangeRequest -> AcceptanceCriterion / ChangePoint
SoftwareChangeRequest <-> Issue
SoftwareChangeRequest -> DvpPlan -> DvpItem -> DvpExecution
Release + Snapshot -> TestRelease / DvpExecution / ImpactAssessment

Release + Snapshot -> ApprovalRequest -> ReleaseDecision
Release + Snapshot -> DeliveryPackage -> Distribution -> SoftwareAuthorization
SoftwareAuthorization -> Deployment -> SoftwareChangeover / ProductionBatch
```

Foreign keys and stored UUIDs are the trace authority. Display numbers, versions and names help navigation but must not be used to infer a formal relationship.

## Frozen and append-only records

- `release_snapshots` and `snapshot_artifacts` hold frozen release metadata/artifact evidence.
- `snapshot_artifact_distribution_rules` preserve recipient decisions at freeze time.
- `audit_events`, `issue_impact_assessments`, `acceptance_dvp_links` and `resource_links` have PostgreSQL triggers rejecting UPDATE and DELETE.
- Corrections to append-only facts are represented by new records. Do not add application code that mutates these tables.

## Migration history

| Revision | Capability |
| --- | --- |
| `0001`–`0003` | Core releases/snapshots, change/testing and policy exceptions |
| `0004`–`0005` | Artifact distribution rules and frozen snapshot policies |
| `0006` | Approval and release decisions |
| `0007`–`0008` | Delivery/distribution/authorization and distribution binding |
| `0009` | Production traceability |
| `0010` | Append-only audit events |
| `0011` | Optional constrained customer region |
| `0012` | Append-only issue impact assessments |
| `0013` | Append-only acceptance-to-DVP links |
| `0014` | Append-only external resource links |
| `0015` | Provider-neutral user/service principals and scoped role grants |
| `0016` | Authenticated principal/display binding and preserved declarations on audit events |
| `0017` | Non-negative actual-report version on Deployment; preserved legacy state at baseline zero |

Revision `0015` stores only external identity references and grants. It deliberately contains no password, token or client-secret columns, and no Seed identities or grants are created. Revision `0016` adds nullable actor identity columns so historical/seed audit events remain unchanged while new OIDC-mode events can reference the exact local principal and preserve the request's declared name separately.

API version `0.13.0` adds audit events for snapshot and production commands without changing the schema; that round used revision `0016_authenticated_audit_actors`; the current head is 0017.

Never edit an applied migration to change history. Add a new ordered revision, import its model metadata in Alembic as required, and update `required_db_revision` in `backend/app/core/config.py` together with deployment documentation and readiness tests.

## Data handling rules

- The public environment is sample/test only; never load company or customer-sensitive data there.
- `DATABASE_URL` belongs only in the API environment, not frontend public variables or Git.
- Demo Seed is idempotent for named sample records but is not a production provisioning process.
- Backup, restore, retention and disaster-recovery procedures are not yet defined and are roadmap items.
- Before a company deployment, configure the approved OIDC provider and grants, review classifications/access rules, add required idempotency/concurrency controls, disable Seed and validate the complete migration chain on a fresh PostgreSQL database.

## Phase 6 retry storage and transaction locks (API 0.14.0)

No new migration is needed: Snapshot and Production Batch use their existing UUID
primary keys for optional `request_id`, and their existing atomic audit JSONB payload
stores canonical request evidence. Historical rows are untouched and cannot be
claimed as idempotent results without matching evidence. The schema remains at
`0016_authenticated_audit_actors`, including the unique `(release_id, snapshot_number)`,
`snapshot_no`, `batch_no` and audit event-number constraints.

Snapshot acquires `FOR UPDATE` on Release before retry/number lookup. Batch acquires
`FOR UPDATE` on Deployment, then SoftwareAuthorization before retry/quota lookup.
The shared authorization serializes batches from every deployment consuming its
quota, and count includes every registered batch regardless of status. Locked ORM
objects use `populate_existing=True`; locks last until the business/audit transaction
commits or rolls back. The validated isolation level is PostgreSQL READ COMMITTED.
Database uniqueness conflicts are rolled back and mapped to HTTP 409.

Real concurrency tests create a unique schema, apply the entire Alembic chain,
observe database blocking across separate sessions, and drop that test schema.
Set `TEST_POSTGRES_URL` only to an isolated development database permitting schema
creation. An unset variable explicitly skips this suite; SQLite cannot stand in.

## Approval retry storage and locks (API 0.15.0)

No migration: `approval_actions.id` and `release_decisions.id` hold optional request
UUIDs, globally unique within each table. Canonical request content is recorded in
existing audit JSONB, without historical backfill. `EVT-AP-{id.hex}` identifies an
action's audit event whose entity remains its ApprovalRequest; `EVT-RD-{id.hex}`
identifies the decision audit event whose entity is the decision. Existing unique
UUID, decision-number and event-number constraints remain final conflict guards.

Both services lock/refresh ApprovalRequest before replay or mutable validation;
actions additionally lock/refresh the current and next ApprovalStep. Locks last
through atomic domain/audit commit under READ COMMITTED. Keyed actions use the
exact expected step UUID, not the current step discovered after a competing commit.
Cross-approval UUID races roll back the losing transaction. No-key compatibility
is retained; distinct decision numbers remain allowed for an approved request.
Real PostgreSQL tests verify actual blocking, final-action/decision ordering,
refresh of cached state, global-key collisions and full rollback/lock release.

## Distribution retry storage and locks (API 0.16.0)

No migration: optional request UUIDs use existing `delivery_packages.id`,
`distributions.id` and `software_authorizations.id`. Canonical request evidence is
stored in the same atomic audit JSONB under `request`, using existing `EVT-DP-`,
`EVT-DS-`, `EVT-PA-` event numbers. UUID keys are global within each domain table;
legacy rows are not backfilled. Existing unique package-number/revision, distribution
number, authorization number, item and audit constraints are retained.

Release Decision now uses Release -> ApprovalRequest locks. Delivery uses the same
order; Distribution locks Package; Authorization uses Release -> Package -> Distribution,
with explicit `FOR UPDATE OF delivery_packages` on its parent join. Earlier identity-map
reads refresh before validation. All locks span domain, child items, audit and commit.
The latest-decision lookup is deterministic by descending decided time then UUID;
Release serialization ensures supported new decisions commit before dependent checks.
Cross-parent global-key/business-number conflicts roll back all domain/items/audit.
Real PostgreSQL tests apply the full migration chain in disposable schemas and observe
blocking, both ordering directions, stale-state refresh and lock release after failure.

## Deployment / Changeover locks and retry storage (API 0.17.0)

No migration: existing `deployments.id`, `software_changeovers.id` and audit JSONB
request evidence implement optional request UUIDs with existing EVT-DPLOY-/EVT-CO-
event numbers. Existing global UUID/number constraints are retained; history is not
backfilled. Changeover timestamps normalize naive input to UTC; omission remains
null in canonical request evidence while creation generates its timestamp once.

Deployment creation locks Authorization -> Site -> Line, using FOR UPDATE OF Site
on the parent join. It refreshes rows and checks exact scope before insert. It does
not lock existing Deployment after Authorization, preserving Batch's opposite
parent direction. Changeover, actual reporting and Batch all start with Deployment;
only Batch subsequently acquires Authorization. Locks last through atomic audit
commit; validation/constraint/audit/commit failures roll back. At 0.17.0 actual rows had no
version column or request ledger, so latest committed reports still overwrite state.
Real migrated PostgreSQL tests observe blocking, cross-parent uniqueness races,
stale authorization/site/line/deployment refresh, audit rollback, timestamp equivalence,
actual-before history, actual/Batch ordering and absence of reversed-lock deadlock.


## Actual-report version migration (0.18.0)

Revision `0017_deployment_actual_version` adds Deployment actual_version: Integer,
non-null, Python/server default zero, CHECK actual_version >= 0. Existing actual
release/snapshot/status/time stay unchanged and all deployments start at version
zero. This is a concurrency baseline, not a reconstructed historical report count.
Audit history is not backfilled. A downgrade drops the column/check and loses version
protection; coordinate downtime before rolling back a serving writer.

Actual commands lock/refresh Deployment, compare expected_version, update current
projection/version and append audit in one transaction. The existing unique
`audit_events.event_no` stores the global actual-request namespace EVT-DA-{UUID.hex};
no request table or Deployment ID reuse is added. Audit JSONB retains canonical
request and complete before/after state/version/time plus correction reason. Matching
replays recover the original result without incrementing version. Cross-deployment
key races use audit uniqueness as the final guard; the loser fully rolls back.
Batch/Changeover retain the same Deployment-first ordering under READ COMMITTED.
Real PostgreSQL tests cover blocking, competing versions, stale cached state,
rollback/lock release, migration downgrade/upgrade preservation and the negative check.

## Request-preparation UI package

The Snapshot/actual/Batch preparation workspace changes no backend persistence,
migration or seed. Required head remains 0017_deployment_actual_version. Drafts
exist only in browser component memory/explicit clipboard export, not the database.
Expected audit links reference the existing deterministic request event numbers;
no event exists merely because a user prepared or copied a request.

## Governance request preparation

Approval/Decision request preparation reads already exposed approval step UUIDs; it needs no table, column, request ledger or migration. Existing ApprovalAction/ReleaseDecision IDs and EVT-AP-/EVT-RD- audit evidence implement keyed execution. API remains 0.18.0 and Alembic head remains 0017_deployment_actual_version.

## Evidence/reference request preparation

Evidence/reference preparation adds no persistence or migration. Existing domain request UUIDs and atomic audit rows implement execution: EVT-IMPACT-{UUID}, EVT-AC-{UUID}, EVT-LK-{UUID} retain hyphenated suffixes. Draft/copy actions insert nothing. Required head remains 0017_deployment_actual_version.

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

2026-10-01 distribution-chain verification: read-only Render PostgreSQL query returned
`0017_deployment_actual_version`. No schema change was made. Direct API probes were
blocked by workspace network policy; service readiness 200 was observed in Render logs.

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

## Authorization/distribution profile queries — 2026-10-02

No migration: profiles reuse existing columns and COUNT by exact foreign key.
SoftwareAuthorization.distribution_id and Deployment.authorization_id are indexed.
ProductionBatch.authorization_id has no dedicated index in the current model;
its count can scan batch rows. Bounded history payloads/fixed query count do not
prove constant database work or latency. Evaluate plans and representative volume
before deciding an index migration; schema/head stays 0017. Counts include all
statuses and do not change transaction-level batch-limit enforcement.

## Delivery revision read migration — 2026-10-02

No migration is needed. Existing migration 0007 provides uq_delivery_package_revision, ix_delivery_package_items_package_id and ix_distributions_package_id. Profile COUNT/conditional COUNT/distinct-control queries scope by the exact package UUID; artifact rows use outer join, deterministic filename/UUID order and SQL LIMIT/OFFSET. Missing metadata remains visible in defensive reads. Counts and filename sorting can grow in cost with stored rows; no constant-latency guarantee or general load benchmark is claimed. Required head remains 0017_deployment_actual_version.

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

## ASR downstream aggregates — API 0.18.4

No migration. The summary and authorization-release production filter reuse indexed
`delivery_packages.release_id`, `distributions.delivery_package_id`,
`software_authorizations.release_id`, `deployments.authorization_id` and both child
`deployment_id` columns (existing schema, including migrations 0007/0009). Seven cold
SQL queries use count/sum with relational subqueries; no growing Python ID lists or
child ORM payloads. Fixed response/query count does not imply constant scan/sort work.
Multi-query READ COMMITTED totals can observe concurrent commits at different times;
they are informational, not a write receipt or transaction quota enforcement.
Migrated PostgreSQL aggregates/scope regression passed; existing serialization tests
remain intact. Single head 0017 and generated PostgreSQL upgrade SQL passed.

## Evidence index migration — 0018

`0018_asr_evidence_index` follows 0017 and adds only
`ix_dvp_executions_release_snapshot_item` on release_id, snapshot_id, dvp_item_id,
execution_no. The previous schema has no release/snapshot execution index; this index
supports exact scope and per-item latest-row selection. Snapshot artifacts reuse their
existing snapshot_id index. Upgrade uses ordinary CREATE INDEX; downgrade drops only
this index. Matching ORM Index is declared; no backfill, row update, new uniqueness,
write lock or permission change. Real PostgreSQL downgrade/upgrade preserved execution
rows, index column inspection passed, and generated upgrade/downgrade SQL passed.
Window/count queries can still scan/sort history; payload/query bounds do not bound CPU.

## Coverage aggregates — API 0.18.6 / schema 0018

No migration or ORM schema change. Coverage scopes use SCR software/project, change-point
SCR bindings, distinct issue/SCR relations and the UNION of both DVP binding tables.
One SQL result returns counts; exact release/snapshot execution aggregation reuses
`ix_dvp_executions_release_snapshot_item`. Existing binding primary keys remain.
No metadata inner join drops legacy orphan bindings; PostgreSQL foreign keys still
enforce normal writes. SQL count/distinct/union can scan/sort many rows, and some legacy
scope foreign keys lack dedicated indexes; fixed transfer is not a performance guarantee.
Additional indexing should follow measured plans/data, not a claimed constant-time result.
No business or audit data is rewritten. Head stays `0018_asr_evidence_index`.

## SSR summary/projection reads — API 0.18.7

No migration, backfill or ORM schema change; sole head stays 0018_asr_evidence_index.
Component reads select only id/definition code/name/version under exact release_id.
The left join preserves missing metadata in legacy data. Application counts/pages join
stored release_id with Release and filter standard_base_release_id; no Python ID arrays
or child ORM are loaded. UUID ordering resolves duplicate labels/timestamps. Existing
keys enforce normal PostgreSQL FK writes. Some legacy scope FKs lack dedicated indexes;
fixed transfer does not bound database count/sort work. Measured data/plans should guide
additional indexing. Parent metadata/notes remain; no total-byte bound is promised.

## ASR component/baseline projections — API 0.18.8

No schema change; single head stays 0018_asr_evidence_index. Declaration rows left-join
only a baseline component on the stored base Release and identical definition UUID;
missing definition metadata is preserved with a separate left join. Unlinked rows use
NOT EXISTS scoped to exact ASR/definition/base component across all declarations, so
pagination never changes membership. Aggregate counts, UUID ordering and LIMIT/OFFSET
are evaluated in SQL. Missing baseline/detail yields no baseline rows. READ COMMITTED
observations are not a frozen read receipt. Existing foreign keys without dedicated
read indexes can require scans; constant statement shape does not imply constant
runtime. Use measured PostgreSQL plans to justify a later index migration. No command
transaction, quota/number lock or append-only constraint changes.

## ASR frozen policy projections — API 0.18.9

No migration; head 0018_asr_evidence_index. Existing snapshot_artifacts.snapshot_id and
snapshot_artifact_distribution_rules.snapshot_artifact_id indexes support the exact
foreign-key read scopes. Summary uses CASE plus correlated EXISTS for recording counts;
artifact projections use scalar per-row rule counts, and rule pages join exact snapshot
and optional validated artifact UUID. No rule/ID collection is built in Python. Null
recipient_code duplicates remain stored rows and are counted; sorting coalesces null/
empty codes only for ordering, then uses decision/UUID ties. Stable artifact ordering
adds UUID to component/filename. Totals/sorts may grow with data; measured PostgreSQL
plans must justify additional read indexes. READ COMMITTED counts/pages are observations,
not a transaction receipt or status/approval proof. All command locks and audit rules
remain unchanged; migrated PostgreSQL tests verify null ordering and scope/no writes.

## Exact Snapshot projections — API 0.18.10

No schema migration; head 0018_asr_evidence_index. Reuse exact snapshot_no uniqueness,
snapshot_artifacts.snapshot_id and rule.snapshot_artifact_id indexes. Shared frozen
policy SQL projections serve ASR and exact detail, with correlated rule counts and
joined rules; exact file UUID filtering is validated inside the selected Snapshot.
Parent summary counts and stable LIMIT/OFFSET child projections avoid complete child
ORM collections and growing Python ID lists. Existing FK/public fields and nullable
release metadata behavior are retained. Tests cover 124 files/364 rules with fixed
statement shape and bounded transfer; totals/order can still scan growing data.
Real PostgreSQL READ COMMITTED test commits a newer Snapshot in a separate session
between summary and page reads: exact historical pin remains, no audit write occurs.
Reads are observations rather than a cross-request transaction receipt. Existing
command locks, number/quota serialization and atomic audits are unchanged.

## SQL frozen comparison — API 0.18.11

No migration; head 0018_asr_evidence_index. Exact Snapshot lookups and existing artifact/
rule FK indexes are reused. SQL GROUP BY/HAVING count>1 LIMIT 1 rejects duplicate file
identities over the entire selected manifests before paging. A UNION of frozen file
keys is left-joined to exact source/target metadata; NULL-safe IS DISTINCT FROM compares
six fields, and bidirectional EXCEPT of grouped rule tuples plus COUNT compares policy
multisets (NULL differs from empty, multiplicity retained). CASE classifies added/
removed/modified/unchanged; SQL sums/counts and LIMIT/OFFSET bound transfer without
materializing child ORM rows, nested rule arrays or growing Python ID sets. File side
rule counts use correlated SQL counts. UUID tie rules are not part of policy identity.

SQLite exercises projection semantics; the complete PostgreSQL 16.15 suite proves the
actual EXCEPT/null ordering/duplicate behavior and all existing command locks. Growth
from 5 to 65 comparison file identities (including 360 added rules) keeps SQL statement
shape and returned page size fixed, not execution cost. Counts/joins/EXCEPT may scan
increasing data; measure plans before adding indexes. A separate PostgreSQL session
committing a newer Snapshot does not move the explicitly pinned pair. Reads do not
append audits and are not cross-request transaction receipts. All command constraints,
number/quota locks and atomic business/audit behavior remain unchanged.

## ASR passport bounded consumer — 2026-10-03

No migration for API 0.18.12. Existing release FK indexes and Snapshot number
constraints suffice for correctness of the passport read slice. Summary counts use
SQL; identity lookups are fixed and each history materializes at most 100 bounded rows.
No whole downstream ID sets or unbounded decision arrays. Four independent totals and
bounded ordered queries do not imply constant database work; query cost still grows
with release history and needs measurement before adding performance indexes. Snapshot
and decision pins select exact rows and do not create a repeatable-read snapshot of
mutable records. Alembic head stays 0018_asr_evidence_index. PostgreSQL tests prove
paging/scoping and a second-session commit does not retarget selected Snapshot UUID;
existing PostgreSQL write-concurrency suite remains required and unchanged.

## Bounded readiness and policy aggregation — 2026-10-03

No migration. Artifact summary now returns one SQL aggregate row with correlated
rule EXISTS predicates, without full artifact/rule ORM collections or growing ID arrays.
Duplicate nullable rules count an artifact once; nullable levels/SHA/empty strings and
INTERNAL_ONLY match prior Python semantics. Percent rounding and empty-count rates are
unchanged. New readiness summary uses existing SQL coverage plus approved-exception
count/verification-rule presence; exception projection pages are limited to 100 rows.
Existing exception Snapshot FK and rule artifact FK indexes support exact predicates;
no unmeasured performance index is added. Fixed query/response shape is not constant
DB work. Compatibility array APIs and evaluate remain unchanged. A real PostgreSQL
second-session newer Snapshot commit invalidates stale current-readiness summary pin
with 409 while old exception UUID scope remains exact. Reads append no audit. Schema
head remains 0018_asr_evidence_index; full PostgreSQL upgrade SQL remains valid.

## Release catalog consumer migration — API 0.18.14

No schema migration: head stays 0018_asr_evidence_index. Catalogs use outer joins to preserve parent release rows and SQL counts; latest Snapshot lookup uses the existing (release_id, snapshot_number) uniqueness/index. Resolver selects at most two scalar rows. Offset pages/counts are live observations; large-offset performance requires future workload measurements.

## SCR/Issue directory migration — API 0.18.15

No migration; single head 0018_asr_evidence_index. Scalar SCR status counts use case-sensitive SQL replace/length on PostgreSQL and SQLite; issue_no/UUID and SCR created_at/UUID ordering are deterministic. Filtering never expands child ID sets. Large-offset performance still needs representative load measurement.

## SCR detail scalar projections — API 0.18.16

No migration; head 0018_asr_evidence_index. Correlated scalar counts summarize
criteria, valid Issue relations, points, plans, owned-plan items and valid point-item
bindings. Child projections use count subqueries and stable bounded ORDER/LIMIT/OFFSET
without ORM graph hydration or growing ID lists. Exact point/plan ownership checks
prevent selecting another SCR's child. Existing cross-plan point assignments remain
visible; missing references match legacy inner-join visibility. SQL statement shapes
remain fixed after 120-row child/assignment growth. Counts/pages are live reads.

## SCR coverage SQL projections — API 0.18.17

No migration, head 0018. Owned-plan items form a scalar CTE; newest execution_no is
selected with ROW_NUMBER on exact release/Snapshot/item UUID. Correlated group counts
exclude outside-SCR/missing references, aggregate full assignment/result states and
union all definition/assignment gaps without growing ID lists or ORM graphs. Issue
membership uses EXISTS to avoid duplicate relation inflation. Bounded pages project
only selected rows; formal criterion histories have their own pages. Counts preserve
null/rounding/current-definition semantics. Historical execution pins do not freeze
assignments; stale missing-freeze context rejects a newer freeze.
