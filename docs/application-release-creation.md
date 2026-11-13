# Application release draft creation

This package adds one separate, controlled application-release creation operation.
It does not change the original fourteen-command workspace or its acceptance
denominator. Public production and Preview remain sample-only and read-only.
The implementation and validation status is recorded in the newest HANDOFF entry;
this contract alone is not evidence of successful execution or deployment.

## Bounded outcome

The operation creates an empty `APPLICATION` release with original status `DRAFT`
and one matching `ApplicationReleaseDetail`. It derives the customer from the
selected project and the software product from one exact `STANDARD` release UUID.
Names, matching version strings and the latest catalogue entry cannot select a
different baseline. Client inputs cannot set the customer, product, actor, release
type, status, approval, snapshot, component or artifact.

The selected standard release may be not yet formally released. A recorded
revocation still prevents a new association. The context and receipt preserve its
recorded version and status. `Release.status` is a record observation, not proof
of a current approved snapshot or effective formal release decision. Creating a
draft never grants delivery, distribution, deployment or production permission.

No components, binaries, storage references, distribution policies, snapshots or
approval records are copied or created. An empty draft cannot pass the existing
snapshot service's artifact requirement. Previous-application relationships,
component editing and binary upload remain separate work.

## Exact context and request

Routes:

- `GET /api/v1/application-release-creation/context?project_id=...&standard_base_release_id=...`
- `POST /api/v1/releases/application`
- `GET /api/v1/application-release-creation/receipts/{request_id}`

The private context endpoint accepts one project UUID and one standard-release
UUID. It returns only that authorized pair and its derived customer/product
identity; it is not a global customer, project or software selector. The context
digest binds the reviewed parent facts. A fresh submission must still match that
context under the transaction's locks.

The create request contains a mandatory request UUID, project UUID, standard
release UUID, version, nullable release notes, reason and expected context digest.
Extra fields are rejected. Version and reason have explicit nonblank length and
text validation; release notes preserve their accepted text. Client and server
normalization must agree. The client never generates a second request UUID to
silently recover an uncertain first attempt.

The version is at most 100 characters and reason/release notes at most 4000.
Canonical version and reason have no outer whitespace. Version rejects control
characters; reason and notes may contain LF and TAB but no other control characters.
Unpaired Unicode surrogates and nil UUIDs are rejected. No case-folding or semantic
version normalization rewrites the identity.

The existing customer-scope model and migration `0024_release_customer_scope`
remain unchanged. Each new release records a non-null customer scope and its
matching detail in the same transaction. The existing unique key is software,
release type, version and customer, not project. Thus different customers may
reuse a version, while two projects of one customer may not create the same
software/version pair. A legacy null-scope application with matching stored
customer/software/version also conflicts. Historical records are not backfilled,
adopted or overwritten.

## Independent identity and authorization

This new operation requires OIDC and an active human principal. It does not
inherit legacy auth-disabled write compatibility. Both an exact active project
`CONTRIBUTOR` grant and an exact standard-product `SOFTWARE_VIEWER` or
`SOFTWARE_MAINTAINER` grant are required. `PLATFORM_ADMIN` alone is not a bypass
for this new operation. Existing routes keep their own existing policies.

The service rechecks identity, any supplied browser session and both role scopes
inside the transaction. Administrative revocation and creation share the existing
administrative transaction gate. Parent locks and refreshed reads protect the
exact relationships and revocation check. The baseline's recorded status alone
cannot establish that its chain is not revoked.

The public read-only guard takes precedence for new business writes. No identities,
grants, credentials, provider settings or production write flags are provisioned
by this feature. The new operation has its own reviewed route contract; adding
it must preserve exhaustive coverage of every existing registered write route.

## Atomic creation and original evidence

The request UUID identifies the new release. An independent `EVT-ASR-` audit
namespace records the canonical request, resolved context, trusted principal and
original creation receipt. Release, detail and audit commit together. Validation,
constraint, audit and commit failures roll back all new rows and release locks.

A new request returns HTTP 201. A matching original request from the same currently
authorized actor returns HTTP 200 with its original immutable receipt and creates
no additional rows or events. Different content, another actor, a legacy domain
UUID or inconsistent evidence returns a conflict. Historical successful recovery
does not re-run new-work eligibility checks, but always checks current identity,
session and scope. A later record status does not change the original `DRAFT`
receipt.

The dedicated receipt endpoint reads authenticated original evidence only. A
missing receipt or lost response does not prove that the write did not commit.
Recovery never repeats the POST. Current domain records and pasted JSON are not
substitutes for the original audit.

New ASR creation events are excluded from the existing public activity, audit
catalogue, search and dashboard-event surfaces, including exact event reads. This
prevents those older public routes from bypassing the new private receipt rule.
Existing non-ASR events retain their original behavior. General release catalogue
and profile visibility is pre-existing; this bounded exclusion is not a general
company-data read authorization rollout.

## Browser boundary

The new bilingual form is reachable directly from Create. Users can edit the
draft fields when submission is unavailable. An independently default-disabled
server-side capability binds the approved application origin and API base before
any authenticated context, submit or recovery proxy is used. Browser requests use
fixed same-origin routes; clients cannot supply an upstream URL, credentials or
headers. Request/response sizes, media types and result shapes are bounded and
checked. Private responses use no-store headers.

The independent configuration keys are `APPLICATION_RELEASE_CREATION_MODE`,
`APPLICATION_RELEASE_CREATION_APPROVED_API_BASE_URL` and
`APPLICATION_RELEASE_CREATION_APPROVED_APP_ORIGIN`. They are not enabled in this
package or inherited from another command's gate.

Review binds the exact context and fields. Changes invalidate unsent confirmation.
After an attempt, the original request is retained for receipt recovery, including
an unknown result. Repeated clicks cannot cause parallel submissions. No automatic
browser persistence, token export or hidden resubmission is permitted. Imported
recovery material, if offered, is inert until an explicit original-receipt query.

The standard baseline's record status is displayed. A baseline not marked
`RELEASED` has an explicit warning, while a `RELEASED` label still does not certify
formal approval or delivery authority. Upload is not implemented, and resource
references are not file storage.

## Validation and remaining acceptance

Meaningful regression-first tests must fail on the unchanged baseline before
implementation. Backend coverage includes binding and authorization denials,
non-released/revoked baselines, scoped and legacy uniqueness, retry conflicts,
immutable receipt checks and atomic rollback. Independent-session PostgreSQL
tests run only within the existing normal CI's disposable migrated database and
cover lock ordering, concurrent requests, duplicate versions, revocation and
deferred constraints. SQLite results do not prove PostgreSQL behavior.

Browser coverage includes Chinese/English, input and context changes, confirmation,
repeated entry/clicks, Cancel, Back/Forward, disabled capabilities, rejected sessions,
unknown results and original receipt recovery. The existing read-only browser
journey must remain unable to send mutations or contact external destinations.
Its strict signed-browser, sandbox, report and aggregate gates are retained.

The complete backend suite, migration round trip, frontend suite, production
Next.js/OpenNext build and existing normal CI gates remain required for the exact
published head. Targeted checks are not a complete pass. Real OIDC, live database,
approved-provider multi-user/browser acceptance and company deployment remain
separate requirements. No roadmap percentage rises solely because this code exists.

## Follow-on upload scope

Binary upload requires a separately agreed storage destination, file permissions,
size/type/integrity checks, temporary-to-final commit behavior, incomplete-upload
cleanup, failure recovery and authorized download/distribution rules. This package
does not select or purchase storage, transmit a file or pretend a local browser
cache is a saved application release.
