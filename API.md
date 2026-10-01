# API

Base path: `/api/v1` except health endpoints. Interactive OpenAPI documentation is served at `/docs` when FastAPI is running. Application version is `0.9.0`.

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
- There is no implemented authentication or project authorization. Actor names are unverified declarations.
- The provider-neutral principal and scoped-role schema in `SECURITY.md` is a design/enforcement foundation; it does not authenticate a request by itself.
- Issue impact and acceptance-link writes use client-generated request IDs for retry handling; other commands do not all provide the same idempotency guarantee.
- Current approval/release-decision and delivery/distribution/authorization service writes record audit events in the same transaction.
- Snapshot and exact UUID bindings take precedence over matching version, name or display code.
- Bounded catalogs validate filters, limit and offset; totals/counts apply to the full filtered result, not just the visible page.
- Storage references are intentionally omitted from selected public evidence responses.

## Error conventions visible in current APIs

- `403` — read-only guard blocks a write.
- `404` — exact business record does not exist.
- `409` — conflicting state, ambiguous legacy identifier or incompatible release/snapshot scope.
- `422` — validation failure, unsupported filter or invalid bound.

When an endpoint changes, update its tests and this map. Generated `/docs` remains authoritative for request/response field shapes.
