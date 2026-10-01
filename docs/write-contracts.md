# Write contract inventory

This is the reviewed baseline for every non-read FastAPI route. The executable source is `backend/app/write_contracts.py`; `backend/tests/test_write_contracts.py` fails when a write route is added, removed or renamed without updating that inventory.

This inventory is descriptive, not an access-control implementation. Every current write route has `authentication=NONE` and `authorization=NONE`. The public sample service must therefore keep `READ_ONLY_MODE=true`.

The intended scoped roles are recorded in the executable contracts and defined in `SECURITY.md`: snapshot creation uses software-maintainer/project-contributor scope; review actions use reviewer; release decisions use release authority; delivery/distribution use distribution authority; production authorization uses production authority; deployment/changeover/batch use production operator. `PLATFORM_ADMIN` is a future exceptional override. None of these roles is enforced yet.

| Route | Scope | Actor | Audit | Retry | Concurrency | Main gap |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/v1/releases/{release_id}/create-snapshot` | Release | None | None | None | None | No actor/audit; concurrent numbering is not serialized |
| `POST /api/v1/approvals/{approval_no}/actions` | Approval target/step | Declared | Atomic append | None | None | Actor untrusted; step transition not locked |
| `POST /api/v1/approvals/{approval_no}/release-decision` | Approved release/snapshot | Declared | Atomic append | None | None | Actor untrusted; approval not locked |
| `POST /api/v1/deliveries` | Release/snapshot/recipient/artifacts | Optional declared | Atomic append | Duplicate rejection | None | Actor optional; no idempotency key |
| `POST /api/v1/distributions` | Package/recipient | None | Atomic append | Duplicate rejection | None | Audit actor unavailable |
| `POST /api/v1/authorizations` | Distribution/customer/project/site/line | None | Atomic append | Duplicate rejection | None | No authenticated authority |
| `POST /api/v1/deployments` | Authorization/line | None | None | Duplicate rejection | None | No actor/audit/locking |
| `POST /api/v1/deployments/{deployment_no}/actual` | Deployment/release/snapshot | None | None | Mutable overwrite | None | No audit or optimistic lock |
| `POST /api/v1/deployments/{deployment_no}/changeovers` | Deployment/releases | None | None | Duplicate rejection | None | No actor/audit/locking |
| `POST /api/v1/deployments/{deployment_no}/batches` | Deployment/authorization/changeover | None | None | Duplicate rejection | None | Batch-limit race; no actor/audit |
| `POST /api/v1/issues/{issue_no}/impact-assessments` | Issue/release/snapshot | Declared | Atomic append | Request ID | Issue row lock | No authenticated/project-authorized actor |
| `POST /api/v1/changes/{request_no}/acceptance-dvp-links` | SCR/criterion/DVP | Declared | Atomic append | Request ID | SCR row lock | No authenticated/project-authorized actor |
| `POST /api/v1/testing/releases` | Release/snapshot | Declared | Atomic append | Request ID | Release row lock | No authenticated/project-authorized actor |
| `POST /api/v1/resources` | Referenced entity | Declared | Atomic append | Request ID | Target row lock | Location/access not verified |

## Terms

- **Declared actor** means request text. It is not a verified user identity.
- **Atomic append** means the domain record and audit event share one database transaction.
- **Request ID** means identical retries return the existing result while conflicting reuse is rejected.
- **Row lock** describes the current PostgreSQL serialization target; SQLite tests do not simulate concurrent PostgreSQL sessions.
- **Duplicate rejection** is not idempotency: a retry receives a conflict rather than the original result.

## Review rule

Before a new write route can merge, its contract must state scope, actor source, authentication, authorization, audit, idempotency and concurrency behavior. Before any route can be exposed beyond controlled local development, replace `NONE` authentication/authorization with enforced policy and add positive and negative integration tests.
