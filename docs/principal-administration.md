# Audited local principal administration — API 0.18.32

This package adds local identity registration and enable/disable controls. It does
not create provider accounts, roles or grants, configure a provider, or implement
an administration UI. Public sample deployments remain read-only with OIDC disabled.

## Controls

Both controls require writable mode, verified OIDC, an exact ACTIVE local actor,
current PLATFORM_ADMIN and, when supplied, a valid token-bound X-Browser-Session.
Request bodies forbid additional fields, including client-declared actors and roles.
Reasons are printable, trimmed and 5–500 characters. event_no is 1–50 ASCII
letters/digits/dot/underscore/colon/hyphen, starting with a letter or digit.
Success, denial and validation responses use private,no-store and Vary:Authorization.
Responses that reach the route also vary on X-Browser-Session; early middleware
denials are independent of that optional header. No own-session read-only exception applies to these controls.

| POST route | Required body | Effect |
| --- | --- | --- |
| `/api/v1/security/admin/principals` | event_no, reason, principal_id UUID, subject, principal_type USER/SERVICE, display_name | Registers a DISABLED local identity with no grants and no email; issuer comes only from current server configuration |
| `/api/v1/security/admin/principals/{principal_id}/status` | event_no, reason, expected_status and different status ACTIVE/DISABLED | Changes one exact non-platform-admin principal; disabling revokes every previously unrevoked registered browser session in the same transaction |

Subject is an opaque exact string (1–500 characters). Display name is 1–200.
Surrounding whitespace, C0 controls and DEL are rejected instead of silently
normalizing identity references. Registration duplicates by UUID or exact issuer/sub
return409; they never attach new requests to an existing identity. Missing or
oversized configured issuer fails503. Only disabled-first registration is allowed;
activation requires a separate audited transition. Activation alone grants no roles.

Responses contain only principal_id, applied_status, current_status, replayed,
audit_event_no and revoked_browser_sessions. No subject/issuer/name/email/token is
returned. Registration audit binds the exact canonical request and configured issuer
with a SHA256 digest; it does not duplicate provider identifiers or display name.
This digest is retry evidence, not a credential or anonymization guarantee. The
reason and local principal UUID/type are retained in append-only audit. Callers
must keep provider identifiers, credentials and secrets out of reasons.

## Preconditions, retries and atomicity

All PLATFORM_ADMIN identities are protected from status changes, including self,
other administrators and already-disabled administrators:409 admin_principal_protected.
This intentionally defers administrator lifecycle, first-admin bootstrap, last-admin
protection and recovery policy. It does not silently downgrade a protected admin.
No role-grant write API exists in this package. Out-of-band SQL grant edits are not
part of the concurrency protocol and must not race these controls.

An expected-status mismatch returns409 principal_status_conflict; missing identity
returns404. Audit keys are globally unique. A replay requires the same actor UUID,
exact entity ownership/type/reference and same canonical request. A changed reason,
identity fields, transition or actor returns409. Duplicate concurrent registrations
may return409 principal_registration_conflict when uniqueness is the rejecting
constraint, including a concurrently reused audit key. Every conflict rolls back.

A successful old request returns its historical applied_status and revocation count,
plus separately read current_status. It never reapplies its transition or revocations.
Thus registration replay after enable does not disable, and disable replay after
re-enable does not revoke newly registered sessions. Current status is an observation
in READ COMMITTED, not a reservation against a later transaction.

Actor identity and its current admin grant are locked first. Status changes reject
platform-admin targets before locking the target to avoid actor/target lock cycles,
then lock and refresh the exact recipient principal and recheck admin protection.
Own-session register/revoke use that same recipient lock. New registrations use
actor locks plus database UUID and exact issuer/subject uniqueness. Different admins
racing on a recipient serialize; same request/admin replays once, changed key sees
stale state, different actor cannot claim another actor's replay. Audit insert, local
identity change and session revocation commit together; failures roll everything back.
No schema migration is required; head remains0019_browser_sessions.

## Revocation boundaries

Disable marks all unrevoked registry entries, including expired ones, with one bulk
UPDATE and one principal status event with a count. Already-revoked timestamps and
other principals' sessions are preserved. No session IDs/digests are copied into
principal audit, and no synthetic per-session revoke events are generated. Roles and
membership status are retained; disabled identity denies new authenticated requests.
Re-enable restores access according to those retained grants and still-valid provider
bearer tokens, but previously registered browser cookies stay revoked. A fresh browser
login/session is needed. Provider token revocation/password/reset is not implemented.

This does not cancel already-authorized in-flight business transactions. A request
or read that passed authorization before disable may finish. Principal/session
commands specifically serialize on the recipient lock; business commands do not all
share it. Provider configuration and actual administrator/browser credential tests
remain required for full acceptance.

## Evidence

`backend/tests/test_principal_admin.py` runs signed HTTP acceptance against SQLite
and migrated PostgreSQL: registration, USER/SERVICE lifecycle, exact replay after
later transitions, conflicts, protected administrators, validation/denials, copied
cookie rejection after re-enable, retained memberships, minimal evidence and rollback
after audit insert. `test_principal_admin_postgres.py` forces real database blocking
for competing administrators, duplicate identity registration and session registration
versus disable in both orders. The CI suite rejects skipped PostgreSQL tests.

The14 domain commands retain their fixed inventory. Two own-session controls and
three admin controls have separately reviewed inventories. Full identity-admin
milestone remains open: role creation, global-admin/bootstrap/recovery policy,
bilingual management UI and approved-provider/actual-administrator acceptance.
