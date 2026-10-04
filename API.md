# API

Base path: `/api/v1` except health endpoints. Interactive OpenAPI documentation is served at `/docs` when FastAPI is running. Application version is `0.18.23`.

This document is a maintained map, not a replacement for the generated OpenAPI schema or endpoint tests.

## Health

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/health` | Compatibility status |
| GET | `/health/live` | Process liveness and API version |
| GET | `/health/ready` | Database connection plus exact Alembic revision |

## Primary read API families

| Area | Representative paths | Notes |
| --- | --- | --- |
| Dashboard/search | `/api/v1/dashboard/summary`, `/api/v1/search` | Live counts and cross-domain lookup |
| Organizations | `/api/v1/organization-views/{suppliers,customers,projects}`, summary/items; `/api/v1/organizations/release-matrix` | Bounded catalogs and UUID-pinned child pages; legacy organization reads return 410 |
| Releases | `/api/v1/releases`, `/releases/standard`, `/releases/application`, `/releases/application/id/{release_id}` | Exact-ID application profiles are preferred over version-only compatibility routes |
| Snapshot evidence | `/api/v1/releases/{release_id}/snapshots`, `/api/v1/snapshots/{snapshot_no}`, `/compare/{target_no}` | Frozen manifest/history and metadata comparison |
| Change/Issue | `/api/v1/change-catalog/{requests,issues}`, `/change-views/{request_no}/summary`, `/change-coverage-views/{request_no}/summary`, `/issue-views/{issue_no}/summary` and exact impact | Bounded summary/children preserve exact release/Snapshot scope; legacy GETs return 410 |
| Testing | `/api/v1/testing/dvp/catalog`, `/testing/dvp/id/{item_id}/profile`, `/testing/releases` | Bounded DVP directory plus test-release records |
| Governance | `/api/v1/governance/approvals`, `/decisions`, exact profiles/actions | Preferred bounded governance history |
| Distribution | `/api/v1/distribution/catalog/deliveries`, `/distributions`, `/authorizations` | Preferred bounded catalogs; exact delivery revision is significant |
| Production | `/api/v1/production/catalog/{kind}`, `/deployments/{deployment_no}/profile`, `/batches/{batch_no}` | `{kind}` is deployments, changeovers or batches |
| Audit/resources | `/api/v1/audit/events`, `/activity/{event_no}`, `/resources` | Bounded audit review and append-only external references |

API 0.18.22 retires legacy delivery/distribution/authorization/deployment/batch lists and rich production/distribution reads with HTTP 410; use the bounded successors below. Other compatibility families such as governance/audit and release evidence still require review. Not every retained compatibility route is unbounded.

## Existing command endpoints

These endpoints exist in code; their presence does not mean they are safe for anonymous public use.

The detailed security/consistency review is maintained in [docs/write-contracts.md](docs/write-contracts.md). Its executable inventory and test require every registered write route to declare identity, authorization, audit, idempotency and concurrency behavior.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/releases/{release_id}/create-snapshot` | Freeze a release snapshot |
| POST | `/api/v1/approvals/{approval_no}/actions` | Record an approval action |
| POST | `/api/v1/approvals/{approval_no}/release-decision` | Create a release decision |
| POST | `/api/v1/deliveries` | Create a delivery package revision |
| POST | `/api/v1/distributions` | Record a distribution |
| POST | `/api/v1/authorizations` | Create production authorization scope |
| POST | `/api/v1/deployments` | Create deployment expectation |
| POST | `/api/v1/deployments/{deployment_no}/actual` | Report actual software |
| POST | `/api/v1/deployments/{deployment_no}/changeovers` | Record a changeover |
| POST | `/api/v1/deployments/{deployment_no}/batches` | Create a production batch |
| POST | `/api/v1/issues/{issue_no}/impact-assessments` | Append a snapshot-bound impact judgment |
| POST | `/api/v1/changes/{request_no}/acceptance-dvp-links` | Append an acceptance/test assignment |
| POST | `/api/v1/testing/releases` | Create a purpose-limited test release |
| POST | `/api/v1/resources` | Append an external resource reference |

## Safety and consistency rules

- `READ_ONLY_MODE=true` rejects every method except GET, HEAD and OPTIONS with HTTP 403. The public sample API must use this mode.
- `AUTH_MODE=oidc` requires a valid configured OIDC Bearer token and an ACTIVE matching local principal for every write. `READ_ONLY_MODE` takes precedence.
- In OIDC mode, every current write route additionally requires its exact active project/software role or the exceptional `PLATFORM_ADMIN` override. Scope is resolved from stored relationships; a client-supplied project alone is not authorization evidence.
- `AUTH_MODE=disabled` preserves controlled local development compatibility; it is not appropriate for public writes.
- For atomically audited writes in OIDC mode, stored actor names come from the authenticated principal. Audit events also expose `actor_principal_id`, full `actor_display_name` and the original `declared_actor_name`. Disabled mode retains legacy declaration behavior.
- Snapshot, production-batch creation, approval actions, release decisions, deliveries, distributions, production authorizations, deployments and changeovers now accept optional client-generated request IDs, in addition to the existing request-ID commands. Actual reporting now also supports keyed replay plus a required expected version; see the 0.18.0 contract below.
- All 14 current command routes record an audit event in the same transaction as their domain change. Snapshot and production audit payloads retain exact release, snapshot, authorization, deployment and before/after identifiers as applicable.
- Snapshot and exact UUID bindings take precedence over matching version, name or display code.
- Bounded catalogs validate filters, limit and offset; totals/counts apply to the full filtered result, not just the visible page.
- Storage references are intentionally omitted from selected public evidence responses.

## Error conventions visible in current APIs

- `403` — read-only guard blocks a write or the authenticated principal lacks the exact active scope/role.
- `401` — OIDC mode rejects a missing/invalid token or an unknown/disabled principal.
- `404` — exact business record does not exist.
- `409` — conflicting state, ambiguous legacy identifier or incompatible release/snapshot scope.
- `422` — validation failure, unsupported filter or invalid bound.

When an endpoint changes, update its tests and this map. Generated `/docs` remains authoritative for request/response field shapes.

## Snapshot / Batch retry contract (0.14.0)

`POST /api/v1/releases/{release_id}/create-snapshot` accepts no body, JSON null,
`{}` or `{"request_id":"<UUID>"}`. The optional body rejects unknown fields.
`POST /api/v1/deployments/{deployment_no}/batches` adds optional `request_id` to
its existing JSON fields; existing clients and response shapes remain compatible.

