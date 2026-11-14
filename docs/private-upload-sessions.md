# Private upload session preparation

This package implements a default-disabled trusted Python coordinator and private
database recovery metadata. It uses synthetic finite bytes for validation. It adds
no application caller, HTTP upload/download, browser file selection, environment
switch, Artifact, formal release or deployment. Public operation stays sample-only
and read-only. The caller must explicitly provide `enabled=True`, an existing
trusted Linux-local root, a nonzero storage namespace UUID and a finite size bound.
There is no enabled default size. Test values are not company file policy.

## Durable state and meaning

The service accepts only an exact component whose complete retained private
declaration evidence validates. Multiple upload attempts may belong to one
component; equal bytes, names or versions never merge entities. Only the original
request UUID identifies a reservation replay. Original filenames, client paths,
URLs, type/classification/distribution choices and Artifact fields are not accepted.

1. `context(component_id, request)` obtains current authorized private context and
   its digest. The context includes exact ASR/SSR/project/customer/software and
   component relationships, plus the trusted storage namespace and admission bound.
2. `reserve(request=..., **command)` validates the explicit request UUID, expected
   byte count/SHA256, reason and context digest. The storage core generates an object
   UUID without touching disk. Reservation metadata, original receipt and audit
   commit together before any bytes can be consumed. Exact actor/body replay returns
   the original reservation, even after later parent ineligibility. Conflicts fail.
3. `receive(request_id, source, request)` atomically claims RESERVED as RECEIVING
   and commits before calling the synchronous bounded storage reader. It consumes
   each request at most once. STAGED is recorded only after stage returns success;
   PUBLISHING is committed before the one-shot storage commit; STORED_PRIVATE and
   the immutable original stored receipt commit after storage commit returns.
4. `receipt(request_id, request)` returns the validated original reservation,
   current durable phase/revision and stored receipt, if one exists. It never
   performs filesystem I/O or synthesizes success from current bytes.
5. `inspect(request_id, request)` independently observes the two retained byte names.
   It authorizes before filesystem access, releases locks during that access and
   rechecks current scope before returning. The response separates the byte
   observation/revision/time from current database status. It does not write or sync.

The successful path is:

`RESERVED → RECEIVING → STAGED → PUBLISHING → STORED_PRIVATE`

An ordinary failure after a known claim can append RECONCILIATION_REQUIRED if the
actor still has write authority and the database accepts the record. Abrupt process
loss, authorization revocation, read-only changes or a failed metadata write can
leave the last durable phase instead. Both are unresolved states, not permission
to resume. No lease expiry, process restart, verified `.part`/`.blob`, receipt miss,
or lack of an acknowledgement automatically permits another stream or publication.

A database commit whose acknowledgement is lost might have succeeded. The service
propagates uncertainty, keeps the original identity and permits only explicit
query-only recovery. It never downgrades an already committed STORED_PRIVATE
receipt while recording another failure. A missing receipt does not prove absence
of a transaction. No automatic retry, fresh replacement UUID, overwrite, cleanup
or deletion is implemented. New deliberate attempts are separate decisions for a
future interface, not a recovery shortcut in this package.

STORED_PRIVATE records that storage returned success before the final database
transaction. It does not assert current byte health forever, prove power-loss
durability, identify file origin, provide a scan verdict, create an Artifact or
grant download, approval, distribution or production rights. A later read-only
inspection may report mismatch while the original stored receipt remains intact.

## Authorization, concurrency and confidentiality

Every operation requires strict OIDC mode, a current ACTIVE human principal and a
valid browser session when supplied. Exact active project CONTRIBUTOR and software
visibility are required together; PLATFORM_ADMIN alone does not bypass them.
Reservation, claim and every later success transition also require the exact
current DRAFT/unrevoked chain, active parents/definition and unchanged reviewed
context. The server derives scope from stored relationships rather than supplied
customer/software identifiers or public samples.

An authorized contributor may use another contributor's valid private declaration.
This is limited to the new internal coordinator. The original declaration receipt
API remains creator-bound, and all upload recovery remains bound to its own original
actor plus current scope. Removing or corrupting declaration/audit evidence fails
closed rather than reclassifying it as a valid public upload target.

The coordinator reuses existing principal/admin and deterministic parent locks,
then locks the upload row. Each instance exclusively owns its SQLAlchemy session
and storage core and rejects reentrant/concurrent calls. Database state prevents
another process from claiming an already attempted request. No database transaction
or global authorization lock spans stream or filesystem I/O. Revocation can commit
while a stream blocks; the next transition then refuses business completion and
retains any bytes. This may leave a complete private stage without a published
object, or published bytes without a stored receipt.

Each phase and receipt is tied to the complete original command/context and its
append-only audit chain. Evidence comparison is type-sensitive: JSON `true` or
`1.0` cannot stand in for integer version/revision/size. Audit payloads contain no
file bytes, root paths or raw exception output. Reserved event type or event-number
prefix independently excludes these events from public audit/activity/dashboard/
search surfaces, including malformed evidence. The private table has no read route.
Existing public component/artifact exclusions and snapshot refusal remain intact.

`storage_scope_id` is a trusted immutable deployment mapping to one root. It is not
a bearer credential, client-selected destination, path or download capability.
Changing its root mapping is outside this contract. Root ownership,0700/0600 modes,
symlink/path checks, bounded reads/writes, retained aliases and one-shot publication
remain the [existing byte core's contract](local-artifact-storage-core.md). The
service does not create/chmod an operator root or configure persistent access.

## Schema and offline compatibility

Migration0030 adds only `private_upload_sessions`, references existing principal
and ReleaseComponent keys, constrains state/counters/receipt pairing and uniquely
identifies each service object. It backfills no old row, creates no Artifact and
refuses downgrade if any upload session remains. Application authorization and
audit validation remain necessary; table constraints alone do not implement them.

Current required revision, migration input/count checks, readiness and isolated
restore expectations advance to0030. The new147-fact offline manifest retains the
old119 non-version facts and adds27 upload facts plus the current version. The old
0029 manifest/migration bytes and29-migration SQL generation remain preserved and
tested as historical evidence. Matching self-reported offline evidence is still
not independent database verification. Existing narrow PG guard collectors retain
their original documented coverage; dedicated new CI tests verify upload schema
constraints instead of claiming those collectors now cover this table.

## Verification and open decisions

Regression-first failures cover the absent coordinator/schema, stale frontend
health revision and malformed scalar evidence. Synthetic tests cover exact bounded
storage, all database commit acknowledgement windows, source interruption,
reentrancy, corrupt receipts, changing scope, cross-actor isolation, collaborator
declarations and public audit projections. New independent PostgreSQL sessions
test reservation races, one source consumer, current receipts during a blocked
stream and revocation without holding byte-I/O locks. PostgreSQL tests must pass
the unchanged exact-head normal CI; local SQLite/collection/skips do not count.

The caller still needs approved file type/size/quota policies, wall-clock deadlines,
cancellation and resource admission before accepting network bytes. Total-volume
quotas, file classification, scanners, retention/cleanup, paired database/file
backup, private Artifact/frozen metadata, downloads and real HTTP/browser wiring
remain separate. No real user file, company database, manual container/API rehearsal,
resource purchase, production enablement or live migration is part of this package.

Publish only an isolated draft PR after final review; ready-for-review/merge require
the owner's later approval. Business acceptance remains36/44=82%, increment0;
module/plan denominators, browser stage1/4 and prior finite plan8/8 do not change.
