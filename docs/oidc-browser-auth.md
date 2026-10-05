# OIDC browser authentication implementation — 2026-10-06 (Asia/Shanghai)

Codex implementation; current API version0.18.29 and database head0019_browser_sessions. Public staging remains sample-only/read-only. No provider or secret
has been configured or provisioned by this change.

## Implemented contract

| Frontend route | Method | Behavior |
| --- | --- | --- |
| `/account` | GET | Default Chinese / selectable English; unavailable, signed-out, signed-in or generic failure view |
| `/auth/login` | POST | Same-origin start; encrypted five-minute pending cookie; redirect to configured provider |
| `/auth/callback` | GET | Validate pending state/config/expiry, redeem code with PKCE, verify tokens, resolve active local USER, issue session |
| `/auth/session` | GET | Current projected identity/grant counts; recheck backend every time; clear invalid session |
| `/auth/logout` | POST | Same-origin backend session revocation, then cookie clearing; failures preserve the cookie |

Auth HTTP routes are private/no-store, vary on Cookie, use no-referrer and nosniff.
Wrong GET/POST methods return405. Disabled mode returns503 without provider/API
requests; the account page offers no login form. Login/logout require both the
configured request origin and matching Origin header; cross-site/same-site fetch
metadata fails closed. Callback success returns to `/account`, never an input
return URL. Browser callback errors return to `/account?auth=failed` with a generic
translated message; JSON clients receive only a generic error code, never provider
text, tokens, authorization code or secret values.

The prior helper's HUMAN discriminator was a contract bug: backend principals
use USER/SERVICE. The helper now accepts USER and rejects SERVICE/HUMAN for browser
sessions; signed mock-provider tests cover all three explicitly.

## Operator configuration (not applied to deployed environments)

| Server-only variable | Requirement |
| --- | --- |
| `BROWSER_OIDC_MODE` | Default disabled; code explicitly opts in |
| `BROWSER_SESSION_MODE` | Default disabled; encrypted required for code mode |
| `BROWSER_SESSION_ORIGIN` | Approved HTTPS app origin, no path/query/fragment |
| `BROWSER_SESSION_KEY` | Random32-byte base64url key, managed as a secret; never commit or NEXT_PUBLIC |
| `API_BASE_URL` | Explicit approved HTTPS API target; no NEXT_PUBLIC fallback |
| `OIDC_ISSUER_URL` | Exact HTTPS issuer, shared with backend; trailing slash remains significant |
| `OIDC_AUDIENCE` | API access-token audience, shared with backend |
| `OIDC_CLIENT_ID` | Registered browser/BFF client; ID-token audience |
| `OIDC_AUTHORIZATION_URL` | Explicit approved HTTPS authorization endpoint |
| `OIDC_TOKEN_URL` | Explicit approved HTTPS token endpoint |
| `OIDC_JWKS_URL` | Explicit approved HTTPS JWKS endpoint, shared with backend |
| `OIDC_SCOPE` | Default openid; operator may add provider-specific API scopes; openid required, offline_access rejected |
| `OIDC_CLIENT_AUTH` | none for an approved public client; client_secret_basic for an approved confidential client |
| `OIDC_CLIENT_SECRET` | Required only for client_secret_basic; send only to pinned token endpoint |

Register the exact `BROWSER_SESSION_ORIGIN/auth/callback` as a query-mode code
callback. Provider must support PKCE S256, RS256 signed ID and JWT API access tokens,
matching subjects and the configured API audience; opaque access tokens and
refresh flows are deliberately unsupported. Access token limit2400 characters
keeps the encrypted session cookie below3800 characters. Both tokens require
iss/aud/sub/iat/exp; ID token also requires nonce, bounded authentication age and
proper azp for multiple audiences. Access-token subject must equal ID-token subject;
issuer, audience, signature, expiration and future issued-at are checked for each.
ID at_hash/c_hash are verified when present. Token-provided URLs/JWKs are never
used for network requests. JWKS is fetched from the configured URL on each login;
no shared/stale provider key cache is introduced.

