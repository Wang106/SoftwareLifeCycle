# Write contract inventory

This is the reviewed baseline for every non-read FastAPI route. The executable source is `backend/app/write_contracts.py`; `backend/tests/test_write_contracts.py` fails when a write route is added, removed or renamed without updating that inventory.

This inventory is backed by runtime guards. Every current write route has `authentication=OIDC_WHEN_ENABLED` and `authorization=SCOPED_WHEN_OIDC`. When OIDC is enabled, a valid active principal must also hold the exact active role resolved through stored software/project relationships, unless it has the exceptional `PLATFORM_ADMIN` override. Routes with atomic audit append use `actor_binding=AUTHENTICATED_WHEN_OIDC`; unaudited snapshot/production commands explicitly use `NO_ACTOR_SINK`. The public sample service still keeps `READ_ONLY_MODE=true` because no approved provider is configured and audit coverage is incomplete.

The enforced scoped roles are recorded in the executable contracts and defined in `SECURITY.md`: snapshot creation uses software-maintainer/project-contributor scope; review actions use reviewer; release decisions use release authority; delivery/distribution use distribution authority; production authorization uses production authority; deployment/changeover/batch use production operator. `PLATFORM_ADMIN` is the only scope-free override.

| Route | Scope | Actor | Audit | Retry | Concurrency | Main gap |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/v1/releases/{release_id}/create-snapshot` | Release | None | None | None | None | No actor/audit; concurrent numbering is not serialized |
| `POST /api/v1/approvals/{approval_no}/actions` | Approval target/step | Authenticated; declaration retained | Atomic append | None | None | Step transition not locked |
| `POST /api/v1/approvals/{approval_no}/release-decision` | Approved release/snapshot | Authenticated; declaration retained | Atomic append | None | None | Approval not locked |
| `POST /api/v1/deliveries` | Release/snapshot/recipient/artifacts | Authenticated; optional declaration retained | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/distributions` | Package/recipient | Authenticated | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/authorizations` | Distribution/customer/project/site/line | Authenticated | Atomic append | Duplicate rejection | None | No idempotency key |
| `POST /api/v1/deployments` | Authorization/line | None | None | Duplicate rejection | None | No actor/audit/locking |
| `POST /api/v1/deployments/{deployment_no}/actual` | Deployment/release/snapshot | None | None | Mutable overwrite | None | No audit or optimistic lock |
| `POST /api/v1/deployments/{deployment_no}/changeovers` | Deployment/releases | None | None | Duplicate rejection | None | No actor/audit/locking |
| `POST /api/v1/deployments/{deployment_no}/batches` | Deployment/authorization/changeover | None | None | Duplicate rejection | None | Batch-limit race; no actor/audit |
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

Before a new write route can merge, its contract must state scope, actor source/binding, authentication, authorization, audit, idempotency and concurrency behavior and invoke a runtime authorization guard. Audited routes must resolve a trusted actor. Before any route can be exposed beyond controlled local development, configure an approved OIDC provider, close remaining audit gaps and complete provider-backed positive/negative integration tests.
