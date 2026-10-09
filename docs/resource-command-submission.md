# Resource registration and original-audit recovery

Updated 2026-10-09 (Asia/Shanghai), Codex.

Resource is the twelfth of fourteen business command transports/controllers. Impact
and Acceptance remain preparation-only; Resource's bilingual send/result UI is
not yet connected. Existing eleven UIs remain unchanged.

## Independent disabled gate

POST `/auth/resource-command` submits; POST `/auth/resource-command-receipt`
queries original audit. GET returns 405. `RESOURCE_COMMAND_SUBMISSION_MODE=disabled`
is the default. Enabling requires explicit `enabled`, valid OIDC/encrypted session,
and exact server-only `RESOURCE_COMMAND_APPROVED_API_BASE_URL` and
`RESOURCE_COMMAND_APPROVED_APP_ORIGIN` bindings. Other command/NEXT_PUBLIC gates
cannot enable this route. Responses are private/no-store. No environment secrets,
identities, grants or real-write flags are configured in this package.

Every execution rechecks the current token-bound USER session. Submission requires
non-read-only mode; own receipt recovery remains available after a read-only switch.
The API independently enforces exact Resource target authorization. Grant counts
and the declared operator do not grant permission.

## Exact request and bounded transport

Strict outer fields: operation=`resource`, target=object UUID, body. Body must have
exactly request_id/entity_type/entity_id/title/location_kind/location/description/
actor_name/reason. The redundant target must match entity_id. Existing preparation
validates supported object types, UUIDs, text limits and explicit WEB_URL,
LOCAL_PATH or NETWORK_PATH. Text trims match the API; URL/path strings retain their
original spelling and are never fetched/opened by this transport. Invalid embedded
URL credentials/controls and unpaired Unicode surrogates are rejected.

Same-origin JSON, strict UTF-8, streamed/request Content-Length limit 8192 bytes;
response limit 16384 bytes, 15-second requests, no redirect or caching. Only POST
`/api/v1/resources` is used for business writes. HTTP201 creation and HTTP200
idempotent replay both require exact original audit; neither implies replay status.

## Versioned original request digest

New API audit records retain existing target_type/target_id/target_ref/location_kind
and add request_digest_version=1 plus request_sha256. The digest is SHA-256 of a
compact UTF-8 JSON array of normalized fields in this exact order:
request_id, entity_type, entity_id, title, location_kind, location, description,
actor_name, reason. Python uses ensure_ascii=False and separators=(',', ':');
JavaScript uses JSON.stringify. Resource locations and descriptions remain absent
from general activity payloads. The digest is written atomically with the existing
Resource row and audit; replay does not rewrite history. No schema migration.

Recovery only GETs `/api/v1/activity/EVT-LK-{original UUID}`. It requires the exact
current principal, AUTHENTICATED_PRINCIPAL source, RESOURCE_LINK/REGISTER type/action,
original entity UUID/ref, declared operator/reason, target type/id, location kind,
and versioned full request digest. Receipt projects only that confirmed request's
original fields and original target_ref. No caller-supplied href or current-object
lookup is used. No status is invented: registration does not prove file existence,
content verification, file delivery or distribution permission.

Older audits lacking the digest remain unknown; no retrofit or current-object
fallback fabricates original evidence. Backend must be deployed with API0.18.37
before real Resource submissions can be confirmed. Online API deployment/version
is not verified by a frontend Cloudflare build.

## Frozen controller and remaining acceptance

ResourceSubmission requires exact confirmed canonical path/trace/audit/body,
freezes original target/UUID/bytes, and synchronously interlocks sends and queries.
Lost responses stay unknown; only explicit retry resends original bytes and only
explicit recovery queries original audit. Later denials cannot erase uncertainty;
confirmed is terminal. Memory only: refresh/unmount/cross-session import is pending.

The bilingual `/commands` interface now projects independent Resource submit/recover
booleans using one current USER session for all six command groups. Read-only permits
original-audit queries; only explicitly non-read-only permits sending. Unknown
requests keep their original target, ID and exact bytes across context/gate changes.
The result displays original registration text, target_ref and precise Resource/audit
links without turning a location into a clickable URL or fetching it. Reference
registration does not prove file existence, verified content or distribution rights.

Public samples stay read-only; all submission and OIDC gates remain disabled.
Real provider/browser/admin/internal-server acceptance is pending. Internal server
installation has not begun; SSO, personnel, OS/CPU and no-Docker constraints are
undecided. Existing browser access denial is not retried or bypassed.


## Manual cross-session audit-only recovery — 2026-10-09
All fourteen business commands can explicitly export canonical, versioned recovery text and import it on the same origin in a later session. Import stages uncertainty without network activity, permits only explicit original-audit queries and has no write/retry method. Missing or denied audit stays unknown; existing in-page exact retries are unchanged. No automatic browser storage or credential export. Manually saved business text may include private references. See [business-request-recovery.md](business-request-recovery.md); real provider/browser/internal acceptance remains pending.
