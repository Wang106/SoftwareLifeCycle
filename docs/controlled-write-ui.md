# Controlled write UI plan and request preparation

This is an implementation plan for the existing 14 command APIs, not authorization
to enable public writes. The current `/commands` workspace prepares requests only.

| Priority | Commands | UI status | Remaining submission work |
| --- | --- | --- | --- |
| First | Snapshot, actual-software report/correction, Batch | Request preparation implemented | Approved target, login/session, authenticated submission and uncertain-result recovery |
| Next | Approval Action, Release Decision | Request preparation implemented; exact step UUID visible in approval detail | Permission-aware pickers, authenticated submission and outcome verification |
| Next | Impact Assessment, Acceptance-to-DVP Link, Resource | Request preparation implemented | Permission-aware context pickers, authenticated submission and outcome verification |
| Later | Delivery, Distribution, Authorization | API retry/locks exist; forms pending | Artifact policy/recipient/scope pickers and complete chain confirmation |
| Later | Test Release, Deployment, Changeover | API retry/locks exist; forms pending | Purpose/location/source pickers; activation/revocation contracts where absent |

## Implemented workspace

Entry points are `/create`, exact SSR/ASR release profiles and deployment detail.
Release links prefill its UUID for Snapshot. Deployment links prefill the exact
business number for actual/Batch preparation. Switching query targets remounts the
form; changing any field or operation invalidates the reviewed request. Deployment
detail displays actual_version; missing versions are shown as unavailable, never zero.

The Snapshot/actual/Batch forms validate UUIDs, bounded business numbers without path separators/dot segments, exact version integer,
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

Approval preparation requires an explicit step UUID, one of APPROVED/RETURNED/REJECTED,
and a nonblank declared operator (up to 120 characters). Approval detail shows exact
step UUIDs and can prefill the first visible PENDING/WAITING step for a nonclosed
request. It does not establish that this step is still active. If none is visible,
no UUID is invented; truncated/stale context must be checked through the API.
Changing the step query remounts the workspace and clears any old review.

Decision preparation requires its number plus exact declared operator, readiness
status and decision text (each status/decision up to 30 characters). The existing
backend accepts arbitrary readiness/decision strings: this UI does not compute or
certify readiness, introduce an enum or infer a new business policy. Declarations
retain their exact text, optional comments/notes retain exact text or null. Client
text limits are a stricter preparation subset; legacy API behavior is unchanged.
OIDC execution binds the actual actor to a trusted principal and preserves these
declarations separately. Neither field identifies an authenticated reviewer.
Approval/decision evidence links lead to the exact approval and original snapshot;
expected audit links use EVT-AP-/EVT-RD- with the request UUID hex. Approval outcomes
are reviewed in history; decision outcomes link to the exact decision business number.
These links do not prove that a copied request executed successfully.

Snapshot links to its release's snapshot history; actual links to its deployment;
Batch links to its expected batch business number. Audit links use deterministic
EVT-SN-/EVT-DA-/EVT-PB- plus the request UUID's hex form. Before execution these
expected audit records may not exist. Prepared/copied requests are never labeled as
successful writes. A business-number link alone does not prove this request succeeded;
verify the API result and matching audit evidence after controlled execution.

## Evidence and reference preparation

Eight of 14 commands now have request-preparation forms; this counts preparation,
not authenticated submission or full Phase 6 completion. Impact evidence links prefill
issue number and exact release/frozen-snapshot UUIDs. No missing snapshot is invented.
Impact requires AFFECTED/NOT_AFFECTED/NEEDS_REVIEW, reason and declared operator;
optional evidence_ref is text only. Shared software, matching versions or PASS tests
never select the judgment. The evidence page may show a newer snapshot later;
review the exported snapshot UUID and the matching event, not latest status alone.

Coverage displays criterion/DVP UUIDs and can prefill an exact criterion within its
SCR. A DVP UUID is explicitly supplied; no first item/default assignment is selected.
The backend checks both objects belong to the SCR. Assignment does not prove execution
or readiness. Impact/assignment reasons and actor names are trimmed as in Pydantic;
blank evidence references become null. Resource text is trimmed, optional description
becomes the empty string, and text length/control checks follow its existing schema.

Resource requires one of the ten existing target types, target UUID, title, explicit
location kind, location, reason and declared operator. Its WEB_URL checks form a
stricter preparation subset: explicit lowercase HTTP(S) authority, no embedded
credentials/backslashes/whitespace, invalid ports, malformed escapes or decoded controls.
The original trimmed URL is preserved; it is not fetched or normalized into a different
location. LOCAL_PATH accepts absolute POSIX/Windows drive paths; NETWORK_PATH requires
server and share. Paths/URLs are text inputs and previews, not auto-opened links,
file uploads, verified access or distribution permission. Supplier/customer registration
still requires PLATFORM_ADMIN in OIDC mode. Input references must not contain secrets.

Expected event numbers use hyphenated UUIDs: EVT-IMPACT-{UUID}, EVT-AC-{UUID},
EVT-LK-{UUID}, unlike earlier commands' hex suffixes. Impact links to bounded issue
judgment history, assignment to SCR coverage with assignment IDs, and Resource to its
request UUID detail. Historical pages may truncate or change; use exact API outcome
and matching audit evidence after execution. No dedicated assessment detail endpoint,
provider-backed execution or generalized supersession/revocation is claimed.

Only bounded release/snapshot/criterion/entity-type query context is consumed.
Array/oversized release/snapshot/criterion context stays empty; malformed UUID text fails preparation; context changes remount the workspace and
invalidate old review. Sensitive locations/reasons/operators are not query-prefilled.
No backend/schema, migration, transport, browser storage or auth configuration changes.

## Boundary and remaining acceptance

The workspace has no fetch/POST transport, server mutation route, API-origin picker,
login/token field, browser storage or background retry. Query inputs are bounded,
rendered as text and encoded into route paths; no client input chooses an API host.
Public API remains READ_ONLY_MODE=true. The workspace does not bypass OIDC, exact
scope, trusted actor, row locking, versions, limits or atomic audit; it makes no write.

Actual authenticated submission, permission-aware pickers, stale-context refresh,
uncertain-result resolution, success/error trace and the other six forms remain pending.
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
