# API

Base path: `/api/v1` except health endpoints. Interactive OpenAPI documentation is served at `/docs` when FastAPI is running. Application version is `0.18.3`.

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
| Organizations | `/api/v1/organizations/suppliers`, `/customers`, `/projects`, `/release-matrix` | Project detail uses UUID when codes may be ambiguous |
| Releases | `/api/v1/releases`, `/releases/standard`, `/releases/application`, `/releases/application/id/{release_id}` | Exact-ID application profiles are preferred over version-only compatibility routes |
| Snapshot evidence | `/api/v1/releases/{release_id}/snapshots`, `/api/v1/snapshots/{snapshot_no}`, `/compare/{target_no}` | Frozen manifest/history and metadata comparison |
| Change/Issue | `/api/v1/changes`, `/changes/{request_no}`, `/changes/{request_no}/coverage`, `/issues/{issue_no}/impact` | Coverage and impact remain release/snapshot scoped |
| Testing | `/api/v1/testing/dvp/catalog`, `/testing/dvp/id/{item_id}/profile`, `/testing/releases` | Bounded DVP directory plus test-release records |
| Governance | `/api/v1/governance/approvals`, `/decisions`, exact profiles/actions | Preferred bounded governance history |
| Distribution | `/api/v1/distribution/catalog/deliveries`, `/distributions`, `/authorizations` | Preferred bounded catalogs; exact delivery revision is significant |
| Production | `/api/v1/production/catalog/{kind}`, `/deployments/{deployment_no}/profile`, `/batches/{batch_no}` | `{kind}` is deployments, changeovers or batches |
| Audit/resources | `/api/v1/audit/events`, `/activity/{event_no}`, `/resources` | Bounded audit review and append-only external references |

Older unbounded list/detail routes such as `/api/v1/deliveries`, `/distributions`, `/authorizations`, `/deployments`, `/batches`, `/approvals` and `/activity` remain for compatibility. New directory consumers should prefer bounded catalog endpoints.

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
Recorded evidence/identifiers stay original. See [interface contract](docs/i18n.md).
API 0.18.3 and schema 0017_deployment_actual_version are unchanged; no migration.
Public staging remains read-only. Authenticated submission and OIDC configuration are
still pending. Roadmap checked scope stays 34/44 (77%); bilingual coverage is an
additional UI requirement, not completion of the Phase 6 submission gate.

Verification: frontend 292 passed (78 localization/coverage checks plus 214 command
checks); final Next/OpenNext production build passed. Full backend: 733 passed,
3568 existing warnings, no skips, including 103 real PostgreSQL integration/concurrency
tests. Local SSR: 126 page/language checks, invalid preference fallback and stable raw
input/option values for 14 forms. Live verification is recorded after deployment.
