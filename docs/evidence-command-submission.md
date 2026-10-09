# Impact and Acceptance submission / original-audit recovery

Updated: 2026-10-09 (Asia/Shanghai), Codex.

All fourteen business command transports/controllers are now implemented. Eleven
bilingual submission UIs exist; Impact, Acceptance and Resource UI wiring remains
pending. These counts exclude two own-session controls, six administrator commands
and offline operator modes. Mock regression is not real-user/browser acceptance.

## Independent disabled gate and fixed transport

POST `/auth/evidence-command` submits; POST `/auth/evidence-command-receipt` queries
original audit. GET returns 405. Only impact and acceptance are supported.
`EVIDENCE_COMMAND_SUBMISSION_MODE=disabled` is default. Enabling requires explicit
`enabled`, valid OIDC/encrypted session configuration, and exact server-only
`EVIDENCE_COMMAND_APPROVED_API_BASE_URL` / `EVIDENCE_COMMAND_APPROVED_APP_ORIGIN`
bindings. Resource/production/other command or NEXT_PUBLIC flags cannot open this
route. No actual secrets, identities, grants or approved write flags are configured.

Every execution resolves one current token-bound USER session. Submission requires
non-read-only mode; own original-audit queries remain available after read-only
switches. The backend independently authorizes exact Issue/SCR CONTRIBUTOR scope.
Declarations and active grant counts do not grant permission. Credentials remain
server-side. Responses are private/no-store.

Strict outer operation/target/body fields. Target is an explicit Issue or SCR
number, with existing identifier validation. Impact body is exactly request_id,
actor_name, reason, release_id, snapshot_id, decision, evidence_ref; Acceptance body
is exactly request_id, actor_name, reason, criterion_id, dvp_item_id. The reference
must be explicitly present; null or text is normalized by existing preparation.
All UUIDs, explicit judgment and text bounds use the existing command contract;
unpaired Unicode surrogates are rejected. No caller URL/path/headers/credentials.

Same-origin JSON; strict UTF-8; declared and streamed request limit 8192 bytes.
Responses/audit reads are bounded to 16384 bytes, 15 seconds, no redirects/caching.
Business POST paths are `/api/v1/issues/{original number}/impact-assessments` and
`/api/v1/changes/{original number}/acceptance-dvp-links`. HTTP201 creation and
HTTP200 idempotent replay both still require exact original audit confirmation;
POST current-state replies do not prove original result or replay status.

## Original historical evidence

Recovery only GETs `/api/v1/activity/{original event number}`. It never queries
current domain objects and never falls back to business POST. Every receipt binds
the original authenticated principal, declared actor, reason and exact original
entity reference. The domain entity UUID is the Issue/SCR UUID; the operation
UUID comes from payload.assessment_id / assignment_id, not entity_id.

Impact: EVT-IMPACT-{hyphenated request UUID}, ISSUE_IMPACT / Issue / ASSESS.
Bind release_id, snapshot_id and original decision. New audits add
`evidence_ref_digest_version=1` plus `evidence_ref_sha256`: SHA-256 of the compact
UTF-8 JSON representation of the normalized nullable evidence_ref. Python uses
ensure_ascii=False/separators=(',', ':'); JS uses JSON.stringify. Explicit null
hashes the bytes `null`; absence does not equal null. The reference remains absent
from activity payloads. The digest is written in the same transaction as the
assessment/audit; replay does not rewrite history. Old audits missing it stay
unknown, including old null references. API0.18.38 must be deployed before new
Impact submissions can be confirmed; online API deployment/version is unverified.

Impact receipt keeps the exact release/snapshot UUIDs, original audit snapshot_no,
original decision, declaration/reason and digest-confirmed reference. snapshot_no
is the original server audit label, not a caller request field or a current-label
lookup. NEEDS_REVIEW is a judgment, not a test result; no propagation or downstream
release/distribution/production permission is inferred.

Acceptance: EVT-AC-{hyphenated request UUID}, ACCEPTANCE_DVP /
SoftwareChangeRequest / ASSIGN. Existing audit already contains assignment_id,
criterion_id and dvp_item_id, plus original entity ref/declaration/reason. These
complete historical fields are validated without fabricating a request fingerprint
or modifying legacy audits. Receipt proves only the original explicit assignment;
it does not imply DVP PASS, verification completion, acceptance completion or release
permission. No current status, replayed or invented status field is projected.

## Frozen controller and remaining work

EvidenceSubmission requires exact boolean-confirmed canonical path/trace/audit/body,
freezes original number/UUID/bytes and synchronously interlocks sending/querying.
Confirmed is terminal. Lost replies or invalid/missing/denied audit stay unknown;
only explicit retry resends original bytes. Later gate, session, role or business
denials cannot erase prior uncertainty. Only explicit recovery reads original audit.
Memory only: refresh/unmount/cross-session import is still pending. Bilingual UI
capability projection, sending, original-audit queries, explicit retries and exact
results for these two and Resource are implemented in `/commands`. The page projects
only submit/recover booleans from the independent gates and one current USER session;
read-only still permits querying the original audit. Unknown requests stay frozen
across command, context and capability refreshes and cannot borrow another gate.
Impact links the original audit snapshot label; Acceptance links the assigned DVP
UUID. Detail/history links are separate observations and open independently.

No schema migration (0020). Public sample environment remains read-only; OIDC and
all submission gates stay disabled. Real provider/browser/admin/internal acceptance
has not occurred. Internal installation has not begun; SSO, personnel and offline
Windows/no-Docker/CPU constraints are undecided. Do not retry denied browser access.


## Manual cross-session audit-only recovery — 2026-10-09
All fourteen business commands can explicitly export canonical, versioned recovery text and import it on the same origin in a later session. Import stages uncertainty without network activity, permits only explicit original-audit queries and has no write/retry method. Missing or denied audit stays unknown; existing in-page exact retries are unchanged. No automatic browser storage or credential export. Manually saved business text may include private references. See [business-request-recovery.md](business-request-recovery.md); real provider/browser/internal acceptance remains pending.
