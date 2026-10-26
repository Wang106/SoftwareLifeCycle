# Controlled Batch correction workbench

## Scope and completion boundary

Baseline main `609394fdd55ac01dc40d06c888d37c1bc3edf833` (PR154) provides public
sample-only correction history, but not a controlled Batch correction experience.
This package is a Batch-only vertical slice: authenticated exact-parent preparation
context, independent default-disabled submission/original-audit recovery, and bilingual
review, confirmation and original-result UI. Changeover correction submission remains
separate. This supplements the existing14 ordinary business commands; it does not
inflate that inventory or imply all correction/revocation flows are accepted.

Maps R12/R13 and Phase6 correction/trace work. Real approved-provider, browser,
multi-user and company acceptance are still required. Overall36/44=82% and existing
seven module/plan denominators stay unchanged. No actual identity, credential, role,
provider variable, network, billing, migration or CI/deployment permission is changed.

## Private context, not public history permission

GET `/api/v1/deployments/{deployment_no}/batches/{batch_no}/correction-context`
uses existing OIDC authentication, current ACTIVE principal and token-bound browser
session validation, then exact deployment `PRODUCTION_OPERATOR` authorization (with
existing administrator behavior). Backend USER/SERVICE support follows the existing
contract; the browser proxy additionally requires the current token-bound USER.
Disabled OIDC or absent/invalid identity is denied, not legacy unauthenticated access.
Responses are private/no-store; permission or session revocation is rechecked.

The exact parent-child relation must match. The canonical projection supplies batch
UUID, immutable software/snapshot attribution, effective facts, revision and predecessor
from one SQL statement. It is a read-only observation, not a reservation or write grant.
Read-only mode can allow authenticated preparation but still blocks business writes.
Public sample history never substitutes for this private context or permission.

## Independent default-off browser channel

`BATCH_CORRECTION_SUBMISSION_MODE` is disabled unless explicitly `enabled`, with
`BATCH_CORRECTION_APPROVED_API_BASE_URL` and `BATCH_CORRECTION_APPROVED_APP_ORIGIN`
matching the existing validated session configuration. No values are configured by
this package. Other command gates, public variables or active-grant counts cannot
open this channel.

POST-only `/auth/batch-correction-context`, `/auth/batch-correction` and
`/auth/batch-correction-receipt` use existing encrypted sessions, same-origin checks,
strict bounded UTF-8 JSON, fixed backend paths, timeouts, redirect refusal and
private/no-store responses. No caller URL, credentials, headers or private identity
are accepted from the client. Context is fetched explicitly; no background write or
automatic retry occurs.

The frozen command contains exact parent/Batch target, canonical context and body:
request ID, expected revision, predecessor ID, start/end timestamps, optional
Changeover link, note and correction reason. Software/snapshot attribution cannot
be edited. UTC normalization preserves microseconds. **Null start/end means retain
existing effective time, not clear it**; null note or Changeover link clears that field.
The reason is explicit and bounded; timestamps and chronological order are validated.

## Trusted original result and history compatibility

Existing Batch correction audit request fingerprints do not contain a deployment
number. Matching a client-supplied parent against that fingerprint alone would permit
a forged route-parent claim. Therefore NEW correction audit payloads additionally
record `deployment_no` derived from the service's locked canonical deployment.
This field is outside the existing request fingerprint: existing idempotency and
append-only historical events are preserved, with no migration or retrospective edit.
No new cryptographic proof, key or credential is introduced.

Receipt validation requires the exact authoritative audit parent, Batch UUID/number,
authenticated actor, `PRODUCTION_BATCH`/`CORRECTED` event, original request, correction
reason and before/after values. The original event is `EVT-BC-{request_id_without_hyphens}`.
Null timestamp retention is checked against original before/context facts; current
history, current status, a newer head or a successful HTTP response cannot prove the
original result. Revision shown from the successful original contract is expected
revision plus1, not a later current revision lookup.

Historical audit events without authoritative parent evidence remain UNKNOWN in this
new channel, even if their backend replay contract remains valid. They require manual
review through existing audit/history tools; no fake success or absence is inferred.
Recovery queries only the original audit with current authenticated identity and
validates the original actor. A later revoked membership may deny a new write/replay;
it cannot turn an uncertain previous outcome into proven failure. Historical own-audit
recovery does not grant current production permission.

## Frozen UI and limitations

The Batch-only workbench is linked from the Batch history view. It explicitly loads
private context, shows original versus replacement facts, then requires review and
confirmation before constructing the frozen submission. Request ID, parent, child,
revision, predecessor and body stay fixed while sending/checking/unknown. Context,
form or capability changes cannot overwrite an unknown operation. Explicit recovery
reads the original audit; explicit retry repeats the original bytes and request ID.
Known stale/version rejection requires fresh context and review, never automatic
rebase. Confirmed original results are terminal and include audit/history trace links.

Labels are bilingual, while raw facts, notes, reasons and identifiers are not translated
or silently truncated. Default-disabled/read-only/session failures remain explicit.
This is memory-only workflow state, not cross-refresh/session import recovery. Real
browser interaction and provider-backed user acceptance remain unverified; prior
sandbox/browser restrictions are not bypassed.

## Verification checkpoint

Exact tests, independent review, PR head, complete unchanged CI and fresh postmerge
provider evidence are recorded in DEVELOPMENT_STATUS/HANDOFF and the PR. Backend
context tests cover authentication/session/scope/parent binding and coherent reads;
transport/UI tests cover disabled gates, strict original evidence, conflicting/revoked
states and frozen unknown recovery. Real PostgreSQL cases must run without skips in
exact-head CI. An initial new UTC-format assertion was corrected to compare the exact
instant and zero offset, not require a particular equivalent `Z` versus `+00:00` spelling;
no API time semantics or existing test gate was weakened.

Local aggregate validation: 86 related backend cases passed; 19 new SQLite cases
passed and 20 new real PostgreSQL cases await exact-head CI. All 1,634 frontend tests
passed with zero skips, plus typecheck, Worker configuration, Next production build
and 52 automation checks. An external dependency symlink initially blocked Turbopack;
installing the unchanged lock in this checkout resolved it without touching the old
checkout or configuration. Wrangler reported a nonfatal default log-directory problem
while its configuration validation exited successfully; no permissions were changed.
