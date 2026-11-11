# Retained synthetic PostgreSQL input bounds

This repair changes only the existing `app.ops.retained_synthetic_restore`
reader and snapshot copy, plus an optional byte budget in the existing archive
digest/verification helpers, not the v1 package format or recovery scope.

Each JSON manifest/baseline is limited to **65,536 bytes**, and the archive to
**67,108,864 bytes**. These fixed-synthetic limits match the paired coordinator.
Verified main CI42980710200 samples had 1,277-byte manifests, 9,150–9,165-byte
baselines and 199,615–200,053-byte dumps. The limits allow ample headroom for the
supported canonical fixture; they are not sizing guidance for real backups.

Metadata is read in bounded chunks before JSON decoding. Snapshot copying uses
at most 65,536-byte reads, plus a bounded EOF/overflow probe, and exclusive new
snapshot files. Before any database target is created, the copier compares byte
count and SHA256 with the pre-copy fingerprint, verifies the written snapshot,
and the existing complete package validation runs again. File type, size,
identity and modification timestamps are checked around bounded reads; growth,
truncation, replacement and checksum mismatch fail closed. Original inputs are
never written. This is corruption/change detection, not an adversarial filesystem
sandbox: the caller still must supply its own trusted synthetic files and keep
them stable. Native archive catalog validation retains its existing checks. Its pre-catalog
archive digest now receives the same archive byte limit, so a file growing after
the initial size check cannot be read indefinitely. Digest reads consume no more
than the limit plus one overflow sentinel byte. Other helper callers retain the
unlimited default; their behavior and existing checks are unchanged.

These are input and copy-buffer budgets, **not an absolute process RSS or runtime
guarantee**. JSON object allocation, Python/native processes and PostgreSQL have
separate resource costs. SHA256 agreement does not authenticate executable SQL.
No arbitrary, company, old database or third-party backup is supported.

Existing numeric-loopback/control-database restrictions, absent-target refusal,
canonical fixture/schema, trusted-own flag, native version checks, append-only
verification and exact ownership-marker cleanup are unchanged. Pre-target failure
may retain an incomplete new evidence/snapshot directory, but creates no target
or cleanup proof. Failures after target creation retain the existing sanitized
report and owned resources for explicit diagnosis/cleanup; no retry or automatic
cleanup was added.

## Verification

The initial seven focused regression cases failed on the old implementation
(two failures and four missing-helper errors). Ten focused standard-library
cases now pass using isolated dependency stubs and synthetic files, without a
native database. Three parameterized actual-module pytest cases additionally
exercise archive/manifest/baseline limits and assert rejection before database
access/target creation. A fourth actual-module case and an equivalent
standard-library test execute the real validation/digest path with a 32-byte
budget: a 27-byte fixture grows by 100 bytes at its first digest read. Before the
optional-cap repair this consumed 127 bytes and failed only at checksum comparison;
now it reads exactly 33 bytes and rejects before native catalog work. Exact-limit
and legacy unlimited digests are also tested. Full local validation passes 882
offline, 52 automation and 126 CI guard cases. Existing real PostgreSQL retained and paired recovery
integration tests remain unchanged and must pass in exact-candidate CI.

Local full pytest/native PostgreSQL could not run because runtime dependencies
are absent. This package does not claim deployment, a manual API/database
rehearsal, company recovery acceptance or new business milestones.