With a key, identical requests and the same trusted actor return the original row
and response (HTTP 201), with no second audit or batch-limit consumption. Snapshot
replay is tied to the release ID, not a fresh hash of changing source files. Batch
replay compares deployment, batch number, optional changeover, timestamp and note;
UTC-equivalent timestamps match and omission stays distinct from explicit time.
Different content/actor, a legacy row without retry evidence, or a duplicate batch
number under a different key returns 409. Malformed UUIDs return 422.

Keys identify domain UUIDs within each record type. Without a key, Snapshot still
creates a new record and Batch still rejects duplicate numbers. PostgreSQL locks
serialize Release snapshot numbering and Deployment/shared Authorization batch
quota evaluation through domain/audit commit. Replay still requires current exact
scope authorization. See [write contracts](docs/write-contracts.md) for details.

## Approval / Release Decision retry contract (0.15.0)

Approval action JSON adds optional UUID `request_id` and `expected_step_id`.
Read step UUIDs from `GET /api/v1/governance/approvals/{approval_no}` (`steps[].id`).
When a key is supplied, the exact step UUID is required; missing step or malformed
UUID yields 422. A fresh request targeting a different/currently completed step
returns 409. Unkeyed callers remain compatible with current-step behavior;
providing an optional expected step also protects an unkeyed action from stale use.

Identical keyed actions return HTTP 200 with the original `approval_no`/`status`,
even after later workflow transitions. A replay never approves the next step.
Canonical content includes approval number, declared actor, action, comment and
expected step. Release Decision adds optional UUID `request_id`, returns HTTP 201
with the existing response shape, and compares approval number, decision number,
declared actor, readiness status, decision and notes. Changed content or actor
returns 409; historical rows without retry evidence cannot be claimed.

Both commands lock the owning ApprovalRequest through validation, domain write,
audit and commit. Concurrent decisions wait for the final action and recheck its
committed status. Distinct decision numbers retain existing append-history behavior;
a duplicate decision number under another key conflicts. Every replay still passes
current exact-scope authorization. No migration or server retry loop is added.

## Delivery / Distribution / Authorization retry contract (0.16.0)

`POST /deliveries`, `/distributions` and `/authorizations` add optional UUID
`request_id` to their existing JSON. UUID validation returns 422; existing payloads
and HTTP 201 response shapes remain compatible. Same key/content/trusted actor
returns the existing domain row without additional business/items/audit records.
Responses expose that row's stored status; this is not a frozen historical response
body or a lifecycle transition API. Reusing a key with changed content/actor or
claiming a legacy row without request evidence returns 409. Without a key, duplicate
business numbers still conflict; delivery identity includes both number and revision.

Canonical retry content includes every existing input field. Delivery artifact UUIDs
are compared as a sorted collection: order changes match, duplicate IDs remain
invalid. Strings and optional/null values keep existing exact semantics. Distribution
and Authorization have no declared-actor input; OIDC still binds their trusted actor.
Replay precedes mutable parent eligibility/latest-decision checks but always requires
current exact HTTP scope. Fresh writes retain all frozen artifact policy, recipient,
release/snapshot, customer/project, purpose and batch-limit checks.

Delivery locks Release then the selected decision's ApprovalRequest. Distribution
locks its exact DeliveryPackage. Authorization locks Release, Package, Distribution
in that order. Release Decision now locks Release before ApprovalRequest, coordinating
all current latest-decision writers/readers. Locks refresh ORM state and last through
atomic domain/audit commit. Unique UUID/business constraints guard cross-parent races;
all validation/constraint/audit/commit failures roll back. No migration, public writes,
correction/revocation or automatic server retry is introduced.

## Deployment / Changeover retry contract (0.17.0)

`POST /deployments` and `/deployments/{deployment_no}/changeovers` add optional UUID
`request_id`. Existing payloads and HTTP 201 shapes stay compatible. Same key/content/
trusted actor reuses the existing domain row and audit. Returned status is the row's
current stored status, not a historical response-body ledger. Changed content/actor,
legacy evidence missing, or duplicate number under another/no key returns 409;
malformed UUID returns 422. Keys are global within each domain table.

Deployment compares deployment number, authorization UUID and production-line UUID.
Changeover compares deployment number, changeover number, source release UUID,
changed_at and note. UTC-equivalent timestamps match; naive changed_at means UTC.
Omission remains distinct from explicit time and generates server time only once.
Replay precedes mutable parent/domain checks, but every HTTP call still needs current
exact project PRODUCTION_OPERATOR scope and trusted actor resolution.

New Deployment locks Authorization -> Site -> Line, refreshes cached state, verifies
approved authorization, active parents and exact customer/project/site/line scope.
New Changeover locks Deployment and retains existing source/target checks. Distinct
changeover numbers remain append history; no single-use transition rule is invented.
Actual reporting now uses the same Deployment lock as Changeover and Batch, ensuring
serialized before/after audit state and batch eligibility checks. At version 0.17.0 actual reports
still lacked request-ID replay, optimistic tokens and explicit correction semantics;
repeated reports append new events and may overwrite the previous actual state.
All validation/constraint/audit/commit failures roll back. No migration, automatic
server retry, frontend write UI or write-enabled public deployment is added.


## Actual-software reporting (0.18.0)

POST `/api/v1/deployments/{deployment_no}/actual` adds optional UUID `request_id`,
`expected_version` (strict non-negative integer) and `correction_reason` (1–2000
characters, not whitespace-only). Keyed calls require expected_version; malformed
fields/missing keyed version return 422. Read actual_version from deployment detail.
HTTP 200 retains deployment_no/status and adds actual_version. A matching keyed
retry returns the original committed status/version even after a later correction.

A new keyed report with a stale expected version returns 409. Replacing any existing
actual report requires correction_reason, including migrated version-zero rows.
Same key with different content/target/full actor or legacy evidence returns 409.
Timestamps normalize to UTC; naive means UTC and omission differs from explicit time.
Every call still needs current exact PRODUCTION_OPERATOR authorization.

Example: first read detail at version 0, then POST release/snapshot IDs with a new
request UUID and expected_version=0. Retry that exact payload/key after a network
failure. For a correction, reread detail, use a new key/current expected_version and
an explicit reason. The audit retains before/after state; existing batches and physical
flashing are not reversed. Legacy no-key calls remain compatible, increment version
and append events, but have no retry safety or required precondition. See the full
contract in [docs/write-contracts.md](docs/write-contracts.md).

## Frontend command preparation

`/commands` prepares keyed Snapshot, actual-software, Batch, Approval Action and
Release Decision requests using the
existing 0.18.0 contracts. It copies an envelope `{method, path, body}`; a controlled
client sends only body as JSON. No frontend mutation route or new backend API is
added. Client checks do not establish authorization, entity membership or quota.
See [UI contract](docs/controlled-write-ui.md) for confirmation/retry and trace limits.

