# Administrator registration transport

The default-disabled server proxy and memory-only retry controller are now connected
to the bilingual registration preparation page. Server-approved configuration and a
fresh writable identity are required before sending is offered; confirmation is still
required. The backend separately authorizes administrator access.

## Independent server gate

`POST /auth/admin-registration` requires all three operator settings:

| Setting | Required value |
| --- | --- |
| ADMIN_REGISTRATION_SUBMISSION_MODE | enabled |
| ADMIN_REGISTRATION_APPROVED_API_BASE_URL | exact canonical server API_BASE_URL |
| ADMIN_REGISTRATION_APPROVED_APP_ORIGIN | exact canonical BROWSER_SESSION_ORIGIN |

Complete encrypted browser-session and OIDC code configuration is also required.
The grant-status enablement settings do not enable registration. Missing, disabled,
invalid or mismatched configuration returns 503 before contacting any service.
GET returns 405/Allow: POST. All responses are private/no-store, cookie-varying,
no-referrer and nosniff. No environment settings or secrets are changed by this package.

## Exact command and receipt

The same-origin JSON envelope is the exact `RegistrationInput` from the preparation
helper (kind/newId/eventNo/reason plus kind-specific fields). It does not contain an
API URL, issuer, actor, token or requested initial status. Unknown fields, cross-scope
roles, invalid UUIDs/audit keys/text and bodies above 8192 bytes are rejected before
session lookup. Subject and display name retain exact case and Unicode; reason uses
the existing Python whitespace contract. The server constructs one of the existing
fixed principal/global/project/software registration paths.

The encrypted cookie is unique and bound to the configured provider/target. Before
each POST, the backend current-user endpoint rechecks the registered browser session;
read-only mode rejects the operation. Token and session ID remain server-only. Backend
PLATFORM_ADMIN authorization, issuer/recipient eligibility, protected admin recipients,
duplicate detection, actor-bound replay and atomic audit remain authoritative.

Successful receipts must match kind, UUID, event number, initial applied status, and
grant recipient/role/target where applicable. Principal registration requires zero
revoked sessions. The browser receives only a projected receipt, never arbitrary
upstream fields, subject, issuer, credentials or provider error text. Initial identity
DISABLED and grant SUSPENDED are distinct from observed current status, which may be
ACTIVE on replay after a separately audited activation. Registration never activates
an identity, resumes a grant or creates an account at an identity provider.

## Retry and uncertainty

The tested `RegistrationSubmission` foundation requires an unaltered confirmed review,
freezes the request, locks synchronously against double clicks, and stops after an
exact confirmed receipt. Loss, malformed/oversized/mismatched receipts, redirects and
unrecognized server failures produce outcome_unknown with no automatic retry. Explicit
retry uses byte-identical original input and audit key. A later rejection or disabled
gate does not erase an earlier uncertain outcome. Recognized pre-commit denials are
allowlisted; configured_issuer_required is a known backend pre-write 503.

Recovery is only in memory. The page freezes fields and confirmation after the first
attempt, warns before leaving during sending/unknown outcomes, and permits only explicit
original-request retries. Unknown outcomes cannot start a new registration. A confirmed
receipt or authoritative first rejection permits a new UUID/audit key and clears target
fields for a fresh review. Copying an attempted request does not claim no write occurred.
Grant details open in a separate tab without replacing the recovery page; principal
reading is still unavailable. Registration does not activate identities or resume grants.
Cross-refresh/cross-session import and durable recovery remain unimplemented. Tests
use simulated identity/session/transport behavior and production disabled-route SSR;
they do not constitute real provider, browser or administrator acceptance.

API0.18.35/schema0020 unchanged; public sample-only/read-only/OIDC-off boundaries remain.
No real identities, grants, secrets, internal deployment or accepted SSO are provisioned.

The private catalog projects current identity read_only_mode separately from catalog extras.
The page shares registrationSubmissionConfigured with POST and cannot use grant-status
settings as registration permission. CI explicitly runs the fixed progress ledger --check.
Component event-handler tests use an isolated hook runtime, plus real React bilingual SSR;
these are not actual browser/DOM or provider-backed administrator acceptance.

The beforeunload warning covers full page unload/refresh only. Client-side navigation
or losing access to the private page may unmount it without that warning. Copy the
original request/receipt first; durable or cross-session recovery is not implemented.
