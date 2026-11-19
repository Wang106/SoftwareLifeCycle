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

## Authorized SSR selection

The optional selector reads `GET /api/v1/application-release-creation/standard-options`
through the same-origin POST `/auth/application-release-options` proxy. It uses the
existing creation switch and approved API/origin binding; disabled configuration
makes no network request. A project UUID remains an explicit input; this is not a
project selector or a global software catalog.

Every page rechecks the authenticated USER/browser session, active project
CONTRIBUTOR membership, active project/customer and active software visibility
(VIEWER or MAINTAINER). Only active software's STANDARD releases with details and
without recorded revocation are candidates. DRAFT/READY and other non-REVOKED
statuses remain eligible: the existing non-RELEASED warning and draft-only rule
are unchanged. Rows show exact SSR UUID, software identity/name, version and status.

Queries have only project_id, limit (default25, maximum50), and optional after.
Duplicate/unknown fields, noncanonical/nil UUIDs, invalid limits and cursors absent
from the currently authorized candidate set are rejected. IDs sort ascending;
next_after is the last returned ID only when a further candidate exists. Each page
is private/no-store; the proxy bounds UTF-8 JSON to32KiB and rejects wrong-project,
extra-field, unordered, duplicate or malformed rows. Selection is not authority:
creation still obtains a fresh exact-pair context/digest and explicit confirmation.

Selection fills only the exact baseline ID. Project changes clear baseline/options,
preview and confirmation. Route changes clear editable selection; locked original
requests and recovery bytes stay intact. Generation checks discard late pages and
old Load/Next/Select callbacks. Pending or uncertain submission and permanently
read-only imported recovery cannot load/select a replacement or resubmit. No
background catalog fetch, auto-selection, draft creation or grant configuration
is introduced.

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


## Confirmation and recovery capability repair

A prepared command may be created only while its current preview generation and
current confirmation still match. Edits, navigation, cancellation and unchecking
invalidate old submit callbacks; a newly confirmed preview cannot reauthorize an
older callback. Recovery text edits have their own revision so an old Restore
callback cannot import a different request from the text currently displayed.
Restore is rejected while preparation/submission is active or a request is already
locked. Import creates a recovery-only controller with creation permanently closed,
including before the first receipt lookup and after failed/disabled lookups.
Normal new requests retain their single-attempt creation and original receipt
contract. These frontend guards do not replace API authentication or authorization.

The recorded repair was recovered onto main7f6af929 after the independent Next16.4.5
security patch. The four affected source/test files had no baseline changes;
component, controller and controller-test blobs match the earlier reviewed source.
UI regression statements were recovered from literal review excerpts; full prior
file byte identity is not claimed. Fresh tests reproduced the original7 failures
before repair, then194 related and2398 full frontend tests passed with no skips.
Next/OpenNext production builds and configuration/disabled-auth checks passed.
Exact-head strict CI is separately required; synthetic checks are not real identity
or business acceptance. No API, database, dependency, permission or gate changed.
Historical e2038a94/schema0030 images and the16.4.2 probe remain unchanged and are
not covered by the source/build security patch. Any future runtime media requires
actual source/version/patch verification; current-ref image compatibility is unproven.


### Supplemental generation scheduling regression

A generation ref change must schedule a state update when refreshed callbacks are
required. Resetting an already-null preview and already-false confirmation can be
React same-value no-ops. The shared invalidation path therefore advances both the
ref and a distinct state revision. It retains immediate stale-handler rejection
while ensuring mount/navigation and repeated invalid imports allow subsequent input.
The synthetic harness now models Object.is bailouts and state-driven rerenders,
without an unconditional second mount/navigation render. Three actual-input cases
failed on the previous PR head, then passed after this correction;197 affected and
2401 full frontend tests and Next/OpenNext production builds passed. Prior head
success is not evidence for this correction; new exact-head CI remains required.