Approval preparation requires expected_step_id and an explicit APPROVED/RETURNED/REJECTED
action. Decision readiness_status/decision remain exact declarations, not computed
readiness or newly enforced enums. Declared actor text is not authenticated identity.
Approval detail exposes existing step UUIDs and preparation links; no API shape changes.

## Evidence/reference request preparation

/commands additionally prepares Impact Assessment, Acceptance-to-DVP and Resource bodies with their existing required request UUIDs. Actor/reason/reference normalization follows their Pydantic schemas; resources use a stricter syntactic URL/path subset. No API request/response or authorization changes. Copy method/path/body as instructions; send only body through the controlled API client.

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

## Bounded deployment profile (0.18.1)

`GET /api/v1/deployments/{deployment_no}/profile` resolves the exact business number
or returns 404. It returns identity, stored status, expected/actual references,
`actual_version`, separate `software_observation`, exact authorization/distribution/
delivery parent references and `history_counts` for changeovers/batches. It omits
embedded `changeovers`, `batches` and `provenance.release_decisions` arrays; it does
not load their row payloads. Missing parent references stay null.

Use `/production/catalog/changeovers` and `/production/catalog/batches` with the
returned `deployment_id`; decisions use `/governance/decisions` with the delivered
release and snapshot UUIDs, not inferred expected/current versions. Those existing
catalogs default to 50 rows, allow at most 100 and expose total/next_offset.
Counts and profile fields are live read observations, not a transaction receipt,
remaining batch capacity or authorization. COUNT work may grow with history even
though response size and query count remain bounded. The old deployment detail and
provenance endpoints retain their complete legacy shapes; other legacy consumers
remain to migrate. No write contract, identity configuration or schema change.

## Bounded authorization and distribution profiles (0.18.2)

- `GET /api/v1/authorizations/{authorization_no}/profile`: exact business-number
  identity, complete stored scope, restriction/approval/limit and exact distribution/
  delivery revision references; `history_counts.deployments` and `.batches` replace
  embedded `deployments`/`batches` arrays.
- `GET /api/v1/distributions/{distribution_no}/profile`: exact distribution and
  package revision, recipient, timeline, note and software references;
  `history_counts.authorizations` replaces the embedded `authorizations` array.

Missing exact records return 404; unresolved parent references stay null. Counts
include every recorded status and use stored foreign keys, without selecting child
payloads or inferring a release, location or receipt. Use bounded production catalogs
with returned `authorization_id`, or the authorization catalog with returned
`distribution_id`; default 50/max 100 rows and next_offset remain unchanged.
The UI's finite unfilled slots are max(0, limit - full batch count); null remains
unlimited/no finite limit recorded. Neither count, acknowledgment nor stored APPROVED
is a permission receipt, capacity reservation or a consistent transaction snapshot.
Old detail endpoints keep their complete array shapes for controlled clients.
No write contract, authentication/public-read policy or schema changes.

## Exact delivery revision reads (0.18.3)

- GET `/api/v1/deliveries/{package_no}/revisions/{revision}/profile`: exact positive
  revision, never latest. Retains package UUID/status, exact release/frozen snapshot,
  recipient/purpose/creator; omits items/distributions. `history_counts.artifacts`
  counts stored DeliveryPackageItem rows (including missing metadata),
  `history_counts.distributions` counts every stored status. Fixed `policy_counts`
  contains ALLOW, APPROVAL_REQUIRED and OTHER with zero defaults; OTHER preserves
  unfamiliar legacy values. `control_reference_count` counts distinct non-null
  stored references, not a list of approvals.
- GET `/api/v1/deliveries/{package_no}/revisions/{revision}/artifacts`: query
  `limit` 1–100 (default 50), `offset` 0–100000 (default 0); extra/invalid queries
  return 422. Returns exact delivery_package_id/package_no/revision, full total,
  next_offset and bounded items. Each row includes item UUID, recorded artifact UUID,
  frozen filename/type/SHA-256/distribution level, stored policy/control; missing
  artifact metadata stays null and the row remains visible. Storage references are
  omitted. Ordering is coalesced filename, artifact UUID, item UUID.
- Missing exact package/revision is 404, nonpositive revision is 422. Legacy latest
  and exact revision endpoints retain their original shapes. Distribution review
  uses `/distribution/catalog/distributions?delivery_package_id={exact_uuid}`.

Profile and artifact totals are separate read observations, not a transaction-wide
receipt, current permission, file access or delivery evidence. Offset pages do not
provide a consistent historical snapshot during concurrent writes.

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

## ASR downstream summary and production scope — API 0.18.4

`GET /api/v1/releases/application/id/{release_id}/downstream-summary` validates an
exact APPLICATION release UUID (404 absent/wrong release type, 422 malformed UUID).
It returns a fixed object, including zeros for an empty chain:

```json
{
  "release_id": "<exact UUID>",
  "history_counts": {"deliveries": 0, "distributions": 0, "authorizations": 0, "deployments": 0, "changeovers": 0, "batches": 0},
  "actual_release_observations": {"same_release": 0, "different_release": 0, "not_reported": 0},
  "batch_release_observations": {"same_release": 0, "different_release": 0}
}
```

All statuses count. Deliveries and authorizations use their own release UUID;
distributions use the delivery parent; deployments use authorization parent;
changeovers/batches use deployment parent. Release mismatches do not remove linked
records. Observations compare UUIDs only; no snapshot match or physical flashing is
inferred. Unknown summary in the UI is not zero. Legacy `/downstream` is unchanged.

`GET /api/v1/production/catalog/{kind}?authorization_release_id=<UUID>` accepts a
validated optional UUID for deployments/changeovers/batches. It filters the release
of each deployment's stored authorization (also for batches whose own authorization
is inconsistent). Existing `release_id` still filters expected deployment release,
changeover destination release or batch release respectively; both filters intersect.
Existing limit 1–100, offset 0–100000, ordering and validation remain. Pagination,
filter submit and kind navigation retain the new scope in the frontend.

Summary response/query count is fixed (seven cold queries), not database work.
READ COMMITTED observations across queries are not a consistent write receipt or
quota reservation. Existing indexes suffice; no migration or write contract change.
ASR profile/evidence and remaining compatibility consumers are still unbounded.

## ASR pinned evidence reads — API 0.18.5

All paths start `/api/v1/releases/application/id/{release_id}`. Exact APPLICATION
release required; missing/wrong type or snapshot belonging to another release: 404.
Malformed UUID, unknown query keys or invalid pagination: 422.

- `GET /evidence-summary?snapshot_id=<optional UUID>` returns release_id,
  snapshot `{id, snapshot_no, is_current_snapshot}` or null, artifact_count,
  latest_execution_count and other_snapshot_executions. Default selects highest
  snapshot_number; absent snapshot returns explicit null and zero counts.
