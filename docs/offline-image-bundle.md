# Optional local image handoff bundle

This is an opt-in retention step for the **same successful image rehearsal**,
followed by an independent read-only verifier. It is not an installer, operator
bundle, signature, offline acceptance or company deployment approval.

The starting evidence is main `b471decc85495ff88dbe9c2f5419a0092b133cef` and
[manual run 42463491932](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42463491932).
That run passed 70 contracts, both API/web builds and untouched traditional saves,
strict archive validation, nonroot/read-only dependency-only native smokes and both
Compose views. It did not start the application/database or demonstrate physical
network isolation. Its images remained on the ephemeral runner, with no artifact
upload. This feature cannot recover those expired runner files.

## Explicit local use

Use a trusted checkout and the existing rehearsal's authorized Linux amd64,
Python 3.12 and local Docker/Compose prerequisites. The existing network/build
operations require their own authorization. To retain a newly successful run:

```sh
python scripts/offline_image_rehearsal.py --run \
  --export-bundle /absolute/existing-parent/new-handoff
```

Without `--export-bundle`, the rehearsal retains its existing temporary-only
behavior. The option is incompatible with `--check-host`. Its parent directory
must already exist, and the destination must be wholly new, even if an existing
directory is empty. Relative paths, `.`/`..`, repeated separators, backslashes,
symlink components and an existing or dangling final destination are refused.
An early read-only destination check follows host checks, before downloads/builds;
the export rechecks and exclusively creates the directory after all rehearsal
stages succeeded. No export-from-old-logs command is supplied.

The new directory contains exactly:

- `api.tar` and `web.tar`: byte-identical copies of this run's two validated saves.
- `manifest.json`: the fixed `slc-image-handoff-v1` schema, source commit, exact two
  role records (controlled archive name, size, SHA256, immutable image ID, platform,
  source commit), and safe evidence SHA256. It is deliberately not an operator
  manifest and is not accepted by the operator preflight as deployment approval.
- `evidence.json`: reconstructed fixed-format status/check assertions and explicit
  limitations. No raw native-smoke output, command logs, source paths, host details,
  credentials, database configuration or operator approval is copied.
- `COMPLETE`: an empty regular file created exclusively and atomically only after
  payloads pass validation and their closes return. Its existence alone never
  establishes integrity, authenticity, readiness or acceptance.

The command's successful result adds `image_bundle` with exact source commit and
`manifest_sha256`. Preserve that digest and commit through an independently trusted
channel. A digest copied from the bundle itself does not establish its provenance.
The export step itself does not upload, transfer, download, load Docker images,
start containers, install software or change host configuration. Its later manual
workflow integration is described below.

## Independent read-only verification

Use the verifier and existing strict preflight from a trusted checkout, with an
expected commit and manifest SHA256 obtained independently of the received bundle:

```sh
python scripts/offline_image_bundle.py verify /absolute/path/to/handoff \
  --expected-commit <trusted-40-character-lowercase-commit> \
  --expected-manifest-sha256 <trusted-64-character-lowercase-sha256>
```

Both expectations are mandatory. The tool refuses missing or malformed values;
it does not derive trust from a marker or accept a supplied bundle as its own
source of trusted expectations. It checks the exact file set and empty marker,
bounded duplicate-key/nonfinite-rejecting JSON, exact schema and scalar types,
evidence hash/schema, each archive size/hash/role/commit, and then the existing
strict archive validator's platform, config, revision, environment, volume,
member/path/type and layer checks. Strict classic `LayerSources` handling is
unchanged. Cross-commit or cross-role substitution, unknown fields, bool/int
aliases, truncation, tampering and added/missing files fail closed.

The command only reads. It does not run Docker, extract archives, connect to any
service or database, or modify the input. Filesystem access-time updates by the OS
may occur. Success is `IMAGE_BUNDLE_VERIFIED_NOT_OFFLINE_ACCEPTANCE`: internal
integrity against the supplied expectations, not a signed or safe-to-execute image.
Even a matching trusted checksum does not provide a security review, license
clearance, app/DB/browser health result or deployment permission.

## Bounds, paths and changes during IO

- Two tar files together must be at most **16 GiB**. Metadata is at most **64 KiB per
  file**. The destination filesystem must report at least the two archive sizes,
  generated metadata and **1 GiB additional free space** immediately before directory
  creation. These are fixed conservative support limits, not measured peak usage,
  quota reservation, inode availability or a guarantee against concurrent disk use.
  A valid larger bundle is rejected, never automatically allowed by raising a limit.
- New directories/files are created with modes 0700/0600, subject to the process
  umask. The tool does not change existing permissions. Copies and hash reads use
  at most 1 MiB chunks, detect short reads, bound short-write loops, and compare byte
  counts and digests. Metadata reads are bounded before allocation. The unchanged
  archive validator retains its existing inner-tar budgets. Before invoking it,
  the new wrapper requires actual size to equal the bounded manifest size and
  performs an additional bounded, no-extraction outer-tar scan: at most 10,000
  actual headers and 16 MiB parser reads, 64 KiB per GNU/PAX extension payload,
  64 nested headers, and 1 MiB per structural read. It requires 512-byte alignment,
  two zero terminator blocks and only zero tail padding. Outer GNU sparse formats
  (legacy and PAX 0.0/0.1/1.0) are refused before their sparse-map expansion, so a
  tiny envelope cannot cause arbitrarily large logical layer hashing. Sparse policy
  inside image layer tar files is unchanged. It clears each processed
  member cache and limits the sum of effective inherited PAX dictionaries across
  members to 10,000 key/value entries and 4 MiB characters; member/link names total
  at most 4 MiB characters. These cumulative limits also bound the inputs retained
  by the unchanged second parser. It still reads accepted config/manifest metadata
  up to its existing 8 MiB per-file limit; the 1 MiB copy/structural-read limit is
  not a claim about every allocation in that validator. Unicode representation,
  parser objects and other overhead mean these logical limits are not an exact
  process RSS guarantee. Legitimate exports beyond a support limit fail closed.
