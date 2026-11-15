# Fixed-source API/Web build and measurement

This default-off implementation uses the selected current-tool checkout separately
from image source `e2038a9462770a29254674dd86c0e7b26b26a221`, the sole reviewed
schema `0030_private_upload_sessions` mapping. It has not been dispatched and
produces no downloadable material during development. It is not a company installer.

## Explicit future execution

The `Manual fixed-source offline media build and measure` workflow has one boolean,
`build_and_measure`, default false. True would use an existing standard Ubuntu24.04
runner, two credential-free checkouts, read-only repository permission, the existing
non-cancelling `offline-image-rehearsal` concurrency group and a60minute hard limit.
No scheduled/push/PR trigger, cache, artifact upload, alternate destination or fee
approval flag is present. This development package does not authorize dispatch.

The coordinator checks the clean tool checkout against `github.sha` and the separate
clean source checkout against the fixed image commit. The builder checks the source
commit again inside snapshot before reading tracked bytes using `git show`; it
refuses a different source before dependency acquisition or build. Labels alone
are not trusted source selection. It uses the existing official pinned dependency
inventories, locked bases, dedicated Dockerfiles, traditional docker-save validation,
dependency-only native smoke and Compose parse. No API/Web server or DB is started.
Existing host prerequisites, including Python3.12, local Linuxamd64 Docker/Compose
and20GiB free on temporary/Docker filesystems, still apply. Nothing is installed or
reconfigured. Images and intermediate files can require more space than the final
archives; these runner prerequisites are not laptop/server sizing evidence.

The shared55minute budget begins before checkout/tests. Work stops at53m25s with95s
reserved for unwind and reporting. This new path downloads serially on the main
thread, allowing its one-shot alarm to interrupt opening/reading network responses;
it cannot wait for an executor queue after interruption. Per-read deadline checks
and at-most-one underlying read supplement the alarm. Existing workflows retain
their original concurrent path. TERM disarms the pending alarm before unwinding;
existing exact-owned-CID one-shot removal keeps its30second bound. Host loss or
repeated termination can still leave cleanup uncertain. There is no broad cleanup,
retry, uncertain-directory removal or claim of success after interruption.

## Measurement and trust

After the same-run build/export receipt succeeds, the coordinator reconstructs the
canonical handoff manifest from trusted in-process build evidence and independently
computes its SHA256. It checks the export receipt against that expectation, then
feeds it to the merged retention inspector. It never uses a received manifest or
adjacent digest to manufacture its own trusted expectation.

The handoff remains exactly `api.tar`, `web.tar`, `manifest.json`, `evidence.json`
and empty `COMPLETE`. Original archive bytes are unchanged. Metadata is included in
the16GiB input limit. Successful stdout contains only sanitized tool/source commit,
manifest digest, exact five-file byte counts/hashes and unresolved blocker flags.
It excludes raw build logs, host paths, credentials and source-file inventories.
Uncertain completion preserves the safe commit/digest receipt; cleanup failure stays
explicit. Inspect outcomes before any later attempt; never blindly retry.

No uploader exists. Actual archive sizes are not ZIP stored size or public-content
clearance; checksums are not provenance or secret scanning. `upload_authorized`,
`zero_incremental_cost_verified`, `content_clearance_verified`,
`stored_artifact_size_verified` and `artifact_expiration_verified` remain false.
The only conditionally approved future destination is this repository's Actions
artifacts for exactly7days and at most16GiB, after actual zero incremental cost,
content and size conditions are verified. Current billing evidence has not proved
that capacity; changing budgets/accounts/settings or using another store is outside
scope. A build-only run would discard its temporary media when the runner expires.
Do not dispatch merely to repeat previously discarded image preparation.

The staging laptop is reported Windows10 Home x64 with more than50GB free;100GB is
only a possible future expansion, not verified capacity. The laptop may connect to
the intranet and copy directly to the server, so USB is not required. Preserve
pre/post-copy hash verification in any later transfer. Server capacity/filesystem,
actual laptop storage and Docker availability remain unverified. This code neither
installs Docker on that laptop nor accesses the company network/server.

## Validation boundary

Synthetic tests exercise the actual handoff exporter/inspector with non-runnable
tar fixtures while replacing the builder; they do not prove a real image builds.
They cover receipt/archive tampering, unsupported source before copying, checkout
failure before builder, serial acquisition interruption, deadline/TERM restoration,
uncertain completion/cleanup diagnostics and inert default/workflow boundaries.
Full existing offline, automation and CI guard suites remain required. Exact-head
ordinary CI provides code acceptance; real media build, seven-day retention,
physical offline operation and company acceptance are separate unexecuted stages.
