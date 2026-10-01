# Controlled write UI plan and request preparation

This is an implementation plan for the existing 14 command APIs, not authorization
to enable public writes. The current `/commands` workspace prepares requests only.

| Priority | Commands | UI status | Remaining submission work |
| --- | --- | --- | --- |
| First | Snapshot, actual-software report/correction, Batch | Request preparation implemented | Approved target, login/session, authenticated submission and uncertain-result recovery |
| Next | Approval Action, Release Decision | API retry/step locks exist; forms pending | Exact step selection, review evidence, confirmation and outcome trace |
| Next | Impact Assessment, Acceptance-to-DVP Link, Resource | API retry contracts exist; forms pending | Exact scope/context pickers and judgment/reference validation |
| Later | Delivery, Distribution, Authorization | API retry/locks exist; forms pending | Artifact policy/recipient/scope pickers and complete chain confirmation |
| Later | Test Release, Deployment, Changeover | API retry/locks exist; forms pending | Purpose/location/source pickers; activation/revocation contracts where absent |

## Implemented workspace

Entry points are `/create`, exact SSR/ASR release profiles and deployment detail.
Release links prefill its UUID for Snapshot. Deployment links prefill the exact
business number for actual/Batch preparation. Switching query targets remounts the
form; changing any field or operation invalidates the reviewed request. Deployment
detail displays actual_version; missing versions are shown as unavailable, never zero.

The three forms validate UUIDs, bounded business numbers without path separators/dot segments, exact version integer,
report/correction reason and calendar-valid ISO time with explicit zone. Actual
preparation requires a reason even for an initial report, covering migrated actual
records at version zero. The optional timestamp is UTC-normalized or null; omission
remains distinct from explicit time. Batch notes preserve exact text. These client
checks do not prove existence, snapshot membership, permission or quota eligibility.
The backend remains the business/security authority when a controlled client executes.

Preparing creates one UUID and an immutable request preview. Repeated copies keep
that exact key/content. Confirmation enables copying `{method, path, body}` JSON;
this envelope is an instruction for a controlled client, not the API body itself.
Send only `body` as JSON to `path`. Fields cannot change while clipboard copying is
in progress. Clipboard denial leaves a selectable reviewed request. Starting another
request requires another preparation/key; preserve an exported request until any
uncertain manual API result has been resolved. This page cannot track such execution.

Snapshot links to its release's snapshot history; actual links to its deployment;
Batch links to its expected batch business number. Audit links use deterministic
EVT-SN-/EVT-DA-/EVT-PB- plus the request UUID's hex form. Before execution these
expected audit records may not exist. Prepared/copied requests are never labeled as
successful writes. A business-number link alone does not prove this request succeeded;
verify the API result and matching audit evidence after controlled execution.

## Boundary and remaining acceptance

The workspace has no fetch/POST transport, server mutation route, API-origin picker,
login/token field, browser storage or background retry. Query inputs are bounded,
rendered as text and encoded into route paths; no client input chooses an API host.
Public API remains READ_ONLY_MODE=true. The workspace does not bypass OIDC, exact
scope, trusted actor, row locking, versions, limits or atomic audit; it makes no write.

Actual authenticated submission, permission-aware pickers, stale-context refresh,
uncertain-result resolution, success/error trace and all other forms remain pending.
Configure an approved OIDC provider/session and a separately approved controlled
write target before implementing production submission. Avoid exposing auth-disabled
writes through a frontend proxy. General correction/revocation workflows remain open.

## Verification

`cd frontend && npm test` compiles the pure request helper with the pinned installed
TypeScript toolchain and runs Node's built-in tests without a new dependency.
Tests cover immutable review, confirmation, stable retries, UUIDs/versions/reasons,
UTC equivalence, null omission, impossible dates, exact notes and route encoding.
`npm run build` validates Next.js/TypeScript integration. No database migration or
backend contract change is required by this UI package. Browser/online checks are
reported separately; helper tests are not a provider-backed submission end-to-end test.
