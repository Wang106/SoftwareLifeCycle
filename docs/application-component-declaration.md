# Private application component declarations

This bounded package prepares component declarations for an existing application
release draft. It does not upload, copy, download, inspect or publish binary files.
Public production and Preview remain sample-only/read-only. Implementation and
exact-candidate verification evidence belong in the newest HANDOFF checkpoint.

## Business meaning

An ASR continues to reference one exact SSR. A new declaration may link to one
component in that SSR or add a component without a baseline link. Several
declarations, including several versions of one component definition, may coexist.
Names and equal version strings never merge records or establish inheritance.
An explicit new request creates a new component UUID; only the original request
UUID is an idempotency key. Existing rows are never edited, removed or deduplicated.

The user selects an existing active ComponentDefinition UUID. The global component
dictionary is not managed by this package. A component absent from the selected
SSR can still use an existing definition. Creating a previously unknown definition
is separate work, not silently inferred from a typed name.

Without a baseline component, the declaration is ADDED. With an exact component
from the ASR's SSR and the same definition, the user explicitly declares UNCHANGED
or MODIFIED. These are recorded declarations, not proof of binary equivalence,
successful copying, approval, release or distribution permission. Removal is not
part of this add-only package. The ASR component version is explicitly supplied.

## Private context and write boundary

Routes:

- `GET /api/v1/application-component-declaration/context`
- `POST /api/v1/application-component-declarations`
- `GET /api/v1/application-component-declaration/receipts/{request_id}`

The new interface uses exact ASR, definition and optional baseline-component UUIDs.
The server derives project, customer, software and SSR from stored relationships.
It rejects inconsistent relationships, inactive definitions, non-DRAFT application
releases and revoked release chains for a fresh declaration. An SSR need not have
been formally released, but it must remain unrevoked. This preserves the decision
already implemented by the empty-ASR creation package.

The ASR's stored customer scope must match its project/detail. Legacy null-scope
or inconsistent records are not silently backfilled or adopted by this operation.
An exact linked baseline may have a null recorded component version; its UUID and
definition, not a version string, determine the association.

Identity is OIDC-only and requires an ACTIVE human principal, current browser
session when supplied, exact project CONTRIBUTOR membership and exact software
visibility. PLATFORM_ADMIN alone does not bypass these requirements. Identity,
membership and parent bindings are refreshed under transaction locks. Current
authorization is required for context, writes and original-receipt retrieval.

There is an independent default-disabled backend capability and a separate
default-disabled frontend capability. No existing command's switch enables this
operation. No identity, role, credential, provider or production setting is created
or changed. The public read-only guard continues to reject business writes.

The backend key is `APPLICATION_COMPONENT_DECLARATION_ENABLED`. Frontend keys are
`APPLICATION_COMPONENT_DECLARATION_MODE`,
`APPLICATION_COMPONENT_DECLARATION_APPROVED_API_BASE_URL` and
`APPLICATION_COMPONENT_DECLARATION_APPROVED_APP_ORIGIN`. None is enabled by this
package, and configuration is not an authorization grant.

Review binds the exact context and its digest to a strict command with a mandatory
request UUID, version and reason. Extra fields and unsupported text are rejected.
The client cannot set actor, project, customer, software, SSR, status, policy,
storage reference, artifact or approval. The original fourteen-command acceptance
denominator is unchanged; this operation has its own exhaustive write contract.

## Atomic evidence and recovery

The new ReleaseComponent and its reserved EVT-ASRC- audit event commit atomically.
The request UUID is the new component UUID. The audit preserves the canonical
command, reviewed context and original receipt. Parent row locks serialize this
declaration with relevant existing writers. Audit or commit failure rolls back the
new row; no partial success is reported.

A matching original request by the same currently authorized actor returns its
original immutable receipt without creating another row. Different content,
another actor, a legacy UUID, missing evidence or inconsistent receipt fails closed.
Later parent status changes do not rewrite the original DRAFT receipt, but current
identity, session and exact scope still govern access. A missing receipt is not
proof that an uncertain request failed. Browser recovery only queries the original
receipt; it never silently resubmits or generates a replacement request UUID.

## Public-read isolation

New declaration events are excluded from old public audit, activity, dashboard
and search surfaces. A central SQL predicate classifies a component as private
when associated immutable audit evidence uses the reserved declaration event type
or event-number prefix. Privacy classification is deliberately separate from
strict receipt validation: malformed receipt content cannot make the row public.

Public component declarations, counts, pagination, unlinked-baseline observations
and SSR aggregates exclude these rows, including correlated subqueries and aliases.
Historical sample rows without this marker retain their prior read behavior. The
new interface uses authorized context and original receipts, not a new general
private component directory. Old public endpoints do not become private endpoints
merely because a caller supplies credentials.

The privacy marker relies on atomic creation and append-only audit retention.
This package does not authorize deleting audit evidence. Direct database changes,
future imports and new writers must preserve this invariant; general company-data
authorization remains separate work.

As defense in depth, artifact-policy/search projections exclude artifacts attached
to a private declared component. Snapshot creation refuses such source artifacts
instead of silently omitting them from formal evidence. No artifact attachment is
implemented or enabled here. Private artifact lifecycle, frozen metadata, delivery,
download and storage-state reconciliation still require their own reviewed package.

## Browser behavior

The bilingual form remains editable while submission is unavailable. Fixed
same-origin server proxies bind an approved app origin and API base, with bounded
strict request/response formats and private/no-store responses. They do not accept
arbitrary upstream URLs or client-provided authorization headers.

Changes invalidate unsent confirmation. Double clicks and stale handlers cannot
issue parallel submissions. An attempted request retains its original identity
and body through unknown results. Recovery import is inert until an explicit
receipt query and is permanently query-only. No automatic browser persistence,
token export, background retry or real file selection is added. Success means one
component declaration, not a saved file or completed application release.

## Verification and remaining work

Regression coverage must include linked and added components, multiple versions,
exact-UUID binding, current role/session denials, context changes, request conflicts,
atomic rollback, original receipts, public-read exclusions and artifact/snapshot
barriers. PostgreSQL concurrency and migration checks run in unchanged normal CI;
SQLite tests do not establish PostgreSQL locking behavior. Frontend tests cover both
languages, disabled gates, repeated/interrupted navigation, confirmation changes
and recovery-only flows. All original strict browser/report gates remain required.

No real file transmission, storage location, file policy, cleanup or retention
decision, company database, manual container rehearsal or writable deployment is
part of this package. The byte-storage core remains unconnected. Business acceptance
stays 36/44=82%; code and synthetic CI do not complete company or real-user acceptance.
