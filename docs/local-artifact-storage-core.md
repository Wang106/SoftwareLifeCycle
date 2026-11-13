# Local artifact storage core

This package prepares one standalone local byte-storage primitive. It does not
add file upload to the application. Public production and Preview remain
sample-only/read-only; no route, form, database migration, deployment configuration,
identity, grant, dependency or workflow is changed.

## Scope and call sequence

`backend/app/services/local_artifact_storage.py` uses only the Python standard
library and performs no I/O when imported or constructed. Every operation is
disabled unless a trusted caller explicitly creates an enabled instance. There is
no environment-variable switch, startup hook or existing application caller.

1. `reserve(expected_bytes=..., sha256=...)` returns an immutable receipt containing
   a service-generated UUID, exact expected byte count and lowercase SHA-256.
   It does not create a filesystem reservation. A future adapter must persist this
   descriptor before accepting any bytes; an exception cannot deliver it after a
   process crash.
2. `stage(receipt, source)` consumes a borrowed synchronous binary `read(n)` source
   into a new exclusive `.part` file. It does not close the caller's source.
   Reads and writes are bounded, and exact byte count plus server-computed SHA-256
   must match. File and directory synchronization precede success.
3. `commit(receipt)` is allowed only after successful staging in the same instance.
   It verifies the stored bytes again, hard-links to a new `.blob` name without
   replacement, and synchronizes the directory. The stage alias is retained.
   A commit attempt consumes the local capability, including when its outcome is
   uncertain. No automatic retry or restart-resume is provided.
4. `inspect(receipt)` reports each name as `missing`, `mismatch` or `verified`.
   It does not write, publish, repair, remove or synchronize files. Normal filesystem
   access-time updates may occur. `verified` means current bytes match the supplied
   descriptor, not that a prior operation completed or survived power loss.

A fresh process can inspect retained bytes with the persisted descriptor, but
cannot publish an old stage. Inspection never creates database `READY`, an Artifact,
an audit event, an approval, a delivery or authorization. Descriptor integrity is
not authentication or proof of file origin. A future authenticated adapter and
durable database/file state machine remain separate work.

An interrupted Python return cannot prove whether the caller received an
acknowledgement. The in-memory capability prevents ordinary failed/duplicate calls
from proceeding; it is not a crash-proof receipt log. After an interruption the
caller must use inspection only. Calls on one instance are serialized and
non-reentrant, including from reader callbacks. Its trusted caller keeps the
configuration unchanged and prevents concurrent mutation of the object's paths.
No thread-safe lifecycle or cross-process reservation is supplied.

## Storage boundary

The caller must provide an existing canonical absolute directory on a trusted
Linux local filesystem supporting hard links and directory `fsync`. The root
must already be owned by the service UID with mode 0700. Every created file uses
mode 0600. The core does not create/chmod the root, select a company path, install
mounts or change security settings.

Directory traversal uses directory descriptors and refuses symlinks. Untrusted
owners and writable non-sticky ancestors are rejected. Shared sticky ancestors
such as `/tmp` are suitable for the private synthetic test root. File reads reject
unsafe types, ownership, modes, unexpected hard links and observed identity/content
changes. Only the retained `.part`/`.blob` pair may share the object's inode.

The same service UID and host administrator remain trusted. This is not a sandbox
against them or a proof against privileged concurrent mutation. Files are immutable
through this API, not through a new operating-system security policy. No Windows,
network-filesystem, shared-storage or multi-host compatibility is claimed.

Original filenames and external storage references are not accepted. Object paths
come only from validated UUIDs and fixed suffixes. No URL, network share or archive
is fetched, followed, unpacked, rendered or executed.

## Bounds and failure handling

The default per-object maximum is 64 MiB, with 64 KiB read chunks. These are
development defaults, not an approved company size or file-type policy. The core
checks actual streamed bytes, rejects invalid/oversized metadata before filesystem
access, rejects a reader that violates `read(n)`, and handles partial writes.
Empty content is permitted when the trusted descriptor declares its exact digest.

Byte bounds do not impose a wall-clock deadline on a blocking synchronous reader.
The trusted future adapter must provide request cancellation, time limits,
authentication, quotas and admission control. The core has no total-volume quota,
concurrency scheduler, file-type scanner or malware verdict.

Failures preserve any created data. A full matching stage after a failed `fsync`
is still a failed/uncertain stage and cannot be committed through that instance.
Publication may have occurred even when its acknowledgement or directory sync
fails. The caller uses the original descriptor for inspection instead of repeating
stage/commit or inventing a new UUID. Each owned descriptor is closed once; an
uncertain close is not retried.

There is no cleanup or retention API. Operators must not treat this as permission
to delete orphan files, overwrite unknown objects or replay a failed upload.
Durable reconciliation, retention, capacity recovery and paired database/file
backup require a separately reviewed package.

## Remaining application prerequisites

- PR227 creates an empty ASR without components. Artifact metadata requires an
  exact ReleaseComponent, so component declaration/selection must be addressed.
- Upload, status, receipt and download need strict private identity/scope checks,
  independent default-off capabilities and protection from old public metadata
  reads/search. A UUID or digest must never become download authorization.
- Real storage location, service account, capacity, file types/limits,
  classification, scan policy, retention and backup ownership need approval.
- Existing offline installation remains synthetic, read-only, Linux/amd64 and
  Docker-based. A writable profile and an available internal OIDC/JWKS service
  are not supplied by this primitive.
- Local byte verification does not complete R09/R11, company deployment, actual
  browser upload/download or real-user acceptance. Business remains 36/44=82%.

## Validation

Baseline: main `fcbcbe416ac4bbfea0e32fd8d750f202880dd3d5`, merged PR227.
[Main CI43445242134](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/43445242134)
passed the existing backend/PostgreSQL/migrations, frontend, strict browser and
aggregate gates. Same-main Cloudflare check succeeded; Actions deployment and
continuation skipped. Baseline evidence is not candidate acceptance.

Focused tests use synthetic bytes and private temporary directories. Their initial
missing-module failure established the regression-first baseline. Descriptor-close
fault injection subsequently demonstrated an uncertain-close retry and leaked next
descriptor before its narrow ownership repair. Final counts and review evidence
are recorded in the current HANDOFF entry.

The unchanged normal CI must validate the exact published candidate, including its
full PostgreSQL/migration and strict browser gates. No manual container/API/database
rehearsal, company access, real file transfer or production enablement is part of
this package. Publish only an isolated draft PR; ready-for-review and merge require
the owner's later approval.
