# Production authorization approval workbench (P2)

## Bounded capability

The bilingual workbench at `/distribution/authorizations/{authorizationNo}/approve`
uses the private P1 review context, never the public sample profile as authority.
It explicitly loads the exact target, presents all seventeen frozen scope/provenance
facts and the versioned digest, prepares an independent request UUID and reason,
requires confirmation, and sends only that frozen approval body. Creating DRAFT
records, changing scope, assigning roles and production deployment remain separate.
A second current same-project PRODUCTION_AUTHORITY USER must approve; the creator
and a platform-administrator-only identity have no bypass.

`AUTHORIZATION_APPROVAL_SUBMISSION_MODE=enabled` and exact approved API base/app
origin are necessary frontend opt-ins in addition to the existing browser auth and
backend gates. Defaults are disabled. The offline readonly inventory explicitly
requires the new mode disabled. No actual provider settings, secrets, identities,
permissions, notification channels or company servers are changed by this package.

## Original result, not current approval authority

The new private backend GET
`/api/v1/authorizations/{authorization_no}/approval-receipts/{request_id}` reuses P1's
current USER, browser session, exact project role, non-creator and trusted creation
checks. It reads only the original current-actor audit, validates typed version,
request/context/receipt, canonical digest, target/creator/approver and occurrence
time, and returns the minimal historical receipt. Missing, foreign or malformed
approval events do not prove success. The read rolls back its transaction to release
bounded locks and never invokes the approval POST or writes an audit.

Historical recovery does not require DRAFT or current active upstream business
eligibility: a later revocation or decision replacement does not erase an original
approval. Current identity/session/project-role revocation still denies the read.
P1's conservative current-chain/creation structural matching remains; unsupported
out-of-band edits may make history unavailable, not prove that approval never happened.
An original APPROVED receipt proves neither current eligibility nor deployment,
physical production or formal release. Legacy seeded APPROVED records are not
invented dual-person receipts.

## Frozen transport and recovery

The same-origin frontend proxies accept bounded JSON only; no credentials or reason
are put in URLs. They revalidate the current session, recompute the Python-compatible
version-1 sorted-key UTF-8 context digest, and bind the receipt to the exact actor,
authorization, request UUID, digest, creator and reason. The backend remains the
authority; a digest or frontend capability flag never grants permission.

Unknown outcomes preserve original bytes and request UUID. Explicit retry uses that
same body; there is no automatic retry, context substitution or new key. Stale known
rejection requires a new private preparation. Receipt recovery uses only the strict
GET endpoint, not generic activity or a write replay. A successful POST is followed
by an original receipt check; lost/malformed outcomes remain unknown.

Manual recovery exports a canonical same-site versioned envelope of the confirmed
original command, including unknown attempts. It contains business scope, creator
UUID and reason: handle it privately and locally, do not share it as credentials or
permission. No session cookie, token, issuer configuration or asserted receipt is
exported. Import does no network or storage, generates no identifiers/times, and
exposes only an explicit original-receipt query, never send/retry. A new valid
same-actor session can recover; revoked/foreign sessions or roles cannot. Imported
scope is labeled unverified until the strict server receipt is matched.

Raw context values, identifiers, reasons and timestamps are preserved separately
from translated UI labels. Strict size/schema/Unicode validation fails closed;
malformed and oversized imports are not silently normalized or truncated. Scope
values outside the bounded browser representation remain unavailable, not approved.

## Verification and limits

Synthetic backend tests cover current role/session, exact actor/target, later
revocation, malformed audit, no side effects and real PostgreSQL variants. Frontend
protocol, actual proxy composition, import/recovery, bilingual component rendering,
route/capability changes, confirmation and unknown-state guards are tested. These
are not real-provider/browser/multi-user acceptance. Full exact-head CI, independently
verified artifacts, protected merge and fresh main/provider evidence are required
and recorded in the PR closure, not inferred from local tests.

P1/P2 close one application workflow, not all nondeployment requirements. Overall
36/44=82% remains unchanged until acceptance milestones are actually demonstrated.
Next bounded package follows the finite plan's permission-aware selectors; any new
read policy requires a separate decision rather than inferred access from write roles.

## Local verification checkpoint

Final full local backend:1956 passed+26subtests,766 environment skips,zero failures.
New receipt24 local tests passed and18 PostgreSQL cases await mandatory exact-headCI.
Final frontend1841 passed0skip; new protocol17/proxy14/UI17 synthetic cases, production
build/typecheck, offlinepreflight15+26subtests, automation52+9subtests and progress/diff
validation passed. Local skips are not PostgreSQL acceptance; realbrowser remains unverified.
The new frontend reason validator was corrected to preserve internal newline/tab exactly,
aligning with P1 without changing backend policy or lowering safety checks.
Independent source review:77 backend passed/18 localPG skips and192 frontend+i18n
passed0skip; no scoped blocker. Exact-tree review remains separate from remote CI.
