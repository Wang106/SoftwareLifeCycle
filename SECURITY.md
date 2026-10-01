# Security and identity baseline

## Current status

The repository now has a provider-neutral identity and scoped-role data model. It does **not** yet authenticate requests or enforce authorization. The public sample API must continue using `READ_ONLY_MODE=true` until token validation, scope resolution and permission tests are implemented.

## Authentication boundary

The intended boundary is an external OpenID Connect (OIDC) provider such as a company SSO. The API will validate an issuer-signed token and map its stable `(issuer, subject)` pair to a local `security_principals` record.

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

These are design targets only until an authentication dependency and authorization checks are attached to the routes. Current contracts still state `authentication=NONE` and `authorization=NONE`.

## Required enforcement sequence

1. Select the OIDC issuer and accepted audience; define signing-key rotation and outage behavior.
2. Validate token signature, issuer, audience, expiry and subject; never trust unsigned identity headers.
3. Resolve the active local principal from `(issuer, subject)`.
4. Resolve the target software/project from stored relationships.
5. Require an active scoped role or the exceptional global admin role.
6. Derive audit actor identity from the authenticated principal, preserving old declared actor strings as historical data.
7. Add positive, unauthenticated, disabled-principal, wrong-project and insufficient-role integration tests.

No public write form or non-read-only deployment should be enabled before this sequence is complete.
