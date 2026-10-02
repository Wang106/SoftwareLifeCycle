# Security and identity baseline

## Current status

The repository has a provider-neutral identity/scoped-role model plus configurable OIDC authentication and authorization for write requests. With `AUTH_MODE=oidc`, a write requires a valid Bearer token, an ACTIVE local principal matching `(issuer, subject)` and the exact active project/software role required by that route. Every current write records an atomic audit event bound to that principal. The public sample API must continue using `READ_ONLY_MODE=true` because no approved provider is configured and legacy no-key writes retain weaker semantics; controlled UI, provider-backed acceptance and operations remain unfinished.

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
6. **Implemented for all 14 current keyed routes:** Snapshot and production-batch creation now support optional request-ID replay and PostgreSQL row locks. Approval actions and release decisions also support these safeguards; Delivery, Distribution and Production Authorization also implement optional-key replay and locks; Deployment and Changeover now also implement optional-key replay and locks. Actual reporting now provides optional request-ID replay, expected-version conflict protection and audited corrections; see 0.18.0 below.
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
commit. Failure rolls back both and releases locks. The first package controls cover Snapshot and Batch;
no OIDC provider, public write UI or production readiness is claimed. Public staging
remains `READ_ONLY_MODE=true`.

## Approval retry trust boundary

Approval Action and Release Decision replays require the same authenticated audit
principal, full effective display identity and retained declaration. A matching
UUID or display name cannot substitute for identity. HTTP exact active role checks
run before replay, including denial after grant suspension. The original response
is recoverable after workflow state changes, without bypassing current permission.
Keyed actions require an explicit expected step; unkeyed compatibility calls still
act on the current step and do not provide the same retry guarantee. ApprovalRequest
locking serializes actions and decisions through atomic audit commit. No approved
OIDC provider or public write capability is introduced; staging remains read-only.

## Distribution-chain retry trust boundary

Current HTTP authorization and actor resolution run before every replay. Delivery
and Distribution require exact release/project distribution authority; Authorization
requires both the supplied project and stored distribution-chain production authority.
An absent/suspended scoped grant denies replay. Request IDs do not grant access:
principal, effective/full display name and retained declaration must match audit
identity, including auth-disabled versus authenticated mode changes. Delivery retains
`created_by` as declaration while storing the trusted actor in OIDC mode.

Fresh Delivery retains frozen artifact membership, INTERNAL_ONLY denial and recipient/
purpose policy checks; fresh Authorization retains exact release/snapshot, customer/
project, recipient, purpose and finite-limit validation. Locks coordinate supported
latest-release-decision checks. Recovery of an already committed keyed write does not
recheck mutable parent eligibility, but never bypasses current HTTP permission.
No provider, public write UI or write-enabled public target is configured; staging
continues to be sample-only and read-only.

## Production retry trust boundary (0.17.0)

Every Deployment/Changeover HTTP retry still checks the current exact active project
PRODUCTION_OPERATOR grant before trusted actor resolution and stored evidence lookup.
Replays bind all audit identity fields, including principal, full display identity,
declaration and authentication mode. A request UUID or matching name grants no access;
suspended grants deny recovery. Legacy no-key calls remain compatible with duplicate
business-number rejection and existing disabled-auth behavior.

Deployment creation verifies current approved authorization and exact active site/line
scope after parent locks. Changeover retains source/target release rules. Shared
Deployment locking coordinates actual reporting, Changeover and Batch through audit
commit; it does not reject a stale client's actual overwrite. Those gaps at 0.17.0 are addressed by the 0.18.0 keyed contract below; legacy paths remain weaker. Public staging remains read-only,
without an approved provider, login/grant administration or public write forms.


## Actual-report trust boundary (0.18.0)

Every report/replay passes current exact active project PRODUCTION_OPERATOR scope
and trusted actor resolution before retry evidence. Full principal/display/declaration
and authentication-mode binding remains required; key possession grants no permission.
Keyed calls require expected_version, and replacement reports require a nonblank
correction reason. The atomic append-only event preserves before/after software,
status, time, version and reason; it does not authorize physical flashing rollback,
batch reversal or general revocation. Matching replay recovers the original result
before current-state checks, without changing the current deployment projection.

All 14 current routes now declare request-ID, row serialization, exact scope, actor
and atomic audit contracts. Legacy no-key reporting may still overwrite without a
precondition, so controlled multi-user clients must adopt keyed/versioned reporting.
Approved OIDC/provider-backed acceptance, browser login, audited grants and controlled
write UI remain unfinished. Public staging stays sample-only and read-only.

## Request-preparation boundary

The public /commands workspace performs local validation/review/clipboard export
only. It has no write transport, token/login inputs, API-host picker, mutation proxy
or persistence. Prepared/copied requests do not prove permission or successful writes.
Current API READ_ONLY_MODE, OIDC, exact scope, trusted actor and audit behavior is
unchanged. Authenticated submission must wait for approved identity/session and
a controlled target; a frontend must not proxy auth-disabled public writes.

## Governance request preparation

Approval/Decision preparation requires explicitly entered declared operator text and labels it as evidence, never authentication or a scoped grant. Exact step/context links can be stale; the API still enforces REVIEWER/RELEASE_AUTHORITY, trusted actor binding, row locks and atomic audit for every call. Readiness/decision text is a declaration rather than a security or eligibility check. No login/token field, transport, persistence or public-write permission is added.

## Evidence/reference request preparation

Impact/assignment/resource preparation never establishes candidate membership, scope, identity, test execution or file access. Resource positions are inert text, with no URL fetch, local/UNC open or upload; credentials/control characters are rejected for WEB_URL. Supplier/customer targets still require PLATFORM_ADMIN in OIDC mode. Explicit declarations never replace trusted principals. Public read-only, current scoped guards, actor binding and atomic audit remain unchanged.