- `GET /evidence/artifacts?snapshot_id=<required UUID>&limit=50&offset=0` returns
  release_id, snapshot_id, total, limit, offset, next_offset and items with frozen
  UUID/component/version/filename/type/SHA/classification/distribution/AI metadata.
  It omits storage_reference and policy rule arrays.
- `GET /evidence/executions?snapshot_id=<required UUID>&limit=50&offset=0` returns
  the same envelope with latest execution per item UUID on only that release/snapshot:
  id, dvp_item_id, item_no/title (nullable), execution_no, result, executed_at
  (nullable) and item_metadata_available. Missing metadata does not drop evidence.
  It omits actual_result and never infers coverage/readiness/permission.

Limits 1–100, offsets 0–100000. Artifact sorting component/filename/UUID;
execution sorting item_no null-last/item UUID/execution UUID. Latest selection ranks
execution_no descending, then executed_at/UUID. Other-snapshot count is every execution
on that release outside the selected snapshot, not just other latest rows.
Legacy evidence response remains unchanged. The frontend retains a pinned UUID in
both table pagination links and explicitly distinguishes missing snapshot, unknown
summary, invalid/unavailable page and beyond-end empty page. These are read observations;
new executions can shift offset pages even on a pinned snapshot. ASR profile coverage
and other legacy consumers remain unbounded. Schema head 0018, no write contract changes.

## Release coverage aggregation — API 0.18.6

`GET /api/v1/releases/{release_id}/coverage` and profile/readiness consumers retain their
existing response fields and status behavior. Shared coverage calculation now uses SQL
aggregates rather than loading child history. Distinct required DVP UUIDs are the union
of change-point and linked-issue bindings; only executions on the exact release and
selected Snapshot count. `current_snapshot_passed` means any PASS for that required item
on the selected Snapshot, even if a later result fails; it is not the evidence catalog's
latest-result metric. `dvp_execution_coverage` measures executed required items, not PASS.
Empty denominators stay 100; `snapshot_match` requires at least one selected required
execution. Internal explicit invalid/foreign Snapshot selection remains null without
fallback. APPLICATION SCR scope is exact project plus project-null; missing detail
retains the legacy software-wide fallback. API boundary missing-release validation is
unchanged. These are read observations, not permission, write receipts or reserved quota.
No new parameters/endpoints/migration; schema remains 0018. Other profile reads remain
partially unbounded.

## SSR parent summary and bounded collections — API 0.18.7

All paths begin `/api/v1/releases/standard/id/{release_id}`; exact STANDARD UUID parents
are required (404 for missing/wrong type, 422 for malformed UUID).

| GET suffix | Response | Parameters |
| --- | --- | --- |
| `/summary` | Legacy parent metadata without child arrays, plus component_count/application_count | No query fields |
| `/components` | id/code/name/version projections; missing definitions retained as null | limit 1–100 (default 50), offset 0–100000 (default 0) |
| `/applications` | id/version/status of stored baseline-linked releases, all statuses | Same pagination |

Pages return release_id/total/limit/offset/next_offset/items. Unknown query fields return
422; beyond-end pages retain total and return empty items/null next_offset. Components
order UUID ascending, matching the old profile. Applications order created_at descending
(null last), then UUID descending. Exact baseline bindings determine membership even
when software/status differ; missing referenced Release rows are excluded as before.
The old bare profile endpoint is unchanged. No new snapshot/approval/permission claim:
these are declaration/baseline observations; separate totals/pages may differ during
concurrent writes. Frontend keeps release_limit and independent component/application
offsets, forwarding invalid values rather than silently resetting them. No migration.

## ASR component summary and independent pages — API 0.18.8

All paths begin `/api/v1/releases/application/id/{release_id}/components`.
Exact APPLICATION UUID required: missing/wrong type 404, malformed UUID 422.

| GET suffix | Response | Query parameters |
| --- | --- | --- |
| `/summary` | release_id/version/base_release{id,version} or null, component_count/unlinked_base_count | None |
| `/declarations` | id/code/name/asr_version/declared_delta_type/base_component_version/base_link_status | limit 1–100 default 50; offset 0–100000 default 0 |
| `/unlinked-base` | id/code/name/version for baseline components without a valid ASR link | Same bounds |

Pages return release_id/base_release_id/total/limit/offset/next_offset/items. Unknown
query fields return 422; beyond-end retains total with empty items and null next_offset.
Both pages order UUID ascending. VALID means exact stored baseline component and same
definition UUID, even if version is null; wrong/foreign pointer INVALID, no pointer
NOT_RECORDED. Unlinked rows use every declaration in the exact ASR, independent of
pagination; duplicate links are not duplicate exclusions. Missing/inactive definition
metadata remains visible. Missing detail/base returns null baseline/empty baseline page.
Legacy bare `/components` remains unchanged. No inheritance/approval inference; separate
reads can change. Frontend rejects a different release/baseline context instead of
showing mismatched data. UI parameters component_limit/declaration_offset/unlinked_offset
preserve independent offsets. No migration; schema 0018 unchanged.

## ASR frozen policy summary and pages — API 0.18.9

All suffixes start `/api/v1/releases/application/id/{release_id}/snapshot-policy`.
Exact APPLICATION UUID required; missing/wrong type 404, malformed UUID 422.

| GET suffix | Query | Response |
| --- | --- | --- |
| `/summary` | optional snapshot_id UUID, otherwise highest snapshot_number | release_id, snapshot{id,snapshot_no,status,content_hash,is_current_snapshot} or null; artifact_count/sha_recorded_count/policy_recorded_count/rule_count |
| `/artifacts` | required snapshot_id; limit 1–100 default 50; offset 0–100000 default 0 | frozen public metadata plus rule_count, no embedded rules/storage_reference |
| `/rules` | same bounds; optional snapshot_artifact_id UUID | id/snapshot_artifact_id/filename/component_code/distribution_level/recipient_type/purpose/recipient_code/decision |

Pages return release_id/snapshot_id/total/limit/offset/next_offset/items; rule envelope
also echoes snapshot_artifact_id or null. Missing/foreign snapshot or selected artifact
returns 404; unknown/malformed queries return 422. Beyond-end retains total, empty items
and null next_offset. Artifact order component_code/filename/id. Rule order same artifact
keys then recipient_type/purpose/coalesce(recipient_code,'')/decision/id, preserving
stored null/empty codes and duplicate null-recipient rows with stable UUID tie breakers.
Counts match legacy page recording semantics: non-empty SHA, INTERNAL_ONLY or any rule.
Rule count includes every stored rule, not distinct recipient grants. These are not
hash verification, permission or approval. INTERNAL_ONLY remains denied externally.
Default summary selection includes all statuses as before; selecting a snapshot does
not upgrade its status. Separate reads are not a transaction receipt. Legacy bare
endpoint unchanged. UI policy_snapshot_id/policy_limit/policy_artifact_offset/
policy_rule_offset/policy_artifact_id preserve exact pin and independent pages; artifact
selection resets only rule offset. No migration, head 0018.

