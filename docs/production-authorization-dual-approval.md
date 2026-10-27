# Production authorization: explicit dual-person approval

## Scope and business policy

This backend package closes the existing application gap between creation of a
`SoftwareAuthorization` in `DRAFT` and the `APPROVED` precondition for new deployments
and production batches. The selected policy is dual-person separation: the trusted
creator cannot approve the same authorization. A different currently authenticated
USER with an ACTIVE `PRODUCTION_AUTHORITY` membership in the exact project must
approve explicitly. Platform administrator status alone grants no exception.

No identities, memberships, provider settings or production data are changed by this
package. OIDC remains disabled and public/demo writes remain read-only by default.
The browser workbench is a subsequent package; this is not a production activation,
company installation, physical flashing confirmation or formal release.

## Bounded command and review context

The private context and approval paths are `/api/v1/authorizations/{authorization_no}/approval-context`
and `/api/v1/authorizations/{authorization_no}/approval`. Context is a fixed target
read, not an authorization catalog. Responses, redirects and rejected requests use
private/no-store metadata. Required authentication has no legacy anonymous fallback.

The approval request contains an independent request UUID, the expected versioned
context digest and a reason. There is no arbitrary status setter, automatic approval,
change to the authorization scope or implicit multi-level workflow. Context freezes
the authorization identity and scope, release/snapshot/effective decision, package
revision/distribution, recipient project/customer, site/line/purpose/limit/restriction,
and trusted creation evidence. A digest is a concurrency condition, not permission.
The service derives it from locked canonical records, not caller declarations.

## Provenance, current authority and atomicity

Creator evidence must be the exact existing `EVT-PA-{authorization UUID hex}` creation
audit with authenticated actor provenance, correct event/action/entity/reference and
matching original business facts. Names, legacy declarations, missing or mismatched
creation events cannot establish a creator. Such DRAFT records are rejected by this
new approval path; history is never rewritten to fabricate provenance.

Current principal, optional claimed browser session and exact project membership
are rechecked before attempts and idempotent replay. The existing administrative
transaction gate and actor/membership locks serialize status changes; business locks
follow release, package, distribution, authorization order. Upstream revocation and
current frozen release evidence remain authoritative.

Only one DRAFT-to-APPROVED transition may occur under the target row lock. Approval
status/time and immutable audit evidence commit together. Unique approval audit
numbers bind the independent request UUID to the original actor, target, expected
context and reason; collisions do not adopt another actor's request. Recovery/replay
returns the original approved receipt, not an inference from current mutable status.
A historical receipt does not prove that the authorization remains usable after
subsequent revocation or that deployment occurred.

No new table or migration is needed for this bounded command: the existing target
row lock/state transition and unique append-only audit event provide its invariant.
It does not protect against an authorized database operator deliberately rewriting
application tables outside the application protocol.

## Historical compatibility boundary

Existing seeded/imported `APPROVED` records retain their previous read/runtime
semantics. They are not relabeled as dual-person approved, backfilled with invented
approvers or silently invalidated. Migrating all legacy approvals into a new business
reapproval policy is a separate decision. Unknown-creator DRAFT is not approved by
this command. Existing ordinary creation/production behavior and tests remain intact.

The new approval is counted separately from the fourteen ordinary business commands,
existing correction/revocation commands, two self-session controls, six administrator
controls and offline operator commands. Its strict `OIDC_REQUIRED` contract has its
own exhaustive route inventory; existing route accounting remains enforced.

## Verification and remaining acceptance

Required synthetic coverage: missing/disabled identity, SERVICE, administrator-only,
wrong project or role, self-approval, unknown legacy creator, stale context, malformed
request, request-key/body/actor collisions, revoked session/membership before replay,
original-result semantics, audit failure rollback, concurrent approval and revocation,
and current-role locking. Real PostgreSQL checks are required in exact-head CI.

This document is an implementation contract, not a test-pass receipt. Final test,
review, commit/PR and fresh main/provider evidence belongs in the handoff and PR
closure. Overall acceptance remains36/44=82% until actual milestone criteria pass.
P2 browser confirmation/recovery and real provider/multiuser acceptance remain pending;
no new deployment or operational configuration is authorized by this code.

### Local verification checkpoint

Final frozen-source full local backend:1932 passed,26 subtests passed,748 skips due
to unavailable local test facilities (including PostgreSQL); no failures. These skips
are NOT acceptance: the existing precise-head CI must execute all required tests with
zero skips. New approval53 cases pass locally;11 real PostgreSQL cases collected only.
Focused approval+contract61 pass0skip; independent approval plus modified inventory/
compatibility regression171 pass with1 existing PostgreSQL skip.52 automation checks,
progress validator and diff checks pass. No frontend source changes; full frontend and
production build remain mandatory in fresh CI. No real identity/business operations.

Repairs preserve original assertions: verify exact present creation request and add
locked FROZEN snapshot/release check; accept existing READY/APPROVED package states
rather than unintentionally narrowing established distribution eligibility.
