# First administrator and offline recovery — API0.18.35

The backend now ships a default-disabled LOCAL operator CLI, not an HTTP endpoint
or startup/seed task. No actual provider, identity, grant, secret or operator setting
is provisioned by this development. Public sample remains read-only/OIDC-disabled.
Do not run this protocol against the public sample or company data during development.
This backend implementation does not constitute actual operator/provider acceptance.

## Trust and activation

An approved infrastructure operator with authorized process/database access executes
`python -m app.admin_operator`. This authority is independent of OIDC so an environment
with zero administrators can recover. It is not a verified human/provider identity.
Audit actor_principal_id is null; actor_name uses a digest of OS effective UID,
hostname and PostgreSQL current_user. Payload explicitly states
LOCAL_OPERATOR_PROCESS_NOT_OIDC_HUMAN. Declared approval_ref identifies an external
approval record; the CLI does not verify its existence, reviewer or human identity.
Provider account/subject ownership and operator authorization require independent
approved procedure before an actual run. Possessing the file alone grants no
HTTP capability, and the process still requires target database credentials/access.

All of ADMIN_OPERATOR_ENABLED=true (default false), READ_ONLY_MODE=false and complete
validated AUTH_MODE=oidc configuration are required. Gates run before any DB connection
in the CLI. Only PostgreSQL is executable; SQLite is used for sequential service tests.
Schema must be the configured single head0020, and alembic_version/security_principals/
global_role_assignments/browser_sessions/audit_events must resolve to actual tables
in the same current_schema. The CLI never runs migrations or changes provider config.

Enable the operator flag only in a reviewed temporary local process environment on
an approved controlled target. Keep the web service/operator capability disabled in
ordinary deployments. The flag is not a substitute for OS/database access controls.
Never place credentials, tokens or secrets in request reason/display name/approval
reference, command line or exported logs. The request file contains an opaque subject
and name for bootstrap; restrict its filesystem access and handle it as identity data.

## Reviewed plan and requests

From backend, `python -m app.admin_operator plan` reads bounded scalar counts and
returns target_fingerprint, issuer_fingerprint, schema revision, effective/admin
assignment counts and availability flags. It does not write or reserve that state.
No raw DSN, password, subject, account directory or database role is printed.
Target fingerprint binds actual DB host/port/database/current_schema/current_user,
driver and configured issuer/audience/JWKS/algorithms. A changed target/provider
configuration rejects a previously reviewed request. Verify the actual approved
target independently; a SHA digest does not prove that an environment is approved.

`python -m app.admin_operator bootstrap --request /approved/request.json`
`python -m app.admin_operator recover --request /approved/request.json`

The examples name hypothetical files only; no actual request/identity is supplied.
Mutation JSON always requires event_no (ASCII1–50), printable trimmed reason5–500,
approval_ref (ASCII5–100), target_fingerprint (lowercase SHA25664), principal_id,
grant_id, acknowledge_privileged_change=true (strict boolean) and
expected_effective_admin_count=0 (strict integer). Extra fields are rejected.
Input read is bounded16KiB. Validation/database/unknown failures return fixed error
codes and exit1 without echoing raw input, credentials or stack traces; success is
minimal JSON exit0. Do not infer absence of a committed write from a lost response.

### First establishment

Bootstrap adds subject (opaque exact printable1–500) and display_name (exact printable
1–200). It requires NO PLATFORM_ADMIN assignment anywhere, including suspended,
disabled-recipient or other-issuer history. It requires a new principal UUID, new
configured-issuer subject and new grant UUID; it never adopts an existing identity.
Creates only a local USER identity and exact PLATFORM_ADMIN grant, explicitly ACTIVE,
with one atomic ADMIN_OPERATOR_BOOTSTRAP event. No provider account is created and
no email, credential, service principal, other role or scoped assignment is accepted.
This explicit first-admin exception differs from normal disabled/suspended-first API
registration. Existing non-admin identities require a separate reviewed policy; they
are not silently promoted by bootstrap.

### Recovery

Recovery supplies expected_principal_status ACTIVE/DISABLED and expected_grant_status
ACTIVE/SUSPENDED. There must be ZERO ACTIVE PLATFORM_ADMIN grants whose principals
are ACTIVE in the configured issuer (USER and SERVICE administrators both count).
Target must be an existing configured-issuer USER with that exact existing
PLATFORM_ADMIN grant. It cannot promote AUDITOR, create a new grant, move a grant,
adopt a service identity or migrate issuer/subject. Expected states must match.

Restores principal/grant ACTIVE and revokes ALL still-unrevoked target browser
sessions, including expired registry entries, in the same transaction and one
ADMIN_OPERATOR_RECOVER audit event. Existing revoked timestamps and other people's
sessions remain unchanged. Re-enabling a principal also restores its retained
project/software roles under existing policies; independently review these roles
and approved provider account/token security before a real recovery. This protocol
neither revokes provider tokens nor cancels already accepted business requests.
Fresh session registration after recovery is permitted by normal self-session rules.

## Locking, replay and operations

Both mutations share PostgreSQL advisory transaction gate(1397506887,1) with all6
API admin controls before principal/grant row locks. Zero-admin/history/uniqueness,
exact target states, identity changes, session revocation and actor-bound audit are
one transaction. Competing operators wait and recheck; only one distinct operation
can establish effective admin authority. Session registration shares recipient row
locks; sessions committed first are revoked, registrations after recovery are new.
Unrelated audit writers still can collide on globally unique event keys; all changes
roll back on database/audit-service conflicts and locks release on failures.

Same event key replay requires exact normalized request/operation, target/provider
fingerprint, original infrastructure context and exact audit entity/type/reference.
Audit stores a canonical request digest rather than duplicating subject/name/issuer.
Historical applied states and current observed states are returned; replay never
resumes a later suspended grant, re-enables a later disabled principal, revokes fresh
sessions again or repeats audit. The original revoked count is historical evidence.
A different host/UID/database role cannot adopt the event; container/host replacement
may therefore prevent mutation replay. Inspect original audit/current state through
approved access rather than assuming a new invocation should repeat the operation.

Public GLOBAL status history continues to project only GLOBAL_ROLE_STATUS_CHANGED,
not these operator/registration events. Operator evidence is separate append-only
audit, not a forged API principal or fabricated grant status history.

For an actual approved window: independently verify target/provider/subject and
approval, capture the read-only plan, review the exact file, apply once, verify receipt
and append-only event, verify actual approved administrator login/permissions, then
remove the temporary operator flag and protect/remove the sensitive request file
according to approved retention policy. If verification fails, close the window and
investigate; do not bypass zero-admin/expected-state checks or automatically delete
history to unblock bootstrap. No such live window or cleanup is executed here.

Bilingual management UI, real approved-provider/admin/operator acceptance and broader
company migration remain pending. Module/plan acceptance percentages are unchanged.
