# API-only image preparation: unwired internal helper

Current integration update (2026-11-10): an internal, default-false same-run lifecycle
path is prepared in the coordinator. CLI/workflow remain migration-only and no new
actual API runtime has been performed. See [current lifecycle scope](offline-api-lifecycle-integration.md).
The earlier future/unwired statements below describe the original package.

## Baseline and scope

The independent development checkout starts at PR211 merged main
`d962d223aa228bdbf5967e8376dba65822786deb`. The coordinating task verified
[main CI42763796692](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42763796692):
3565 backend tests, 2720 subtests, 308 PostgreSQL cases without skips and 16+16 strict
browser cases. Cloudflare build `75b0dae0-33db-4cb9-b0ec-ff8a9faede0a`, version
`efacbd0b-9570-45dc-82f2-485cf6481746` succeeded. This is baseline evidence, not this
candidate's CI, real API image preparation or deployment acceptance. Render was
not verified in this package.

This package introduces `scripts/offline_api_image_preparation.py`, pure mock
contracts and this document. It does not modify existing workflows, builders,
Dockerfiles, production code, dependencies, migrations or acceptance gates.
No CLI/main is provided. Import, direct invocation and `--help` perform no work.
No existing caller invokes `prepare`.

## Trusted internal contract

`prepare(commit, *, root, budget)` requires a reviewed clean exact-commit checkout,
a new private preparation directory outside that checkout, a trusted local daemon,
separate authorization for actual acquisition/build, and the caller's original
`offline_migration_image_rehearsal.Budget`. The caller retains signal/interruption
handling. No Boolean, receipt, Python object or digest authorizes work.

The helper establishes the existing host adapter itself: Linux amd64, Python 3.12,
existing Docker/BuildKit, fixed local Unix socket, sanitized configuration and
20 GiB host/daemon free-space checks. It rejects inherited daemon/proxy overrides.
It does not accept a configurable daemon, external image ID, build callback or URL.
The original deadline is never refreshed; each subprocess uses its remaining
allowance, reserving 630 seconds plus the Budget's 30-second margin for downstream
work. That is a safety floor, not proof two builds and a later rehearsal will fit.
Insufficient time fails closed; a later coordinator must budget its entire order.

A bounded source child checks tracked exact bytes, clean HEAD before/after,
regular Git blobs, loaded local tool locations and filter configuration. The
API context includes only app Python/JSON, requirements/lock/inventory, the existing
API recipe, base metadata and wheel verifier. Tool dependencies are source-bound
but not copied into the API image. No migration context substitutes for API bytes.

The existing bounded wheel acquisition child retrieves the 30 reviewed public
wheels with no retries. A second bounded child independently repeats source checks,
compares the source manifest digest, verifies wheel hashes/archive metadata and
writes a new regular-file tar. Tar members and copied wheel bytes are bounded;
manifest records bind exact source/wheel sizes and SHA256 values. The existing API
Dockerfile validates the hash-locked offline dependency closure and runs pip check.
No npm, frontend build, docker-save export, Compose or container smoke is added.

The pinned Python base is pulled once and its exact config/platform checked.
Build uses `--network=none`, `--pull=false`, `--no-cache`, linux/amd64, the exact
commit and a fresh iidfile, consuming the verified tar through one open descriptor.
Its digest is checked before and after build. The output ID comes only from that
new iidfile, never a tag lookup. Existing startup image inspection checks the exact
ID/commit, fail-closed entrypoint, nonroot user, platform and allowed environment.

The small receipt reports image ID and context/build digests. It always reports
application_started=false, database_connected=false and provenance_authenticated=false.
These checks are consistency under trusted checkout/daemon assumptions, not signed
provenance, hostile-same-UID protection, authorization or complete runtime evidence.

## Failure and cleanup boundaries

No API, migration or PG container is created here. There is no container cleanup,
image deletion, name scan, prune, export, upload or automatic retry. Private wheel,
context and iid evidence stays in the run directory for diagnosis; no artifact is
published. A pull/build timeout or interruption is uncertain: killing its CLI does
not prove daemon-side work stopped. No successful receipt is returned after failure.
A future trusted coordinator must install appropriate SIGTERM handling before
actual use; hard termination and host loss remain limitations.

## Later integration, not part of this package

Build the API before PG creation. Only after the existing migration has exited and
its finite observation passed may a separately reviewed internal path call
`offline_migrated_api_probe.run_probe`, before the coordinator's PG finally cleanup.
Pass the live owned PG object, observed netns, this same-run image result, original
Budget and outer daemon adapter. Do not pass the old 300-second migration-stage
closure to the API stage. Do not accept a receipt from a previous run as provenance.

The probe owns API removal; the coordinator owns migration then PG cleanup, even
on errors and control exceptions. API work/cleanup/post-observation currently have
120/40/30-second caps and a 330-second entry floor. Reserve at least the prior
300-second migration allowance plus that floor before creating PG, and separately
review acquisition/build time and outer cleanup margins. Preserve old CLI/default
workflow behavior and avoid a top-level joint/probe circular import.

Default read-only sessions under temporary postgres superuser trust are not a
SELECT-only role. Selected catalogs/counts, read-path results and 403/401 refusals
are not complete schema, real identity, physical isolation or company acceptance.
Actual runtime and publication need their applicable approvals separately.

## Local evidence

Six initial missing-capability contracts failed before implementation. Discovery
then passed 24 focused contracts and 726 full offline tests without skips.
52 automation tests, in-memory compilation, progress and diff checks also passed. Tests
cover source binding, dirty/wrong/filter checkouts, source types/limits, unsafe
paths, tar bytes, source/wheel changes, collision rejection, original budget,
API-only mocked command order, pull/build/image failures, malformed/missing iid,
archive changes, interruption and no retry. All acquisition, Docker and DB work
is mocked; no real dependency/base downloads or containers were executed.
Review identified two bounded issues: legacy host preflight allowances did not reserve
downstream time, and legacy IID reading normalized KeyboardInterrupt. Regressions
first reproduced 30 seconds instead of 1 at the near-budget floor, and the swallowed
control exception. After specific notice and clearance, the new helper alone gained
a private reserve-aware host Budget view and a no-follow 72-byte IID reader that
preserves KeyboardInterrupt/SystemExit while retaining ordinary-error normalization.
Full preparation and reader tests cover both controls. A separate failing test
proved the main guard preceded added classes; moving it to the end makes direct
execution and discovery both run all focused cases. No old helper was edited.
Independent final review passed with no blockers: 24 focused tests passed in both
execution modes; additional mocked real-host allowances were [3, 2, 1] seconds,
reserve exhaustion/deadline mutation rejected, IID hardlinks rejected, and exact
control-exception objects preserved. Exact-candidate full CI remains pending.
No publication.

Business remains 36/44=82%, acceptance increment 0; modules
100/100 demo/100 demo/100/89/60/17; plan 100/100/20/33/40/40/0;
browser stage 1/4 and finite plan 8/8 unchanged.
