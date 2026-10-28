# Identity and grant status manual recovery (P6)

## Bounded capability and authority

This package concerns the existing principal ENABLE/DISABLE and GLOBAL, PROJECT or
SOFTWARE grant RESUME/SUSPEND operations, not identity/grant registration. Existing
status submission and retry behavior, backend policies and administrator protections
are unchanged. It adds a manual same-site export/import and an explicit historical
receipt query. No configuration, roles, identities, credentials or company deployment
are changed; the respective existing principal/grant submission gate stays default off.

Every receipt query requires a current valid USER session and a successfully validated
existing backend administrator-read response before querying the original activity.
Neither a grant count nor an imported actor assertion grants access. A new valid
session for the same original actor can recover; a revoked session, self-suspended
administrator, foreign actor or unavailable/malformed evidence remains UNKNOWN.
There is no elevated fallback or adoption of another actor's event. Existing separate
administrator/offline recovery procedures do not mean this UI bypasses current access.
Read-only authenticated sessions may query history when the existing gate is configured;
they cannot submit a status change. Backend requests in the new recovery path are GET only.

## Frozen user-controlled envelope

The bounded versioned canonical envelope binds the exact application origin and original
kind, target UUID, audit event number, expected and requested statuses, and reason. Grant
commands additionally retain the original principal UUID and role for audit comparison.
It excludes credentials, session IDs, issuer/subject/display name, claimed actor, receipt,
and unaudited principal type/protection/configuration observations. Duplicate keys,
extra fields, invalid Unicode, changed origin/kind, excessive size and noncanonical
normalizations are rejected, not silently repaired. Export requires a confirmed original
preparation; an unknown attempted result remains exportable. Preparation does not prove
that any operation was sent.

Explicit warnings identify internal identity/grant references and reasons as potentially
sensitive information for secure local handling. No automatic storage, download, clipboard
write or external upload occurs. Import makes no network request and generates no ID;
its immutable facade has only original-audit recovery, not send or retry. The UI prevents
replacement of a locally or imported unresolved attempt and ignores stale asynchronous
completions. Recovery remains bound to the same target/kind rather than the current mutable
status. Existing write controls are never added to an imported attempt.

## Historical receipt, not current permission

The server matches the authenticated original actor, event number and type, entity UUID,
reference/type, action, exact payload fields, expected/requested statuses and reason.
Principal events use ENABLE/DISABLE and include a validated nonnegative original revoked
session count (zero for ENABLE); grants use RESUME/SUSPEND. Global and membership events
bind the original principal and role. Membership scope UUID is validated in the original
audited payload; it is not falsely described as matched against an absent import field.

Only original occurrence is confirmed. The receipt never synthesizes current_status,
replayed, current effective grants, provider activation, or restoration of old sessions.
A later opposite status does not erase the original event. Missing/denied evidence proves
neither success nor failure and must not encourage resubmitting an imported command.
Raw identifiers and reasons are preserved under bilingual labels.

## Verification and external limits

Coverage includes all four audit/action shapes, exact canonical envelopes, zero-network
import, frozen unknown export, same-actor fresh session, revoked/foreign/self-suspended
administrator, malformed administrator projection, tampered event/body and historical
success despite later status changes. Composed tests must exercise the actual proxy and
session/audit chain, not only a mocked receipt. UI tests cover Chinese/English, raw data,
manual actions, read-only gating and busy/unknown/route/clipboard interactions.

Focused and full frontend/build results and independent review are recorded in the current
handoff. Exact-head complete backend/real PostgreSQL/frontend CI and fresh main/provider
verification remain mandatory. Synthetic tests are not real browser, identity, multiuser
or company acceptance. Overall 36/44=82% is unchanged. After this bounded package, the
finite plan proceeds to conditional P7 operational integration and P8 reconciliation;
VIN, actual AI and binary storage are not implicitly completed.