All provider/API fetches use no-store, prohibit redirects and have five-second
timeouts. Token response limit32KiB, JWKS64KiB/64keys, own identity16KiB; streamed
and declared limits are enforced. Extra provider fields and refresh tokens are not
retained or rendered. Secret authentication uses encoded HTTP Basic credentials,
never an authorization-page query or client-side field.

Backend must independently be configured for approved OIDC and the same
issuer/audience/JWKS, and an ACTIVE USER must already be provisioned. No automatic
identity/grant provisioning exists. Missing/disabled identity or unavailable API
prevents session issuance. Grant counts do not authorize a command, and login never
changes READ_ONLY_MODE or enables business writes.

## Cookie and acceptance boundaries

Both cookies are __Host-prefixed, Secure, HttpOnly, SameSite=Lax, Path=/, no Domain,
AES-GCM encrypted with cookie-name authenticated data. Pending transaction holds
random256-bit state, nonce and PKCE verifier. Session binds the current principal,
application/API and all provider/client configuration, including secret rotation;
configuration or key changes invalidate pending and existing cookies. Session
expires at the earliest ID-token expiry, API-token expiry, expires_in if provided,
or15minutes; reads never extend it. Invalid session clears the local cookie.

Callback clears the browser's pending cookie on success/failure. Provider must
reject authorization-code reuse; there is no server-side pending-transaction store.
Logout revokes this registered browser session before clearing session/pending cookies.
Subsequent requests with a copied cookie fail the backend session check. Revocation
does not cancel a request whose session check already completed, other browser
sessions, or the provider bearer token. Provider-wide logout, refresh and a server-side
pending-transaction/code replay store remain future work; no completed real-provider/browser credential acceptance
is claimed. Approved provider/controlled target and real browser session tests are
still required before identity-session milestone closure or controlled submission.

## Evidence

- `frontend/tests/browser-auth.test.cjs`: real RSA signatures and Request/Response
  cookie round trip against a simulated provider; positive USER flow, rejection of
  SERVICE/HUMAN, claim/signature/nonce/subject/audience failures, callback tampering,
  origin/method/expiry/config invalidation, code-reuse denial, token/body limits,
  Basic authentication, local logout and current grant/identity rechecks.
- `frontend/tests/browser-session.test.cjs`: encryption, cookie and session bounds.
- `frontend/tests/i18n.test.cjs`: all64 page entrypoints and account labels covered.
- `npm run auth:check`: actual built Next production server; Chinese/English account
  and generic failure SSR, no login form in disabled mode, five route/method private
  denial checks. Also runs in CI after Cloudflare build.
- Current local full frontend541 tests passed; Next/OpenNext production build and actual
  route/SSR smoke checks are required before publication.

ROADMAP36/44=82%; modules100/100-demo/100-demo/100/89/60/17; seven plans
100/100/20/33/40/20/0. This records implemented but partially accepted session work,
not a completed external-provider or browser/revocation milestone.

Standards used: OpenID Connect Core1.0 errata2
https://openid.net/specs/openid-connect-core-1_0.html ; OAuth security BCP RFC9700
https://www.rfc-editor.org/rfc/rfc9700.html ; PKCE RFC7636
https://www.rfc-editor.org/rfc/rfc7636.html ; jose official implementation/docs
https://github.com/panva/jose . Dependency jose6.2.12 is pinned in the frontend lockfile.

### Historical OIDC browser flow rollout acceptance — 2026-10-06 (Asia/Shanghai)

