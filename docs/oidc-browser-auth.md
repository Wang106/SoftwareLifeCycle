# OIDC browser authentication implementation — 2026-10-06 (Asia/Shanghai)

Codex implementation; API version0.18.28 and database head0018_asr_evidence_index
are unchanged. Public staging remains sample-only/read-only. No provider or secret
has been configured or provisioned by this change.

## Implemented contract

| Frontend route | Method | Behavior |
| --- | --- | --- |
| `/account` | GET | Default Chinese / selectable English; unavailable, signed-out, signed-in or generic failure view |
| `/auth/login` | POST | Same-origin start; encrypted five-minute pending cookie; redirect to configured provider |
| `/auth/callback` | GET | Validate pending state/config/expiry, redeem code with PKCE, verify tokens, resolve active local USER, issue session |
| `/auth/session` | GET | Current projected identity/grant counts; recheck backend every time; clear invalid session |
| `/auth/logout` | POST | Same-origin local cookie clearing; redirect to fixed account page |

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
Logout clears this browser's session and pending cookies only. A copied stateless
session may remain usable until expiry while token/principal remains valid.
Provider-wide logout, refresh, immediate server-side session revocation and replay
storage remain future work; no completed real-provider/browser credential acceptance
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
- Local full frontend533 tests passed; Next/OpenNext production build and actual
  route/SSR smoke checks are required before publication.

ROADMAP36/44=82%; modules100/100-demo/100-demo/100/89/60/17; seven plans
100/100/20/33/40/20/0. This records implemented but partially accepted session work,
not a completed external-provider or browser/revocation milestone.

Standards used: OpenID Connect Core1.0 errata2
https://openid.net/specs/openid-connect-core-1_0.html ; OAuth security BCP RFC9700
https://www.rfc-editor.org/rfc/rfc9700.html ; PKCE RFC7636
https://www.rfc-editor.org/rfc/rfc7636.html ; jose official implementation/docs
https://github.com/panva/jose . Dependency jose6.2.12 is pinned in the frontend lockfile.
