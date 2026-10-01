# Database

## Current baseline

- Engine: PostgreSQL 16 in the local Compose environment.
- ORM: SQLAlchemy 2.
- Migration tool: Alembic.
- Required schema revision: `0017_deployment_actual_version`.
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
