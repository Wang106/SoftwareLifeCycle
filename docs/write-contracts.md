# Write contract inventory

This is the reviewed baseline for every non-read FastAPI route. The executable source is `backend/app/write_contracts.py`; `backend/tests/test_write_contracts.py` fails when a write route is added, removed or renamed without updating that inventory.

This inventory is backed by runtime guards. Every current write route has `authentication=OIDC_WHEN_ENABLED`, `authorization=SCOPED_WHEN_OIDC`, `audit=ATOMIC_APPEND` and `actor_binding=AUTHENTICATED_WHEN_OIDC`. When OIDC is enabled, a valid active principal must also hold the exact active role resolved through stored software/project relationships, unless it has the exceptional `PLATFORM_ADMIN` override. The public sample service still keeps `READ_ONLY_MODE=true` because no approved provider is configured and retry/concurrency safeguards are incomplete.

The enforced scoped roles are recorded in the executable contracts and defined in `SECURITY.md`: snapshot creation uses software-maintainer/project-contributor scope; review actions use reviewer; release decisions use release authority; delivery/distribution use distribution authority; production authorization uses production authority; deployment/changeover/batch use production operator. `PLATFORM_ADMIN` is the only scope-free override.

| Route | Scope | Actor | Audit | Retry | Concurrency | Main gap |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/v1/releases/{release_id}/create-snapshot` | Release | Authenticated | Atomic append | Optional request ID | Release row lock | No-key legacy calls create a new snapshot |
| `POST /api/v1/approvals/{approval_no}/actions` | Approval target/step | Authenticated; declaration retained | Atomic append | Optional request ID + expected step | ApprovalRequest and step row locks | Unkeyed callers act on current step |
| `POST /api/v1/approvals/{approval_no}/release-decision` | Approved release/snapshot | Authenticated; declaration retained | Atomic append | Optional request ID | ApprovalRequest row lock | Distinct decision numbers retain history semantics |
| `POST /api/v1/deliveries` | Release/snapshot/recipient/artifacts | Authenticated; optional declaration retained | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/distributions` | Package/recipient | Authenticated | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/authorizations` | Distribution/customer/project/site/line | Authenticated | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/deployments` | Authorization/line | Authenticated | Atomic append | Duplicate rejection | None | Scope rows are not locked |
| `POST /api/v1/deployments/{deployment_no}/actual` | Deployment/release/snapshot | Authenticated | Atomic append | Mutable overwrite | None | No optimistic lock |
| `POST /api/v1/deployments/{deployment_no}/changeovers` | Deployment/releases | Authenticated | Atomic append | Duplicate rejection | None | Deployment row is not locked |
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

Request-ID and row-lock contracts now cover 8/14 routes (57%); scope/actor/atomic
audit contracts cover 14/14 (100%). These counts describe reviewed route contracts,
not provider configuration, production readiness or completion of broad Phase 6 items.