## Exact Snapshot summary and independent manifest pages — API 0.18.10

All routes start `/api/v1/snapshots/{snapshot_no}`; exact number lookup supports both
STANDARD and APPLICATION snapshots, all statuses, including historical records.

| GET suffix | Query | Response |
| --- | --- | --- |
| `/summary` | no query fields | Legacy identity fields without artifacts; release_id, artifact_count, rule_count |
| `/artifacts` | required snapshot_id UUID; optional snapshot_artifact_id UUID; limit 1–100 default 50, offset 0–100000 default 0 | Public frozen file metadata, full SHA-256, rule_count; no nested rules or storage_reference |
| `/rules` | same pin, optional artifact UUID and pagination | Rule id, exact artifact UUID, filename/component/distribution and original recipient/purpose/code/decision |

Both child envelopes contain snapshot_no/release_id/snapshot_id/snapshot_artifact_id
(or null)/total/limit/offset/next_offset/items. Name and UUID must identify the same
Snapshot; missing/foreign Snapshot or artifact gives 404, malformed/unknown query 422.
Beyond-end returns full total, empty items, null next_offset. Orders match ASR policy
pages (component/filename/artifact UUID, then recipient/purpose/coalesced code/decision/
rule UUID). Null/empty stored recipient codes and duplicate null rows remain unchanged.
Summary preserves highest-number current flag over all statuses and release:null if
metadata is unavailable; release_id still identifies the exact frozen FK. No latest
substitute, authorization, hash verification or approval is established by these reads.

Exact detail UI uses manifest_snapshot_id/manifest_limit/manifest_artifact_offset/
manifest_rule_offset/manifest_artifact_id. A provided wrong parent pin fails closed.
Both tables validate returned name/UUID/release/filter context independently. Selecting
or clearing a file resets both offsets and filters both tables. Other paging preserves
the other offset and exact pin. Search-generated frozen artifact links include the
exact file query and retained #artifact-UUID anchor, even when the file was beyond the
first page. Old bare fragment bookmarks alone locate only files on the current page;
use the exact file query for off-page targets. Identity/full hashes/history/compare/
resource and preparation links remain; no bulk fallback. Legacy bare detail and compare
APIs remain compatible and unbounded. No migration; schema 0018.

## Bounded Snapshot comparison — API 0.18.11

All routes start `/api/v1/snapshots/{source_no}/comparison/{target_no}`.

| GET suffix | Query | Response |
| --- | --- | --- |
| `/summary` | no fields | release_id; source/target identity including UUID, number, full hash/date/status; content_hash_matches; frozen version/release_type metadata_changes; full added/removed/modified/unchanged counts |
| `/files` | required source_id/target_id UUIDs; show=changes (default) or all; limit 1–100 default 50; offset 0–100000 default 0 | exact pair identities, show, total/limit/offset/next_offset/items |

Every file matches component_code + filename. Renames are added/removed; repeated file
identity anywhere in either manifest returns 409, even outside the requested page or
changes filter. Missing names/mismatched name–UUID pins return 404; different release
returns 409; malformed, unknown or invalid filter/query returns 422. Self/empty reads
are valid. Files order by component_code/filename; changes filtering and counts are SQL.
Beyond-end retains filtered total with empty items/null next_offset. Summary counts
always describe the complete pair, independently of files filtering/pagination.

Items contain component_code/filename/change_type/changed_fields and before/after or
null when absent. Each side has artifact_type/component_version/full sha256/
classification/distribution_level/ai_access_policy plus exact snapshot_artifact_id and
rule_count, without nested policy_rules or private storage_reference. Policy comparison
uses stored recipient_type/purpose/recipient_code/decision and duplicate multiplicity;
rule UUIDs/insertion order are irrelevant, NULL and empty codes remain distinct. This
also removes the old helper's equal-sort-key ordering ambiguity for mixed NULL/empty
codes; legacy bare comparison is intentionally unchanged. Rule changes are detected
even when file/content hashes match. Counts/rules/hashes/status do not establish grants,
hash verification or approval; INTERNAL_ONLY remains externally denied.

UI calls bounded exact source summary, existing bounded history (latest 100 suggestions),
comparison summary and one bounded file page. to/show/compare_limit/compare_offset and
compare_source_id/compare_target_id pin pagination to both selected identities, never
reselecting latest. Changing the comparison form resets paging. Returned summary/page
name/UUID/release/filter mismatch fails closed; a failed file page retains summary.
Each side links its exact frozen file to paginated rules on the detail page. Chinese
default/English supported. Legacy comparison route remains compatible/unbounded.
No migration, schema 0018; separate GETs are observations, not a transaction receipt.

## ASR passport bounded consumer — 2026-10-03

API 0.18.12 adds GET `/api/v1/releases/application/id/{release_id}/passport/summary`
and `/passport/{decisions|deliveries|distributions|authorizations}`. Exact APPLICATION
release UUID only (404 on missing/wrong type). Summary accepts either no selection
(first observation: latest Snapshot across statuses and latest decision ordered by
`decided_at DESC, decision_no DESC, id DESC`) or both `snapshot_id` and `decision_id`.
Each pin is an exact owned UUID or literal `none`; omission and explicit `none` differ.
Both pins are required on pages; one supplied pin/unknown fields/invalid UUID give 422.
Pages default limit=50, allow 1..100, offset=0..100000; return release_id, both pins,
delivery_scope_snapshot_id, total, limit, offset, next_offset, items. Summary returns
profile, selection pins, selected decision and SQL counts for all four groups; no
coverage or child arrays. Snapshot full hash and historical/current metadata remain.
Decision metadata includes `is_selected_snapshot`, `context_consistent`; summary also
returns `is_current_snapshot` and `is_latest_decision`. Approval is exposed only when
its RELEASE target/release UUID/Snapshot UUID all match. Metadata absence is unknown,
never approval. Context consistency requires the owned Snapshot to be FROZEN; recorded
decision/approval status remains an observation, not a new write authorization.
Deliveries use exact release_id and, when a decision is selected, decision.snapshot_id
regardless of missing Snapshot name/metadata. Explicit no-decision selection shows
release-wide deliveries. Distributions join their direct delivery parent by exact
release; authorizations use their direct release FK. These last two are release-wide,
not narrowed to decision Snapshot; no inferred grant. Pages keep selected UUIDs after
new commits, but offset pages/counts are live observations, not a frozen database view.
Ordering: decision time/no/id descending; package no/revision/id; distribution no/id;
authorization no/id. Legacy profile/decision/history/downstream APIs remain compatible.
UI query keys: passport_snapshot_id, passport_decision_id, passport_limit and four
passport_{group}_offset values. Independent page failures preserve summary and other
pages; no bulk fallback. Formal current badge requires selected RELEASE, current
Snapshot, latest decision and consistent binding; historical selection cannot override
newer HOLD. Chinese is default, English selectable, raw UUIDs/full hashes preserved.

