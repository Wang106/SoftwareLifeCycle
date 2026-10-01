# Security and identity baseline

## Current status

The repository has a provider-neutral identity/scoped-role model plus configurable OIDC authentication and authorization for write requests. With `AUTH_MODE=oidc`, a write requires a valid Bearer token, an ACTIVE local principal matching `(issuer, subject)` and the exact active project/software role required by that route. Every current write records an atomic audit event bound to that principal. The public sample API must continue using `READ_ONLY_MODE=true` because no approved provider is configured and retry/concurrency controls remain incomplete.

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

`PLATFORM_ADMIN` is the universal write override and remains exceptional. Other roles apply only to active grants in the exact software product or project resolved from stored foreign keys. Client-supplied customer/project identifiers are not authorization evidence. Production authorization checks both the supplied project grant and the stored distribution/release scope before its domain service verifies that the complete chain matches.

Resource references resolve project scope through the target project, release, snapshot, SCR, DVP item, test release, DVP execution or all project-linked SCRs for an issue. Supplier/customer targets have no authoritative project/software relationship in the current schema, so only `PLATFORM_ADMIN` can attach those references in OIDC mode.

## Enforced write policy

`backend/app/write_contracts.py` records the planned role set for every current write route. Examples:

- snapshot creation: software maintainer or project contributor, depending on release type;
- approval action and issue-impact judgment: reviewer;
- release decision: release authority;
- delivery/distribution: distribution authority;
- production authorization: production authority;
- deployment/changeover/batch: production operator.

These roles are enforced whenever OIDC mode is enabled. Current contracts state `authentication=OIDC_WHEN_ENABLED` and `authorization=SCOPED_WHEN_OIDC`; a drift test also requires every registered write route to invoke an authorization guard. `AUTH_MODE=disabled` preserves controlled local development compatibility and must not be used to expose writes publicly.

## Authenticated audit actors

For every current route with `audit=ATOMIC_APPEND`, OIDC mode ignores request actor text as an authority. Domain actor fields and `audit_events.actor_name` use the authenticated principal's display name. The event also stores the exact `actor_principal_id`, full `actor_display_name` and original `declared_actor_name`; the latter is evidence of what the client submitted, not who was authenticated. Authenticated idempotent retries must match the original principal and declaration.

Historical/seed records and `AUTH_MODE=disabled` writes have a null principal reference and retain legacy declared/`Not recorded` behavior. There is no identity backfill. Snapshot creation and the four production command paths now use the same authenticated actor binding and atomic rollback guarantee as the other audited commands.

## Required enforcement sequence

1. Select and configure the approved OIDC issuer/audience/JWKS URL; define signing-key rotation and outage behavior.
2. **Implemented:** resolve the target software/project from stored relationships.
3. **Implemented:** require an active scoped role or the exceptional global admin role.
4. **Implemented:** derive audit actors from the authenticated principal and preserve request declarations separately for every current write.
5. **Implemented:** append audit events atomically for snapshot and production commands.
6. **Partially implemented:** Snapshot and production-batch creation now support optional request-ID replay and PostgreSQL row locks. Approval transitions and other writes still need safeguards.
7. Add provider-backed HTTP integration tests after a target provider is selected; unit/route-contract tests already cover wrong scope/role, suspended membership and actor mismatch.

No public write form or non-read-only deployment should be enabled before the remaining sequence is complete.

## OIDC configuration

Set `AUTH_MODE=oidc` together with `OIDC_ISSUER_URL`, `OIDC_AUDIENCE` and an explicit `OIDC_JWKS_URL`. Optional settings are `OIDC_ALGORITHMS` (approved asymmetric algorithms only), `OIDC_LEEWAY_SECONDS` and `OIDC_JWKS_TIMEOUT_SECONDS`. URLs must use HTTPS and cannot contain credentials, query strings or fragments.

The JWKS URL is operator configuration, never a token-provided URL. Invalid/missing tokens, invalid claims, unknown principals and disabled principals fail with HTTP 401 and a Bearer challenge. `READ_ONLY_MODE=true` takes precedence and returns the existing HTTP 403 without contacting the identity provider.

## Snapshot and Batch retry trust boundary

Authorization and trusted actor resolution run before any HTTP retry lookup.
Possessing a request UUID grants no access. An identical retry must match all stored
audit actor fields; another principal with the same display name, a changed retained
declaration, or an authentication-mode change conflicts. A suspended/revoked scoped
grant is denied even for an already successful request. Existing exact relationship
scope and `PLATFORM_ADMIN` rules remain unchanged.

Replay reads the original frozen/business result and does not repeat a write or
consume a second quota. New work still requires all domain checks. Release numbering
and shared production authorization quotas are serialized through atomic domain/audit
commit. Failure rolls back both and releases locks. These controls cover two commands;
no OIDC provider, public write UI or production readiness is claimed. Public staging
remains `READ_ONLY_MODE=true`.
