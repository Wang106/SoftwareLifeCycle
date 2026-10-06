# Scoped role registration — API 0.18.33

POST `/api/v1/security/admin/memberships/{scope}` registers one exact role for an
existing local identity and project/software target. Scope is PROJECT or SOFTWARE;
GLOBAL is not supported. Initial status is always SUSPENDED. A separate audited
existing status command must explicitly resume it before the role is effective.
There is no administrator UI or public write exception in this package.

## Request and response

Body: event_no, reason, membership_id UUID, principal_id UUID, scope_id UUID and role.
No status, actor, issuer, credentials, global-role fields or arbitrary additional
properties are accepted. Event keys/reasons use the same bounded validation as
principal administration: event_no1–50 ASCII key characters, printable trimmed
reason5–500. Caller UUID is the stable registration/retry identifier.

| Scope | Accepted roles | Exact target |
| --- | --- | --- |
| PROJECT | PROJECT_VIEWER, CONTRIBUTOR, REVIEWER, RELEASE_AUTHORITY, DISTRIBUTION_AUTHORITY, PRODUCTION_AUTHORITY, PRODUCTION_OPERATOR | Project UUID |
| SOFTWARE | SOFTWARE_VIEWER, SOFTWARE_MAINTAINER | SoftwareProduct UUID |

The current actor must be an ACTIVE verified OIDC local principal with current
PLATFORM_ADMIN. Writable mode is mandatory; optional X-Browser-Session must be valid
and token-bound. Body roles do not grant the caller administrative authority.
Recipient must be ACTIVE USER/SERVICE, reference the current configured issuer, and
have no PLATFORM_ADMIN grant. Self/admin recipient assignments are protected409
admin_recipient_protected pending the global-admin/bootstrap/recovery policy. Admins
already have the scope-free override; this restriction also avoids actor/recipient
principal-lock cycles. Disabled recipients409 recipient_inactive, issuer mismatch409
recipient_issuer_mismatch, missing principal/target404 and mismatched role/scope422.

Success returns membership_id, scope, principal_id, scope_id, role, applied_status,
current_status, replayed and audit_event_no. No identity subject/issuer/name/email,
token or raw ORM graph is returned. Registration audit binds the trusted actor UUID,
exact membership/scope/recipient/role and reason. No provider identities, secrets,
actual grants or environment configuration are provisioned by this development.

## Replay, uniqueness and transactions

An audit key is globally unique. Replay requires the original administrator UUID,
exact event type, entity type/id/canonical reference and identical normalized
request. Same UUID/role under a new key is a409 conflict, not implicit adoption.
Changed scope, recipient, target, role, UUID or reason is409 audit_event_conflict.
Duplicate membership UUID or principal/target/role409 membership_registration_conflict.
Distinct roles for the same target and equal role names on different targets are
separate grants; no inherited software/project permission is implied.

An old successful request returns historical applied_status SUSPENDED and observed
current_status. It never suspends a subsequently resumed grant, recreates a row,
adds a duplicate audit event or reactivates a disabled identity. Replay can succeed
when the recipient has subsequently become DISABLED: it reports existing evidence
without granting authority. Current actor authentication/admin/session checks still
apply. Unsupported out-of-band identity/global-role edits are outside this protocol.

Actor principal/current admin grant are locked first. Platform-admin recipients are
rejected before locking the recipient, then rechecked after locking/refreshing it.
The recipient lock is shared with principal enable/disable and own-session controls.
Different admins creating for that recipient serialize; exact original requests
replay once and other requests recheck uniqueness/identity state after waiting.
Database UUID and principal/target/role uniqueness provide final protection, including
cross-recipient UUID collisions. Input/authentication/admin-recipient protection and principal existence checks
precede replay; replay never bypasses them. Recipient state check, row insert and audit insert
are in one transaction; any failure rolls back all changes and releases locks.
A concurrent global audit-key insertion may reject through database uniqueness or
the audit service duplicate check as membership_registration_conflict. Existing
principal registration/status and membership status controls now also map late
audit-service duplicate errors to409 after rollback. Every such conflict leaves no unrecorded grant.

Principal disable versus creation has two accepted orders: disable first prevents
creation with409 recipient_inactive; creation first commits a suspended grant, then
disable leaves it suspended and blocks authenticated recipient requests. A later
status resume checks recipient ACTIVE independently. This does not cancel already
accepted business requests or change provider credentials. Existing status command
semantics and the14 fixed business-command inventory are retained.

Catalog/detail reads show new rows. Membership `/history` continues to include only
MEMBERSHIP_STATUS_CHANGED events; registration evidence is a separate append-only
MEMBERSHIP_REGISTERED audit event and is not presented as a status transition.
Replay current_status is a READ COMMITTED observation, not a reservation against
later status changes. No schema migration is needed; head remains0019.

## Validation and pending acceptance

Signed HTTP tests run against SQLite and migrated PostgreSQL. They cover all9
scoped roles, authorization before/after explicit resume, wrong target denial,
USER/SERVICE, private failures, duplicates/replays after later state changes, audit
insertion rollback and minimal responses. Real PostgreSQL overlap tests observe
actual blocking for competing administrators, global audit-key collision across
recipients and principal disable versus creation in both orders. CI rejects skips.

Public sample stays read-only/OIDC-disabled. Private success/denial/validation
responses are no-store and vary on Authorization; route-level responses also vary
on X-Browser-Session, whereas early middleware denials are independent of it.
GLOBAL AUDITOR/PLATFORM_ADMIN creation, first-admin/bootstrap and recovery policy,
bilingual management UI and real-provider/actual-administrator acceptance remain
pending. This completes a scoped registration slice, not the full identity-admin
milestone. Module/plan acceptance percentages do not change for partial evidence.
