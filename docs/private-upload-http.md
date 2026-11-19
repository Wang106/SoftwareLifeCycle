# Default-off private single-file HTTP ingress

This backend slice connects the existing private-upload coordinator to finite
HTTP bytes. It has no browser file picker, Artifact creation, download, scan
verdict, distribution right or formal release operation. Tests use synthetic
identity/content and disposable storage. Nothing enables a deployed service.

## Contract

- `GET /api/v1/private-uploads/context?component_id=<canonical UUID>` obtains
  current exact private component context and digest.
- `POST /api/v1/private-uploads/reservations` accepts the existing strict
  `ReservePrivateUpload` JSON. The client explicitly confirms the exact component,
  expected length/SHA-256, context digest and reason before this request. An exact
  replay returns the original reservation; changed content conflicts.
- `PUT /api/v1/private-uploads/<request UUID>/content` accepts only an exact
  `application/octet-stream` body with one canonical Content-Length. No multipart,
  encoding, transfer-encoding or content-range input is supported.
- `GET /api/v1/private-uploads/receipts/<request UUID>` is authenticated recovery
  of the original reservation and durable phase/stored receipt. It never retries
  storage and never returns file bytes or storage paths.

Context/reservation/receive use existing active USER, project CONTRIBUTOR,
software visibility, exact ASR/component/SSR binding and revocation rules. A
supplied browser session is rechecked. Trusted token expiry is rechecked after
ingress. These are not legacy-auth or administrator-bypass endpoints. Responses,
including failures, use private/no-store and authorization/session Vary headers.
Unknown JSON fields, duplicate fields, invalid IDs and unsupported headers fail
closed. Errors do not echo request content, filesystem paths or SQL details.

## Disabled configuration and bounds

`private_upload_http_enabled` defaults false. Enabling requires all of
`private_upload_root`, `private_upload_scope_id`, `private_upload_max_bytes`,
`private_upload_total_seconds`, `private_upload_idle_seconds` and
`private_upload_transfers`. This package does not supply operational values or
create a root. The existing Linux local-storage core requires an existing,
service-owned 0700 directory and refuses unsafe ancestors/symlinks.

The implementation ceiling is 8 MiB per file, 4 admitted transfers per process,
120 seconds of ingress and a positive idle deadline no longer than the total.
These ceilings are not approved production capacity settings. JSON reservation
bodies are limited to 64 KiB. File data is buffered in bounded memory before the
synchronous storage call; copies and the ASGI server's own buffering add overhead.
Admission is per process, not a host-wide, distributed or proxy quota. Real
installation still requires explicit process/proxy/request-size/storage policies.
A running process refuses a changed runtime policy instead of resetting permits
or silently changing the storage scope. No hot root migration is supported.

Preauthorization opens, uses and closes its own database session in a worker.
No database transaction is retained across network reads. The finite ingress
reader enforces actual bytes, total elapsed receive time and byte-progress idle
time, independently of Content-Length. It verifies length and SHA-256 before
calling the existing coordinator, which rechecks current authorization and
parents and consumes the single durable storage attempt.

The ingress deadline does not terminate a blocking DB/filesystem operation.
Cancellation cannot kill its worker: ownership and admission remain until that
worker actually finishes, even after repeated cancellation. Process termination
can leave a durable in-progress phase; no restart/takeover/retry is implemented.

## Failure and recovery

A rejected preflight reads no file body and creates no stored object. An ingress
length/digest failure, timeout or disconnect does not invoke storage; an existing
reservation can remain RESERVED. That status is not permission for an automatic
resend. Clients must stop after an uncertain request and inspect the original
request ID's receipt. There is no automatic retransmission or new-ID fallback.

A lost response after worker start may leave RECEIVING, STAGED, PUBLISHING,
RECONCILIATION_REQUIRED or STORED_PRIVATE. Even cancellation can accompany a
committed success. Only the authenticated original receipt establishes the
recorded outcome; the HTTP response cannot invent a failure/success receipt.
STORED_PRIVATE does not establish content safety, durability after recording,
Artifact registration, download permission, distribution eligibility or release
readiness. The existing coordinator's retained exact objects are not cleaned,
repaired or resent by this adapter.

## Validation boundary

Synthetic ASGI tests cover finite/slow/stalled streams, disconnect, malformed
headers, mismatched length/hash, refusal before body reads, admission, repeated
cancellation and worker failure. Signed HTTP tests exercise the real coordinator
against isolated SQLite and synthetic temporary bytes; they do not prove
PostgreSQL locking. Additional tests are defined for normal CI's isolated
migrated PostgreSQL: no parent lock across ingress, revocation during ingress and
two independent adapters competing for one reservation. Local missing PostgreSQL
configuration is reported as skipped, never passed.

The exact two-write-route inventory and two-caller/four-route isolation checks
pass. Both retirement inventories include the new contract and enumerate every
unsafe HTTP method, including PUT; all original closure assertions remain. Ordinary strict CI, independent reviews and real environment acceptance
remain distinct gates. This implementation does not patch historical runtime
images or resolve the previously unexplained Node harness timeout.
