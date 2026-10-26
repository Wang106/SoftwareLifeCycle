# Production correction target authorization binding

## Confirmed gap and scope

On baseline main `2c1622a40082553202a5d72ada4d7069ce93301b`, both nested correction
routes authorized the URL's deployment number but then invoked service methods that
resolved the child globally by its own business number:

- POST `/api/v1/deployments/{deployment_no}/changeovers/{changeover_no}/correction`
- POST `/api/v1/deployments/{deployment_no}/batches/{batch_no}/correction`

`authorize_deployment` checked the parent authorization's project role. The service
independently loaded the target child and derived its deployment. There was no comparison
between the route's authorized parent and that actual child parent. A principal permitted
only for project A could therefore submit a path naming deployment A with a child belonging
to project B. This was confirmed in two intentional regression tests against the unfixed
baseline: isolated synthetic FastAPI requests returned200 and corrected foreign child facts,
where404 was expected. No public or company write endpoint was used.

Existing service-level correction tests proved history/idempotency behavior but did not
exercise this nested-route mismatch. This package closes that concrete authorization gap,
not a speculative parser edge case or new production feature. It maps R12/R13 and the
remaining correction-E2E/exact-scope acceptance work. Fixed progress percentages remain
unchanged; no real provider/multi-user acceptance is implied.

## Implementation and ordering

After the existing parent authorization succeeds, `_require_correction_target` selects
only the requested child ID joined to its deployment with **both exact business numbers**,
using `FOR UPDATE OF` the child table. This child lock remains held in the same request
transaction through the existing service commit/rollback. Concurrent attribution changes
cannot move the child between the check and service use. The lock order remains child
then deployment, matching the existing correction service.
A missing child or child outside that parent yields the same404 and fixed detail
`production correction target not found`. The query does not first resolve a foreign child
and does not return its metadata. Unauthorized parents retain the existing403 before any
child resolution. Even a global administrator must supply a consistent parent-child route.

Only after this guard succeeds does the route resolve the trusted actor and invoke the
existing service, including its idempotent replay path. A previously used request ID is
not permission to address its target through a different parent. Existing service checks
still reject cross-child request-ID reuse, version/predecessor conflicts and wrong actors.

The helper is read-only. On denial it creates no baseline, correction, domain change or
audit event. Existing `0029` guards freeze recorded facts but do **not** independently freeze the child
`deployment_id`; independent review caught and corrected an initial mistaken assumption.
The scoped row lock provides the check/use protection instead. It does not change lock ordering,
service signatures, request/receipt schemas, migrations, legacy direct-service callers,
identity configuration or public read-only mode. The service remains an internal domain
layer; callers outside HTTP must establish their own authorized context as before.

## Verification

`backend/tests/test_production_correction_scope.py` uses a synthetic principal in an
isolated ASGI app with the actual production router/authorization/service code. Identity
injection is a test fixture, **not** real OIDC/provider acceptance. The suite is parametrized
for SQLite and the existing disposable **migrated PostgreSQL** fixture; no company/public
DB is used. PostgreSQL variants must run in unchanged CI without skips.

For both Changeover and Batch:

1. Foreign-project target through an authorized parent is404, with all physical facts,
   baselines, corrections and audit rows unchanged.
2. A same-project child under a different deployment is still404; an absent target is
   indistinguishable. Service execution is explicitly forbidden on these paths.
3. Unauthorized parent requests are403 before child resolution, whether child exists or not.
4. Correct parent/child succeeds; original-key replay returns the original response with
   one correction and its trusted-principal audit, no extra changes.
5. Suspended project membership denies both new writes and original-key replay.
6. Global administrator can operate on the correct foreign parent, but both new requests
   and existing-key replay through the wrong parent are404 with unchanged evidence.
7. Existing request ID belonging to another child under a valid same-project parent is409
   through the existing service guard, without changes.

Two additional PostgreSQL-only tests hold the exact scoped child lock and prove a competing
child-attribution UPDATE is blocked via `pg_blocking_pids`, then release and roll back both
transactions. They verify real lock behavior without retaining any reassignment.

Local SQLite tests and existing correction regressions provide fast confirmation; fresh
exact-head full CI supplies PostgreSQL evidence. Required checks, protected merge, fresh
main CI and both providers are independently verified and recorded in the PR. Intentional
pre-fix red tests are defect reproduction, not an unexplained failing acceptance gate.

## Boundaries and next work

Public/demo remains read-only; no provider identity, role assignments, credentials, real
business data, scheduler/CI, network, billing or deployment permissions are changed.
The correction UI for Batch/Changeover and its exact revision/head context reads remain a
separate missing user-facing capability; do not enable it before this backend scope binding
is accepted. Real approved-provider desktop/mobile/multi-user correction acceptance remains
external, as do operational target/alert delivery and Docker runtime rehearsal.