## Bounded readiness and policy aggregation — 2026-10-03

API 0.18.13 adds GET `/api/v1/releases/application/id/{release_id}/readiness/summary`
and `/readiness/exceptions`. Exact APPLICATION release UUID required; missing/wrong
release type gives 404. Summary has optional snapshot_id (UUID or literal `none`),
unknown query fields/invalid values give 422. With no pin, observe latest Snapshot
across statuses as before. A supplied UUID must belong to this release (404 otherwise),
and must equal the observed current Snapshot (409 if a newer Snapshot replaced it).
Explicit `none` succeeds only while there is no current Snapshot; it never reselects.
Summary returns release_id, snapshot_id (UUID or `none`), snapshot{id,snapshot_no,status,content_hash},
overall, approval_eligible, coverage, artifact_policy, exactly eight rules, exception_total;
no exception array. Every raw/effective rule, evidence string and eligibility rule remains
identical to compatibility readiness. Only approved verification exceptions can change
the verification effective result; hard SHA/policy/frozen/match gates remain enforced.

Exceptions requires snapshot_id UUID or `none`, limit default50/range1..100,
offset default0/range0..100000; unknown fields/invalid arguments give 422. UUID must
belong to exact release; this page may inspect an owned historical Snapshot. Literal
`none` returns explicit empty selection, without fetching a later Snapshot. Page is
APPROVED-only, ordered exception_no/id, and returns release_id, snapshot_id, total,
limit, offset, next_offset, items{id,exception_no,status,scope,reason,
compensating_control,rule_code,snapshot_no}. Missing child metadata is not synthesized.

The UI uses readiness_snapshot_id, readiness_limit, readiness_exception_offset. Summary
is read first; stale/mismatched/failed selection stops child reads and provides latest
refresh. Child failure preserves eight gates/full total rather than reporting zero
exceptions. Full Snapshot UUID/hash, reason/control and Chinese-default/English remain.
Readiness keeps live release artifact declarations (not frozen Snapshot policy), current
Snapshot DVP evidence and approved exceptions. Empty policy percentages remain 100 but
zero artifacts still fail formal SHA/policy gates. Non-empty SHA (including whitespace)
is recording completeness, not cryptographic verification. Any recorded rule makes a
non-internal artifact policy-complete; INTERNAL_ONLY overrides eligibility flags.
SQL EXISTS avoids multiplying artifact counts for duplicated nullable recipient rules.
Legacy readiness/artifact endpoints and ArtifactPolicyService.evaluate remain compatible;
legacy array routes/evaluator may still be unbounded. Current UI does not call them.
Reads/counts/pages are live observations, not cross-request transaction receipts or grants.

## Bounded release catalogs — API 0.18.14

- GET `/api/v1/release-catalog/{application|standard}` accepts q (literal escaped
  substring, max 200), status (exact, max 30), software_id (exact UUID),
  limit (1..100, default 50), offset (0..100000, default 0). Unknown fields and
  malformed filters return 422. Returns kind, total, limit, offset, next_offset,
  items. Counts cover all matching rows, including beyond-end pages. Ordering
  is created_at DESC NULLS LAST then id DESC. Original catalog row fields are
  preserved; missing optional metadata is null rather than discarding a release.
  ASR snapshot_no is the latest stored snapshot_number, not a release judgment.
- GET `/api/v1/release-catalog/application/resolve?identifier=...` requires a
  nonempty literal identifier of at most 100 characters. Exact canonical UUID
  OR exact version matches only APPLICATION releases, with LIMIT 2. Returns
  state unique/ambiguous/missing; release {id, version} only for unique. A UUID
  equal to another ASR version is ambiguous. No trimming, case folding or
  arbitrary first-match fallback. Resolution is not limited by catalog pages.
- Legacy `/releases/application`, `/releases/standard` array contracts remain.
  New frontend consumers do not call them. Counts/pages observe mutable records
  and may change between requests; no frozen pagination session is implied.

## Bounded change and Issue directories — API 0.18.15

- GET `/api/v1/change-catalog/requests`: q (literal request_no/title substring, max
  200), status (exact, max 40), scope (exact, max 30), source (max 30), change_type
  (max 40), software_id/customer_id/project_id (exact stored UUID fields), limit
  (1..100, default 50), offset (0..100000, default 0). Unknown/invalid fields get
  422. Order created_at DESC NULLS LAST, UUID DESC; request rows preserve old list
  fields. Returns kind=changes, total, in_verification, ready_for_release, limit,
  offset, next_offset, items. All three counts cover the full filtered set; status
  statistics preserve case-sensitive TEST/READY substring markers from the former
  UI and are not authoritative readiness judgments. Empty counts are zero.
- GET `/api/v1/change-catalog/issues`: shared q/status/scope/limit/offset plus
  severity (exact, max 20), ordered issue_no then UUID ASC. q searches literal
  issue_no/title. Returns kind=issues and the same pagination envelope without
  SCR status statistics. Rows include id/issue_no/title/scope/severity/status;
  description remains on exact Issue profiles. SCR-only filters are rejected.
- Beyond-end pages preserve full counts. Legacy bulk `/changes`, `/issues` and
  rich profiles remain; only these two frontend directories migrated. Counts and
  offset pages are independent live observations, not frozen cross-request data.

## Bounded SCR detail — API 0.18.16

All GET paths start `/api/v1/change-views/{request_no}`. Exact business number
lookup returns 404 when absent. Unknown query fields and invalid UUID/pagination
values return 422. No legacy bulk fallback is used by the SCR detail page.

| Suffix | Projection | Stable ascending ordering |
| --- | --- | --- |
| `/summary` | Parent metadata and six full scalar counts, no child arrays | Single exact parent |
| `/criteria` | Criterion UUID/number/description | criterion_no, UUID |
| `/issues` | Relation UUID, Issue UUID/number/title/type/status | issue_no, relation_type, relation UUID |
| `/points` | Point UUID/number/title/description/status/item_count | change_no, UUID |
| `/plans` | Plan UUID/number/title/status/item_count | plan_no, UUID |
| `/points/{point_id}/items` | Exact point assignment with DVP UUID/number/title/status/plan_id/relation_type | item_no, DVP UUID |
| `/plans/{plan_id}/items` | Exact owned-plan DVP UUID/number/title/status/plan_id | item_no, DVP UUID |

