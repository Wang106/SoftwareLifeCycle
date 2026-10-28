# Release-decision replacement manual recovery (P5)

## Bounded gap and unchanged authority

The existing replacement workbench retains its original request only in memory and
can copy a request. This package adds a manual same-site recovery envelope and a
strictly audit-only imported controller. It does not change approval, replacement,
release or snapshot business policy, backend endpoints, authentication configuration,
existing submission/retry behavior or real personnel permissions.

A newly valid session for the same original authenticated actor may query that
actor's original atomic event under the existing current USER/session and audit-read
contract. This is not a new RELEASE_AUTHORITY grant check or a permission to submit.
An expired/revoked/foreign session, missing audit, unavailable server or mismatch
remains UNKNOWN. A later effective decision does not erase a verified historical
replacement; recovery must not replace original evidence with a current-head query.

## Canonical user-controlled envelope

The bounded, versioned export contains only format, version, exact application origin
and the original canonical command: new approval reference, predecessor UUID,
release/snapshot UUIDs, copied predecessor labels and the frozen body/request ID.
The new decision, notes, correction reason and declared authority text are retained
exactly as originally prepared. Import never normalizes a changed request into a
new one, regenerates an identifier/time, contacts the server, writes local storage or
carries credentials, cookies, tokens, session IDs, claimed authenticated identities
or verified receipts. Duplicate keys, extra fields, other kinds, origin mismatch,
malformed Unicode, oversize and noncanonical payloads are rejected rather than fixed.
Existing business command byte limits remain unchanged.

Confirmed preparation and an unknown attempted result may both be exported. A
confirmed preparation is only the user's reviewed request, not evidence it was sent.
The warning before reveal/copy identifies declared names, internal references, notes
and reasons as potentially sensitive business metadata for private local handling.
No automatic download, clipboard write, browser storage or third-party upload occurs.
Import provides only a read-only recovery method: no send, retry or auto-submit API.
An explicit query uses exactly the imported original command and existing receipt
route. Copy/reveal/import/query interactions cannot overwrite a busy or unknown
attempt, and stale completions must not mutate a newly selected state.

## What the audit actually proves

The existing atomic audit validates the original actor, event/request, new approval,
predecessor UUID, release/snapshot UUIDs and complete applied request body. It does
NOT certify the copied predecessor decision number, decision label or readiness
label: those fields are preparation metadata, not present in the original audit.
The current receipt projection retains a client-derived predecessor label internally;
this package must not display it as verified historical evidence. Such labels remain
explicitly unverified preparation metadata even if the original operation is confirmed.
A regression deliberately changes those labels while preserving the exact event
binding: recovery may still confirm the original operation, not the changed labels.
Changing the actual predecessor UUID/release/snapshot/body or actor cannot confirm it.

The result means only that the matching original event exists. It does not establish
current effective decision, current deployment eligibility, a new approval, physical
flashing or revocation of earlier production facts.

## Verification and acceptance

Tests cover canonical envelopes and byte/Unicode/origin boundaries, unknown export,
zero-network import, absent send/retry methods, explicit query locking, same-actor
new-session recovery, existing same-origin/default-off/current-user checks, mismatched
atomic evidence, metadata versus authoritative fields, raw Chinese/English rendering,
clipboard/async races and refusal to replace unresolved attempts. Composed tests
exercise the imported controller through the real existing proxy, not just a fake
success response. No real business writes or live identity configuration are used.

Full frontend tests/build and complete precise-head backend/PostgreSQL CI remain
required even though no backend source changes. Provider observations must be fresh;
an unchanged backend is not a new Render deployment. Synthetic tests are not real
browser/multiuser acceptance. Overall36/44=82% remains unchanged until actual milestone
criteria pass. P6 status recovery, conditional P7 operations integration and P8 final
integration/reconciliation remain separate bounded packages.