## Distribution-chain request preparation

Delivery/Distribution/Authorization forms prepare existing keyed bodies with explicit
revision/artifact UUIDs, exact recipients/purpose and customer/project/site/line scope.
Finite limits and unlimited null require explicit choices; no default quota is inferred.
The backend still selects/validates the approved snapshot and policies under its current
locks; authorization creation stays DRAFT. Distribution creation does not send files or
acknowledge receipt. Existing exact roles, trusted actor binding, retry and atomic audit
remain unchanged. EVT-DP-/EVT-DS-/EVT-PA- links use UUID hex. No API/schema/migration,
transport, login or public-write setting changes; API 0.18.0/head 0017 remain. See
`docs/controlled-write-ui.md` for preparation subsets and remaining submission work.

## Final three request-preparation forms

Test Release, Deployment and Changeover complete 14/14 preparation forms using
existing request bodies, immutable confirmation/copy and exact UUID context.
Test Release remains DRAFT; Deployment remains PENDING; Changeover appends history
without physical flashing or actual-software updates. EVT-TR- retains hyphenated
UUIDs; EVT-DPLOY-/EVT-CO- use UUID hex. No backend/API/schema/migration, role/actor,
retry/transaction, authentication or public-write settings change. Submission and
outcome recovery remain pending. See docs/controlled-write-ui.md for limits.

## Deployment profile read migration — 2026-10-02

The frontend deployment detail now reads the exact `/deployments/{deployment_no}/profile`
(API 0.18.1), which omits unbounded batch/changeover/decision arrays. Existing indexed
`deployment_id` count queries supply full history totals; linked bounded catalogs
review exact deployment history and exact delivered release/snapshot decisions.
Stored status and software-pair observation remain separate; missing context stays
null. Counts are observations, not quotas, authorization or a consistent write receipt.
No migration is needed: existing child foreign-key indexes serve count scope.
Legacy endpoints retain their old shapes. All 14 write contracts, exact scope,
trusted actors, replay/locks and atomic audit are unchanged; public staging remains
read-only and provider-backed submission/other consumer migrations remain pending.

## Profile read boundary — 2026-10-02

Authorization/distribution profiles follow the existing public sample read policy.
They do not authenticate an operator or establish permission through a count,
acknowledgment, stored approval or catalog observation. Exact-role authorization,
actor binding, keyed retry/locking and atomic write audit remain unchanged.
Public staging remains read-only; company-data read policy/provider setup is pending.

## Delivery revision read migration — 2026-10-02

The new GET profile/artifact page retains the public sample-read boundary, omits storage_reference and never fetches files or linked locations. Counts, recorded policy decisions and controls do not establish current permissions, approval, sending or receipt. All 14 command guards, trusted actors, keyed replay/serialization and atomic audit are unchanged. Public staging remains read-only; provider-backed submission and company-data read controls remain pending.

## Default Chinese and English interface — 2026-10-02

All 63 page entry points and all 14 preparation forms now use the shared bilingual
interface, default Chinese. The language-only cookie persists the selected preference;
UI switching preserves form state, request_id, raw enum values, JSON and exact links.
Stored evidence and identifiers stay original; known demo summaries have display translations. See [interface contract](docs/i18n.md).
API 0.18.3 and schema 0017_deployment_actual_version are unchanged; no migration.
Public staging remains read-only. Authenticated submission and OIDC configuration are
still pending. Roadmap checked scope stays 34/44 (77%); bilingual coverage is an
additional UI requirement, not completion of the Phase 6 submission gate.

Verification: frontend 292 passed (78 localization/coverage checks plus 214 command
checks); final Next/OpenNext production build passed. Full backend: 733 passed,
3568 existing warnings, no skips, including 103 real PostgreSQL integration/concurrency
tests. Local SSR: 126 page/language checks, invalid preference fallback and stable raw
input/option values for 14 forms. Live bilingual/persistence/immutable-request checks passed; rollout evidence is recorded in HANDOFF.md.

## ASR summary read boundary — API 0.18.4

The new summary and authorization_release_id catalog filter are sample read paths,
not role grants or authenticated write authority. All 14 write guards, exact scope,
trusted actor binding, serialization/replay and atomic audit remain unchanged.
Release-count observations do not grant permission, reserve finite capacity or prove
snapshot/physical flashing/approval. No child notes are loaded by the summary.
Public staging remains sample-only/read-only; company evidence still requires approved
identity, network/data access and environment review. No write was enabled for this package.

## Pinned evidence read boundary — API 0.18.5

The new read routes verify exact APPLICATION release and selected Snapshot ownership;
query scope is not authorization. Projections omit artifact storage references and DVP
actual-result bodies, retain known evidence UUIDs and do not infer readiness, approval
or current permission. All 14 write guards, trusted actors, serialization/replay and
atomic audits are unchanged. The index-only 0018 migration grants no new access.
Default Chinese/English presentation leaves identifiers and request exports untouched.
Public staging stays sample-only/read-only; protected company reads still need approved
identity/network/data/environment review.

## Coverage read aggregation — API 0.18.6

Coverage SQL preserves exact software/project and release/Snapshot read scopes. It loads
no change-point descriptions, SCR requirement text or DVP actual_result body. Required
DVP bindings and any-PASS semantics stay unchanged; counts never confer approval/write
authority. This does not add read authentication or retire all legacy rich profiles.
All 14 write-route role/actor bindings, request-ID locks and atomic audits remain
unchanged and covered by complete PostgreSQL regressions. No migration, login/session
or grant administration is added; public staging remains READ_ONLY_MODE=true.