PR#5 featureafb0b24871c7b1ddaafef15edad9ab85fc626633 merged as
625648a7a2658dcead4bab876a3ed49e19dc2b84. PR Actions37340442349 and exact-merge main
Actions37341096873 passed all four backend/frontend/acceptance/Workers
checks. Frontend533 passed; backend1250 passed with real PostgreSQL and no skips;
schema head0018_asr_evidence_index SQL/isolated round-trip passed. Production Next
route checks verified disabled503/405/no-store plus Chinese/English account and
generic failure SSR on both local and remote CI. Signed mock-provider50 cases
exercise code/PKCE/state/nonce/JWT claims, USER identity, logout, expiry and refusals.

Cloudflare main build00817246-ea03-4f99-821f-71c9ebe980fd succeeded
2026-10-05T16:30:13Z, version03d241d0-da85-4565-95a2-c76f69a93042.
PR Preview build/deployment succeeded2026-10-05T16:26:00Z,
deploymentdddb31d5-99b1-42b9-a574-2a9b9955d095:
https://codex-oidc-browser-flow-20261006-softwarelifecycle.whf969.workers.dev
Runtime Render /health/ready retry returned200, version0.18.28 and schema0018;
first request timed out. Live main /account from this execution environment
returned403/body error code1010. No security rule was changed or bypassed. Actual
live page access and real provider/browser acceptance remain unverified; deployment
success, signed mock flow and production local/CI SSR are separate evidence.

This final follow-up changes documentation only. No provider/secret/principal/grant
or public business-write settings were configured. Stateless logout remains local
cookie clearing; copied-cookie/server/provider-wide revocation remains pending.
ROADMAP36/44=82%; modules100/100-demo/100-demo/100/89/60/17;
seven plans100/100/20/33/40/20/0, delta0. Session partial implementation evidence is
recorded without closing the real-browser/revocation acceptance milestone. Next
approved provider/controlled target and real browser/revocation acceptance, then
controlled submission/recovery, all14 commands, corrections and operations.

## Server session registry — 2026-10-06 (Asia/Shanghai)

Migration0019 follows0018 and adds only browser_sessions. The API stores a session
UUID, principal UUID, SHA256 bearer digest, creation/expiry/revocation timestamps;
no token plaintext or refresh token is stored. Inner cookie envelope v2 includes
this UUID; legacy v1 session envelopes require a new login. Encryption format v1
and cookie attributes stay the same.

| API route | Method | Contract |
| --- | --- | --- |
| `/api/v1/security/me/browser-sessions` | POST | OIDC required, ACTIVE USER only; self token-bound UUID registration; expiry capped by JWT exp and900seconds;16 active sessions per principal |
| `/api/v1/security/me/browser-sessions/{session_id}/revoke` | POST | OIDC required, same USER and exact bearer digest; idempotent revocation;404 for absent/wrong owner/token |
| `/api/v1/security/me` and `/grants` | GET | With X-Browser-Session: check owner/token/unrevoked/unexpired registry row; invalid401; successful me echoes validated browser_session_id |

The frontend requires the validation echo for v2 session reads, so an API rollback
that ignores the header fails closed. Registration must return the exact requested
UUID/expiry before a cookie is issued. All requests use pinned server-only API,
no-store, no redirects, five-second timeout and16KiB response bounds. The self
identity projection never exposes token or session metadata to the browser.

Creation/revocation lock the principal row and recheck ACTIVE USER in the same
transaction. Each successful first change appends an authenticated audit event;
retries append no duplicate audit; audit failure rolls back the session change.
Audit payload holds expiry only. Revoked identifiers cannot be registered again.
The exact two metadata routes have a read-only exception, protected by required
OIDC even when AUTH_MODE is disabled. The14 business routes remain read-only
blocked and keep their scoped command contracts. Executable route inventories
cover14 business commands plus2 session controls, never silently omit routes.

Successful logout means confirmed200 revoked or404 session_not_found, followed by
local cookie clearing. Network,401, malformed or5xx responses keep cookies and
return generic503; HTML forms redirect to fixed /account?auth=logout_failed with
a translated retry message. Expired/invalid cookies can be cleared without a
network call. Session endpoints are private/no-store; self reads also vary on
X-Browser-Session. An endpoint outage prevents session reads and issuance.

