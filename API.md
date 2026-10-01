# API

Base path: `/api/v1` except health endpoints. Interactive OpenAPI documentation is served at `/docs` when FastAPI is running. Application version is `0.15.0`.

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
| Production | `/api/v1/production/catalog/{kind}`, `/deployments/{deployment_no}/provenance`, `/batches/{batch_no}` | `{kind}` is deployments, changeovers or batches |
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
- Snapshot, production-batch creation, approval actions and release decisions now accept optional client-generated request IDs, in addition to the existing request-ID commands. Other commands still have incomplete retry protection.
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
