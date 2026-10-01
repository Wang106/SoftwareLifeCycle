# Security and identity baseline

## Current status

The repository has a provider-neutral identity/scoped-role model and configurable OIDC authentication for write requests. With `AUTH_MODE=oidc`, a write requires a valid Bearer token and an ACTIVE local principal matching `(issuer, subject)`. Project/software authorization is **not** yet enforced. The public sample API must continue using `READ_ONLY_MODE=true`.

## Authentication boundary

The boundary is an external OpenID Connect (OIDC) provider such as a company SSO. The API validates a configured issuer's signing key through its explicit HTTPS JWKS URL, the configured audience, expiry/issued-at claims and a fixed asymmetric-algorithm allow-list. It then maps the stable `(issuer, subject)` pair to a local `security_principals` record.

The database intentionally stores no passwords, password hashes, access tokens, refresh tokens or client secrets. Selecting and configuring an actual OIDC provider remains a deployment decision.

There is currently no principal/grant administration API and Seed creates no identities or grants. Grant creation, suspension and revocation must become authenticated, narrowly authorized and auditable before operational use.

`principal_type` distinguishes:

- `USER` — a human identity from the configured issuer;
- `SERVICE` — a non-human workload identity issued through an approved machine-to-machine flow.

Disabled principals must be denied even if the external token is otherwise valid.

## Authorization scopes

| Scope | Roles | Meaning |
| --- | --- | --- |
| Global | `PLATFORM_ADMIN` | Administrative override; assignment must be exceptional and audited |
| Global | `AUDITOR` | Cross-scope read access; no write authority |
| Software product | `SOFTWARE_VIEWER` | Read a standard/software-product scope |
| Software product | `SOFTWARE_MAINTAINER` | Maintain standard-release evidence and snapshots |
| Project | `PROJECT_VIEWER` | Read a customer-project scope |
| Project | `CONTRIBUTOR` | Add project evidence, test drafts and trace assignments |
| Project | `REVIEWER` | Record formal review and impact judgments |
| Project | `RELEASE_AUTHORITY` | Record release decisions after approved workflow |
| Project | `DISTRIBUTION_AUTHORITY` | Create controlled delivery/distribution records |
| Project | `PRODUCTION_AUTHORITY` | Create production authorization scope |
| Project | `PRODUCTION_OPERATOR` | Record deployment, actual software, changeover and batch activity |

`PLATFORM_ADMIN` is the intended universal override. Other roles apply only to active grants in the exact software product or project resolved from stored foreign keys. Client-supplied customer/project identifiers are not authorization evidence.

## Planned write policy

`backend/app/write_contracts.py` records the planned role set for every current write route. Examples:

- snapshot creation: software maintainer or project contributor, depending on release type;
- approval action and issue-impact judgment: reviewer;
- release decision: release authority;
- delivery/distribution: distribution authority;
- production authorization: production authority;
- deployment/changeover/batch: production operator.

These roles are design targets until authorization checks are attached to the routes. Current contracts state `authentication=OIDC_WHEN_ENABLED` and `authorization=NONE`. `AUTH_MODE=disabled` preserves controlled local development compatibility and must not be used to expose writes publicly.

## Required enforcement sequence

1. Select and configure the approved OIDC issuer/audience/JWKS URL; define signing-key rotation and outage behavior.
2. Resolve the target software/project from stored relationships.
3. Require an active scoped role or the exceptional global admin role.
4. Derive audit actor identity from the authenticated principal, preserving old declared actor strings as historical data.
5. Add wrong-project and insufficient-role integration tests in addition to the existing token/principal denial tests.

No public write form or non-read-only deployment should be enabled before the remaining sequence is complete.

## OIDC configuration

Set `AUTH_MODE=oidc` together with `OIDC_ISSUER_URL`, `OIDC_AUDIENCE` and an explicit `OIDC_JWKS_URL`. Optional settings are `OIDC_ALGORITHMS` (approved asymmetric algorithms only), `OIDC_LEEWAY_SECONDS` and `OIDC_JWKS_TIMEOUT_SECONDS`. URLs must use HTTPS and cannot contain credentials, query strings or fragments.

The JWKS URL is operator configuration, never a token-provided URL. Invalid/missing tokens, invalid claims, unknown principals and disabled principals fail with HTTP 401 and a Bearer challenge. `READ_ONLY_MODE=true` takes precedence and returns the existing HTTP 403 without contacting the identity provider.
