# Synthetic private-upload restored-root evidence

This is a test package, not a backup product or an operator restore command.
The existing software/joint retained restore uses fixed README/settings/firmware
fixtures and requires single-link files. It does not cover the upload storage
primitive's deliberately retained `.part` and `.blob` hard-link aliases.
No existing restore guard or production storage behavior is changed here.

## Tested slice

The real upload service creates synthetic content and persists the original
request/object/component/actor/scope metadata through existing test fixtures.
The source pair is independently read and asserted to share device/inode with
link count two. Only synthetic bytes are retained in test memory. A fresh owned
0700 root receives new 0600 files, either a linked pair or two independent copies.
The source inode remains allocated, so the new inode cannot accidentally be
mistaken for the original. This is byte reconstruction, not inode preservation,
archive extraction, crash durability or a full database backup/restore.

A new service instance uses the new root and existing original request ID.
The test-only `private_upload_restore.verify_restored` requires the actual
read-only service `inspect` result, matching historical receipt/revision, and
both current aliases verified. It independently rereads the closed blob using
the existing disk witness and checks length/SHA-256 and safe link relationships.
The database test independently checks object/component/actor/scope, bytes/hash,
private state/revision and unchanged audit events in a fresh SQLAlchemy session.

The PostgreSQL case uses only normal CI's existing migrated disposable schema
fixture; no new database service or connection configuration is added. The same
database is retained across the root switch: this is NOT a database-restore test.
Locally that case skips when TEST_POSTGRES_URL is absent; exact-head CI must run
it. Existing full PostgreSQL and macOS browser gates remain unchanged.

## Negative evidence and boundaries

An empty root still has the historical STORED_PRIVATE receipt, but current byte
verification fails. Missing stage alias, wrong size/digest, wrong object names
and an extra hard link also fail. Neither inspection nor the witness republishes,
repairs or changes the historical row. A current matching byte observation is
not proof of the original call's acknowledgement, scanning, distribution rights
or release readiness. LocalArtifactStorage accepts two independent valid files;
there is no invented requirement that a byte-copy restore preserve inode identity.

All test files live under pytest-owned temporary paths. Source bytes are synthetic;
no company files, old database, runtime image, Docker, host, Render or deployment
operation is involved. No production code, permissions, settings, dependencies,
workflow or test gates are changed. Test dependencies use the unchanged repository
requirements in an isolated local virtualenv. Real backup policy, consistent
DB/media snapshots, supported restoration format, target filesystem, retention,
crash recovery and company installation remain unverified. Historical e2038a94
images remain outside Next16.4.5 source-patch coverage; old CI timing causes are
not claimed fixed. Business acceptance remains36/44 (82%), increment0.