- Directory allowlists are checked with streaming enumeration; the first unknown
  entry is rejected without materializing an arbitrarily large directory listing.
- Every path component is opened with descriptor-relative `O_NOFOLLOW` directory
  opens. Source and destination files use descriptor-relative nonblocking,
  no-follow opens, regular-file checks and a single-link requirement. This avoids
  blocking on a substituted FIFO and refuses symlinks/hardlink aliases. Copying and
  validating never reopen an archive through its supplied name.
- The original archive validator performs repeated stat/open operations. A local
  `PinnedArchive` adapter supplies fstat and `/proc/self/fd/<retained-fd>` opens,
  pinning all those operations to the same inode while leaving the gate unchanged.
  Directory links and file device/inode/type/size/mtime/ctime/link count are checked
  before and after operations. Observable mutations or replacements fail closed.
  The adapter is not a snapshot of a writable inode. Use trusted local storage and
  a trusted execution UID: this is not protection against a hostile same-UID/root
  process, kernel or storage provider, and does not lock files against later changes.
- Inputs are never rewritten, converted or deleted. Failure does not remove partial
  output, old run directories, existing images or other resources. There is no
  automatic retry, cleanup, prune, fallback or permission/security change.

## Incomplete and uncertain outcomes

Before the final commit, space exhaustion, IO/close/fsync failure, validation
failure or interruption leaves partial files **without `COMPLETE`**. Preserve that
directory for diagnosis. It cannot be accepted by the verifier and cannot be reused
as an export destination. Do not regard successful rehearsal checks as successful
export if export fails.

There is an unavoidable commit/response window: creation of the final empty marker
can succeed and then its close or a later descriptor close can fail, or the process
can be interrupted before reporting. Such an exception reports
`BUNDLE_COMPLETION_UNCERTAIN`, not success. A completion-window interrupt becomes
an equally interrupting `KeyboardInterrupt` subclass with only fixed safe text;
the CLI prints the uncertainty diagnostic and re-raises it. Earlier interrupts
retain their normal behavior. Both completion exceptions carry the commit and
manifest digest generated and checked by the exporting process **before** creating
the marker. The CLI emits those strictly formatted expectations on stderr so they
can be preserved from this trusted run and used for read-only recovery. No unknown
exception text, paths or values enter that receipt. If the process is killed before
it can report, this receipt may still be lost. Never retry a failed close: the descriptor number might already have been released and
reused. Never blindly rerun an uncertain export or delete its marker. Inspect it
with the read-only verifier and independently preserved expected values instead.
If no trusted manifest digest was preserved, do not manufacture one from the bundle
and label it trusted. A digest
obtained from the uncertain bundle itself is never a substitute for this trusted
process receipt. This does not promise crash/power-loss durable backup; the marker and final directory entry are not a substitute for a durable storage policy.

Public failures use fixed codes, never raw exception strings or supplied paths.
No success is printed on failure. The export result and safe evidence make no
operator-approval, database, application, physical-isolation or deployment claim.

## Validation scope for this change

The new tests use tiny synthetic archives and mocked rehearsal commands. They
exercise local file creation/copy/fsync, original archive validation, expected
commit/hash verification, safe evidence projection, write failures/short writes,
capacity bounds, mutation/path replacement, final-close uncertainty and process
interruptions. They are not runnable image evidence. This package does **not** run
a real full-sized image export, local Docker, a new complete image rehearsal,
application/DB startup or a disconnected/company acceptance test. Required candidate
CI, independent review and later separately authorized runtime evidence remain
separate gates. Business and deployment acceptance percentages do not change.


## Optional temporary-runner workflow integration

The manual image rehearsal now has a boolean `export_bundle` input, default `false`.
When enabled, a single newly successful rehearsal exports to a unique new directory
under `RUNNER_TEMP`, then a separate Python process runs this read-only verifier.
The expected commit and manifest digest come from the same successful run result,
with commit equality to both checked-out HEAD and `GITHUB_SHA`. The coordinator also
reconstructs the expected manifest from that run's image records and safe evidence;
it never reads the received directory to manufacture trusted expectations.
The verifier must return success and the exact same commit/digest with the verified
status. Missing or malformed receipts, contradictory metadata and any child failure
stop the job before a success summary. There is no automatic recovery or retry of
an incomplete/uncertain export and no deletion or reuse of an existing destination.

The boolean travels only through an environment value and is checked against exact
`true`/`false`, not substituted into shell source. The public summary includes only
fixed statements and validated commit/image/hash strings, never local paths, raw
logs/native output, host details, credentials or arbitrary exception text. It says
explicitly that the verified bundle exists only on the temporary runner and is not
a retained downloadable artifact. False means no export and no separate verifier.

This adds copying and repeated validation IO without raising the existing 20 GiB
host gate, 60-minute job limit or the bundle's 16 GiB/1 GiB support bounds. Free space
and processing time can still be insufficient. The workflow does not upload or
cache the bundle, publish images, connect to a company server, start the app/DB or
prove offline operation. Its implementation tests use mocked child processes; no
new real large-image export or workflow dispatch has been executed for this package.
See [the rehearsal workflow contract](offline-image-rehearsal.md#manual-workflow-option--2026-11-08)
for parsing limits, trust checks, failure handling and the separate runtime evidence.