Deploy backend/migration before enabling browser authentication. Migration downgrade
removes registry rows: do not downgrade an enabled authentication system. Before
rollback to an older frontend that accepts stateless cookies, disable browser auth
and rotate its session key; a frontend rollback alone can reintroduce old cookie
semantics. Restoring old configuration/key/database snapshots is an operational
credential boundary; deployment success does not verify that recovery procedure.
No automatic registry/tombstone purge or global token revocation is implemented;
rows may grow and require a reviewed retention/backup policy before production.
Interrupted issuance may leave an unused registration for at most15minutes of
active quota. Clock synchronization and representative-volume measurements remain
operator acceptance items.

Tests add signed-bearer SQLite/PostgreSQL ownership, expiry/quota, idempotent
registration/revocation, replay rejection and atomic audit rollback; real PostgreSQL
cases observe blocking for concurrent retry, last quota slot, concurrent revoke
and revoke-versus-register. Frontend tests cover copied-cookie replay, outage
handling, registration failure, legacy cookies and missing API validation proof.
Real provider and actual browser credential acceptance remain pending. ROADMAP
and seven plan percentages remain unchanged; this is implementation evidence.

Session guidance: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

## Session revocation rollout acceptance — 2026-10-06 (Asia/Shanghai)

PR#6 feature `1f9f828cc84c0f9f9ad2fa364a5e0cbbf9948692` merged as `a9e4765a7f8ed60e7abf70342cc0265a7e03f79a`.
PR Actions37386095765 and exact-merge main Actions37386533240 passed backend,
frontend, CI acceptance and Workers checks. Both complete backend runs passed1285,
with107 PostgreSQL-module cases and no skips; additional parametrized PostgreSQL
cases are included in the total. Frontend541 passed. Single Alembic head0019,
full upgrade/downgrade SQL and isolated0019→0018→0019 round trip passed. Actual
production Next checks cover unavailable/login-error/logout-error SSR in Chinese
and English and five private/no-store disabled route denials. Real PostgreSQL
blocking proves retry/quota/revoke/revoke-versus-register serialization.

Cloudflare PR Preview build/deployment succeeded at2026-10-05T23:05:28.428Z,
deploymentbbddba4c-99b2-4039-998b-6d7117264dc8:
https://codex-browser-session-revocation-20261006-softwarelifecycle.whf969.workers.dev
Main build e144df91-5d82-4ae6-9316-921ca4eef6fb passed at23:08:37Z,
Worker version417daa7f-53bc-485c-b7d2-9c37adafeaa4.
Render /health/ready returned200 / API0.18.29 /0019_browser_sessions. Both new
session POST controls returned401 oidc_not_enabled with private,no-store;
a harmless random-release Snapshot POST returned403 read_only_mode. No business
row, principal, grant, provider or secret was created. Render provider deployment
ID/commit metadata was not independently inspected; the runtime version/schema
are observed evidence. Live main /account and /auth/session from this environment
returned403/error1010; no access rule was changed or bypassed. Successful builds,
local/CI production SSR and simulated signed-provider flow do not constitute real
provider or actual live browser credential acceptance.

This final follow-up updates documentation only; the verified code merge above
remains the feature/CI baseline. ROADMAP36/44=82%; module percentages
100/100-demo/100-demo/100/89/60/17; seven plans100/100/20/33/40/20/0, delta0.
Server session revocation is now implemented/tested; approved provider/controlled
target, actual browser login/logout/expiry and credential/recovery acceptance,
audited identity/grant administration, controlled submission/outcome recovery for
all14 commands, broader corrections and operations remain. Before older-frontend
rollback disable browser auth and rotate its session key; registry retention and
backup/restore acceptance are still required before production.