Summary accepts no query fields. Counts: criterion_count, issue_count (relations to
existing Issues), point_count, plan_count, point_item_count (bindings to existing
DVP items, including other plans), plan_item_count (items in this SCR's plans).
Optional software/customer/project metadata may be null without discarding parent.
All six pages require `change_id` UUID matching the resolved business number;
limit 1..100 (default 50), offset 0..100000 (default 0). Wrong parent pin or child
not owned by the SCR returns 404. Envelope: change_id, request_no, total, limit,
offset, next_offset, items; selected child pages also return point_id or plan_id.
Full totals remain on beyond-end pages. Offset/count reads are independent mutable
observations; identity pins do not promise Snapshot consistency.

Frontend query keys: scr_limit, criteria_offset, issues_offset, points_offset,
plans_offset, point_items_offset, plan_items_offset, point_id, plan_id. Repeated
parameters remain invalid rather than silently selecting/resetting one. Selected
DVP links use exact item UUIDs. Coverage remains a separate rich consumer.

## Bounded SCR coverage — API 0.18.17

All GET paths start `/api/v1/change-coverage-views/{request_no}`. Unknown or invalid
query fields return 422; missing exact SCR or mismatched change_id returns 404.
Summary accepts optional release_id UUID, snapshot_no (1..80 chars) or snapshot_id
(UUID or none). Snapshot selection requires release_id; snapshot_no and snapshot_id
are mutually exclusive. Omitted Snapshot chooses latest FROZEN number. Exact release
selection checks stored software/customer/project candidate scope (409 on mismatch);
missing release 404, wrong/non-frozen Snapshot 409. Historical pins remain valid after
new freezes. Literal none on a release that now has a freeze gets 409; reset report.

Summary returns change_id, request_no, release_id/snapshot_id (UUID or none), selected
release/Snapshot metadata, basis, candidate_count, gap_count and full coverage summary.
No child arrays. Every page/selected-group summary requires change_id, release_id and
snapshot_id pins; assignments-only uses none/none. limit 1..100 (default 50), offset
0..100000 (default 0); Snapshot without release is rejected. Envelopes preserve pins
plus total, limit, offset, next_offset, items; selected pages add kind/group_id.

| Suffix | Rows | Stable ordering |
| --- | --- | --- |
| `/candidates` | Complete candidate release set, scalar UUID/type/version/status/created_at | created_at DESC NULLS LAST, UUID DESC |
| `/gaps` | Full definition/assignment gaps, code/ref/message/owner_id/kind | code, ref, kind, owner_id ASC |
| `/groups/{kind}` | Definitions with full assigned/excluded counts and verification | ref, UUID ASC |
| `/items` | All items from SCR-owned plans, exact latest execution fields | item_no, UUID ASC |
| `/groups/{kind}/{group_id}/summary` | Exact owned criterion/point/linked Issue scalar metadata/counts; no arrays | One exact record |
| `/groups/{kind}/{group_id}/items` | Valid assigned items from SCR-owned plans, exact latest execution fields | item_no, UUID ASC |
| `/acceptance/{criterion_id}/assignments` | Formal assignment UUID/test UUID/reviewer/reason/time, including excluded references | created_at, UUID ASC |

kind is acceptance/points/issues. A selected UUID must be in this SCR's group or
returns 404. Group summary includes assignment_count (criteria only); pagination
fields are validated but do not change its single-record lookup. Test item rows
include id/item_no/title/scope/declared_status/plan_id/execution_no/result/actual_result/
executed_at; last four are null without matching execution context. Latest execution
number is scoped to exact release + frozen Snapshot; prior PASS never replaces later
FAIL. Full counts survive beyond-end and page failures. Definitions/assignments are
current observations, not Snapshot-frozen definitions. Legacy coverage/write APIs remain.

Frontend query keys: release_id, snapshot_no or snapshot_id, coverage_limit,
candidates_offset, gaps_offset, acceptance_offset, coverage_points_offset,
coverage_issues_offset, coverage_items_offset, group_items_offset, assignments_offset,
group_kind, group_id. Links retain exact execution pins and other cursors; selecting a
new group resets only its two child offsets. A new release review resets the context.
Empty release/Snapshot form fields select assignments-only/default freeze; repeated
parameters are forwarded as invalid rather than silently resetting.

## Bounded Issue detail/impact — API 0.18.18

All GET paths start `/api/v1/issue-views/{issue_no}`. Unknown fields/invalid UUIDs
or pagination return 422. Missing business number or mismatched issue_id returns
404. Summary accepts no query fields and returns existing Issue metadata plus
linked_count (relations to real SCRs), candidate_count (visible releases with real
software product metadata), assessment_count (all formal records), basis.

| Suffix | Projection | Stable ordering |
| --- | --- | --- |
| `/changes` | Relation UUID, SCR UUID/number/title/status/relation_type | request_no, relation_type, relation UUID ASC |
| `/candidates` | Scalar release/software/customer/project metadata, full actual-release deployment/batch counts, newest frozen Snapshot/current judgment UUID/decision | created_at DESC NULLS LAST, release UUID DESC |
| `/assessments` | Complete formal judgment UUID/release/Snapshot/decision/reason/evidence/reviewer/time and optional display metadata | created_at, judgment UUID DESC |
| `/impact/{release_id}/summary` | Exact candidate release, selected frozen Snapshot metadata/hash, newest judgment, distinct component_count and verification_count | One exact context |
| `/impact/{release_id}/components` | Distinct frozen component code/normalized version | code, version ASC |
| `/impact/{release_id}/verification` | Issue-linked item UUID/number/title and latest exact execution_no/result/actual_result/executed_at | item_no, item UUID ASC |

All pages require issue_id UUID; limit 1..100 default 50, offset 0..100000 default 0.
Envelope issue_id, issue_no, total, limit, offset, next_offset, items. Impact pages
also require snapshot_id UUID or none and return release_id/snapshot_id pins. Impact
summary accepts optional snapshot_id UUID/none; omitted selects newest FROZEN number.
Wrong/non-frozen/sibling Snapshot or stale none returns 409. Historical frozen pins
survive newer freezes. Missing release 404; release outside linked SCR software 409.
Exact impact scope preserves software membership even when product display metadata
is absent; the candidate directory retains the legacy product visibility rule.

No customer/project ownership or shared version string infers impact. Multiple SCR
relation types remain; Issue-linked verification items may be in different plans,
matching the prior evidence API. Missing DVP references are excluded. History keeps
formal records with null display metadata instead of discarding/crashing. Component
projection includes no storage references. Latest judgments are current observations
for the selected Snapshot and can change independently of page requests. Legacy APIs
and write contracts remain; no write grant is implied.

Frontend query: issue_limit, changes_offset, candidates_offset, assessments_offset,
components_offset, verification_offset; impact context additionally snapshot_id.
First/next preserve unrelated cursors and exact selected Snapshot; invalid repeated
values remain invalid. Recorded judgment links use their stored release/Snapshot UUIDs.


## Organization scalar views — API 0.18.19

Prefix `/api/v1/organization-views`. All new routes are GET.

| Path | Result / specific filters |
| --- | --- |
| `/suppliers` | Scalar supplier rows + complete software_count; country exact |
| `/customers` | Scalar customer rows + project_count/released_project_count; region enum or UNASSIGNED/null |
| `/projects` | Scalar project/customer/latest release rows + site_count; customer_id UUID exact |
| `/{kind}/{identifier}/summary` | Scalar parent metadata/full counts; no query fields accepted |
| `/{kind}/{identifier}/items` | Supplier software, customer projects/current release or project sites; required organization_id UUID |

Catalog shared fields: q (max 200, literal contains in code/name), status (max 30,
exact), limit 1..100/default 50, offset 0..100000/default 0. Country max 100.
Region APAC/EUROPE/AMERICAS/OTHER/UNASSIGNED; blank means no filter. Only region
UNASSIGNED selects null: supplier country text UNASSIGNED remains literal.
Unknown/wrong-kind fields or invalid pagination/UUID return 422. Kind must be
suppliers/customers/projects; unknown parent kind/missing parent returns 404.
Supplier/customer identifier is exact business code. Project identifier is UUID
with precedence, or exact code (LIMIT 2); ambiguous code 409. Page organization_id
must match resolved parent or 404. Envelope kind, total, limit, offset,
next_offset, items; owned pages also organization_id. Stable code/UUID ascending.

No child arrays or long supplier description in directories. Summary retains
supplier website/description. Owned software/project rows include exact latest
release UUID/version (project also status); site rows include exact site UUID.
Latest scope/order and count semantics are recorded in HANDOFF. Complete counts
remain on beyond-end pages; a failed child does not substitute zero parent counts.
Frontend uses limit/offset, retains valid filters and sends repeated values as
invalid. These pins select live identity, not authorization or frozen evidence.
At API 0.18.19 the legacy organization APIs remained compatible. API 0.18.21 retires the six supplier/customer/project GET routes (see below); bounded release-matrix remains available.


## Manufacturing scalar views — API 0.18.20

All GET; prefix `/api/v1/manufacturing-views/sites`.

| Path suffix | Result / query |
| --- | --- |
| empty | Bounded site rows, full total and scalar line/deployed/stored MATCH/attention counts; q/status/region/customer_id/project_id/limit/offset |
| `/{identifier}/summary` | Exact scalar site metadata/full counts and legacy first-line/recorded-batch context; no query fields |
| `/{identifier}/lines` | Flattened owned lines and latest deployment/release/Snapshot/authorization metadata; required site_id UUID, limit/offset |

q max 200 literal code/name contains; status max 30 and region max 100 exact;
customer_id/project_id exact UUID. Limit 1..100/default 50; offset 0..100000/default 0.
Unknown/invalid fields 422. Exact UUID or code resolution LIMIT 2; collision 409,
missing 404; encoded code path separators supported. Required site_id mismatch 404.
Envelope kind, total, limit, offset, next_offset, items; lines add site_id/site_code.
Site name/UUID and line name/UUID ascending; repeated numeric frontend values fail.
Latest per line is created_at DESC NULLS LAST/id DESC. Counts preserve stored states;
summary ordering and batch non-active semantics are detailed in HANDOFF. Raw stored
UUIDs survive optional metadata loss. No nested batch/changeover arrays are returned.
These are mutable reads, not authorization or frozen evidence. Legacy manufacturing
APIs remain compatible; endpoint retirement/bounds remain a separate acceptance task.

## Reviewed compatibility retirement — API 0.18.21

The six legacy organization GET catalog/profile routes and two manufacturing site
GET catalog/profile routes return HTTP 410 `legacy_read_retired`. Response includes
encoded `replacements`, `required_collection_pin` and migration instructions; Link
rel=successor-version points to the first successor. Summary-first child reads use
its UUID as organization_id/site_id. No DB read or rich serializer runs. Unknown
parents and malformed legacy query fields also return 410, not existence results.
This is an intentional compatibility break, not a redirect or partial old response.

See docs/compatibility-read-retirement.md for the exact eight paths/caller review.
Release matrix, bounded views, shared helper functions and all 14 commands remain.
Other retained compatibility families are not retired by this change. No migration,
identity/grant or public-write change; public staging remains sample-only/read-only.

## Production/distribution compatibility retirement — API 0.18.22

Eleven additional reviewed GET routes return 410 `legacy_read_retired`; cumulative
tombstones total 19. Exact paths and repository caller evidence are in
docs/compatibility-read-retirement.md. Rich delivery/distribution/authorization
reads migrate to exact profiles plus bounded children. The unrevisioned delivery
read points to the bounded catalog for explicit package/revision/UUID selection; q
is a substring search, and no latest revision is silently substituted.

Deployment rich detail/provenance migrate to the exact profile. History catalogs
use its deployment UUID; decision history uses BOTH delivered release UUID and
Snapshot UUID from provenance.delivery, never current actual software. Missing
delivery does not infer decision scope. Invalid old queries/revisions or nonexistent
parents return retirement 410 without DB work. Successor endpoint validation is
unchanged. Exact Batch remains. All 14 POST commands sharing these paths remain.
No schema, provider, identity/grant or public-write change.

## SCR/Issue compatibility retirement — API 0.18.23

Eight legacy SCR/Issue GETs return 410 `legacy_read_retired`, bringing the reviewed
total to 27. Exact paths and caller review are in compatibility-read-retirement.md.
Response successor paths and instructions require summary-first change_id/issue_id
pins, independent pages and complete counts. Historical coverage selection carries
release_id plus snapshot_no/snapshot_id; exact impact selection carries snapshot_id
and preserves recorded judgment/frozen execution scope. None sentinels remain.
No query forwarding, redirects, latest substitutes or silent evidence truncation.

Retirement performs no DB read or old UUID/query validation. The old truncated
assessment head is replaced by the navigable bounded history. Internal helpers,
all bounded successors and all 14 commands are retained. No migration or public
write change; sample staging remains read-only.
