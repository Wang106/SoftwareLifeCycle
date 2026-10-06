# Global role lifecycle — API 0.18.34

Schema0020_global_role_status adds ACTIVE/SUSPENDED to exact global role assignments.
Existing rows and legacy default inserts remain ACTIVE; the administrative registration
API explicitly creates SUSPENDED rows. No actual identities, grants, provider or
secrets are provisioned. Public sample remains read-only and OIDC-disabled.

## Controls

POST `/api/v1/security/admin/global-roles`: event_no, reason, grant_id UUID,
principal_id UUID and role PLATFORM_ADMIN/AUDITOR. Existing ACTIVE USER/SERVICE must
belong to the configured issuer. Initial status cannot be supplied. Duplicate UUID
or principal/role is409; distinct roles are independent. This does not bootstrap
an administrator: an existing effective administrator is always required.

POST `/api/v1/security/admin/global-roles/{grant_id}/status`: event_no, reason,
expected_status and status (ACTIVE/SUSPENDED, different). Resume requires the
recipient to be ACTIVE in the configured issuer. Stale expected state409. Suspending
PLATFORM_ADMIN requires another ACTIVE PLATFORM_ADMIN assignment whose principal
is ACTIVE in the configured issuer. Ineffective/suspended/disabled/wrong-issuer
assignments and AUDITOR cannot satisfy last-admin protection. Self suspension is
permitted with another effective administrator. A self-suspended actor loses access
on subsequent calls, including retries; reauthorization is not bypassed by replay.

Both endpoints require writable mode, verified OIDC, current ACTIVE local actor and
ACTIVE PLATFORM_ADMIN. Optional browser-session header must be token-bound and
valid. Unknown extra fields, actor/issuer overrides and status on registration are
rejected. Event key1–50 ASCII characters; trimmed printable reason5–500 rejects
C0/DEL. Receipt includes grant UUID, GLOBAL scope, recipient UUID, role, historical
applied_status, observed current_status, replayed and audit key. No subject, issuer,
email, raw token or credentials are returned.

All global-admin overrides, administrator reads/writes and self grant counts/pages
now require ACTIVE global assignments. AUDITOR gains no administrative or business
write authority. Ordinary project/software roles remain independently effective.
Principal status controls continue protecting ANY PLATFORM_ADMIN assignment,
including suspended ones. Disable/enable cannot bypass global-role recovery policy.
Scoped registration continues rejecting recipients with any PLATFORM_ADMIN grant.
These restrictions remain intentional until a separate audited recovery contract.

## Transactions and replay

All six administrative write controls acquire PostgreSQL transaction advisory lock
(1397506887,1) before any principal/grant/recipient row lock. This database-wide gate
serializes administrative mutations, prevents cross-admin actor/recipient lock
cycles, and keeps the last-admin count and mutation in one transaction. Actor and
recipient records are refreshed after locks. Own-session controls share recipient
principal row locks but do not acquire the admin gate. Ordinary business writes and
private reads do not acquire this gate. SQLite verifies sequential behavior only;
real overlap evidence comes from migrated PostgreSQL. This deliberately trades
admin-write throughput for explicit consistency, without serializing business work.

Each successful control inserts an actor-bound GLOBAL_ROLE_REGISTERED or
GLOBAL_ROLE_STATUS_CHANGED event, entity_type GLOBAL_ROLE with exact UUID and
canonical reference, in the same transaction. Globally unique audit key replay
requires the original actor, exact event/entity/ref and normalized request payload.
Changed ownership/input conflicts409. Replay reports old applied status/current
observed status without repeating mutations or audits. Replay of registration can
observe a subsequently disabled recipient, but never enables it. Audit insert,
late AuditEventError or uniqueness failure rolls back all state and releases locks.
Current status is a READ COMMITTED observation, not a future-state reservation.

## Read contract and migration

Administrator GLOBAL catalog/detail now returns status ACTIVE/SUSPENDED instead
of null; effective requires ACTIVE assignment and ACTIVE principal. GLOBAL status
filter is supported, scope_id remains invalid. All scopes report status history
support. GLOBAL history includes only GLOBAL_ROLE_STATUS_CHANGED with exact
GLOBAL_ROLE entity/UUID/ref; coverage GLOBAL_ROLE_STATUS_CHANGED_ONLY. Registration
is audited separately. Bounds, SQL scalar projection, bounded reason and privacy
remain unchanged. Self read shape is unchanged and excludes suspended global roles.

Migration0020 preserves existing assignments as ACTIVE and validates status at the
database layer. Downgrade rejects if ANY global assignment is SUSPENDED, because
removing status would restore that assignment. Empty/all-ACTIVE round trip works.
Operators must review role state before a schema rollback; the migration never
implicitly resumes/deletes roles to permit rollback. Out-of-band SQL, provider
availability/token expiry, in-flight accepted reads/business writes and disaster
recovery are outside the last-admin transaction guarantee. Counting an effective
local administrator does not prove that person can currently log into the provider.

## Remaining acceptance

First-administrator bootstrap, independent recovery/break-glass policy and audited
operator procedure remain pending. No actual bootstrap/recovery is attempted.
Bilingual management UI and approved-provider/actual-admin browser acceptance remain
pending. This is another identity-admin slice, not full milestone completion.
Seven module/plan percentages remain unchanged until their acceptance items pass.

## CI serialization regression

The initial full PostgreSQL run passed all100 new cases but exposed4 prior race
assertions that assumed concurrent admin transactions passed entry key checks.
The shared gate now makes the first committed audit visible before the second
entry check. Cross-recipient same-key requests deterministically reject
audit_event_conflict409 without state/audit mutation. Principal duplicate UUID/
subject overlap now uses distinct audit keys to independently prove uniqueness,
and an additional different-actor same-key case verifies exact audit ownership.
Late unrelated audit writers still exercise AuditEventError rollback separately.
These expected semantic changes are explicitly tested; revised and exact-main full CI passed1901 cases with no skips.

## Accepted deployment

PR#12 merged456d41c1d0f7d4559737fc0d0fdc2fef51e4fa2a. Revised PR CI37434734541
and exact-main CI37435556865 each passed1901 backend,159 PostgreSQL-module cases
plus parametrized PostgreSQL, no skips; frontend541 and Worker build passed.
Current main HTTP/SSR5 checks and API readiness/private-read/new-global-write
protection5 checks passed; precise timestamps and initial failed probes are retained
in HANDOFF.md/PROJECT_STATUS.md. Observed runtime0.18.34/schema0020; actual
provider/browser/admin acceptance and operator recovery remain pending.
