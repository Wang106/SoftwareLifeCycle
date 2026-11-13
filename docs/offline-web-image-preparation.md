# Reserve-aware Web-only image preparation

## Scope and authority

`scripts/offline_web_image_preparation.py` adds an internal
`prepare(commit, root=..., budget=...)` callable. Import and direct script
execution do nothing. No CLI, default invocation, workflow wiring, API build,
application/container start, HTTP/database probe, image export/upload or new
resource is added. Existing implementation files, dependency locks, Dockerfiles and workflows
are unchanged; four checkpoint files are updated. This is preparation for a future same-run Web → API → PostgreSQL
integration, not another runtime probe or evidence that integration works.

A future caller must independently trust the reviewed exact clean checkout and
local daemon and have explicit authorization for acquisition and image building.
Calling a Python helper or supplying JSON does not confer that authorization.
Labels, digests and receipts establish consistency, not authenticated provenance.
Tests use mocked daemon/acquisition operations and tiny local files only.

## Original deadline and admission arithmetic

The caller supplies the existing `offline_migration_image_rehearsal.Budget`
created from the original job start, before checkout. This helper never creates
a Budget, changes the deadline, resets the clock, or grants another 55 minutes.
It rejects a different Budget type, nonfinite deadline, mutation during work,
and insufficient remaining time. The existing 60-minute job ceiling is unchanged
because this package does not edit or invoke workflows.

Every work allowance retains **1,630 seconds downstream + 60 seconds owned local
cleanup + the existing Budget's 30-second final margin**. The 1,630 is:

- Existing migrated-API coordinator pre-PG admission floor: **1,330 seconds**,
  comprising 600 PG pull + 300 migration work + 430 API work/guards and reverse
  cleanup headroom. Existing subsequent phase-specific checks still apply.
- Provisional additional Web work/cleanup allowance: **300 seconds**, including
  180 work + 35 cleanup (the separate startup contract's current maxima) + 85
  coordination headroom. No existing startup function is called here: its own
  fresh phase clocks are not a same-budget integration implementation.

At an entirely unused original 3,300-second budget, at most **1,580 seconds**
remain for all Web source checks, acquisition, audit, pull, build and inspection.
Earlier checkout/tests/builds reduce that window. Per-operation caps are clipped
by the remaining allowance, including the nominal 1,800-second build cap.
This may reject a real build and is not a claim it can finish in that time.

These reserves are **admission floors**, not duration estimates or proof that
all three layers fit. They do not reserve additional migration/API image build
time. A future coordinator must choose ordering, retain the same original
Budget, independently apply all stronger admission/phase floors, bound Web work
and reverse cleanup on that deadline, and reject insufficient time before new
work. Increasing or composing the budget is outside this package.

## Source, artifacts and daemon custody

The source child verifies exact HEAD, clean tracked/untracked status, no Git
filters, regular nonexecutable Git blobs, no-follow single-link local file reads,
byte equality to Git, and the complete transitive repository tool set. It selects
only the existing allowlisted frontend inputs plus the dedicated Web recipe and
base inventory, never backend application code. It enforces source counts and
size limits and checks the two pinned official Node FROM references.

The source child returns only a compact source-manifest commitment, not the
roughly 584 KB npm inventory. Acquisition independently re-reads exact sources,
checks all 399 lock-derived entries and sizes, then uses the existing official
registry fetcher in batches of four: no credentials, redirects, proxy bypass,
mirror or retry. A bounded child contains the total acquisition duration.

Context construction independently re-reads source again and applies the
existing full tarball integrity/metadata/expanded-size audit against the exact
recorded inventory. Artifact bytes are checked again while packing a private
exclusive tar; each artifact is streamed, not accumulated as a whole in memory.
The build manifest binds source commit, source hashes, artifact hashes and sizes.
The tar is hashed before and after Docker consumes the already-open input file.

The supplied root must not exist and must be under an existing trusted parent
with no symlink ancestors. Placement outside the clean checkout is an explicit
caller prerequisite, not a containment check enforced by this helper. It is created exclusively
with mode 0700; context output is exclusive mode 0600. Paths are caller-owned
local paths, never a user-uploaded receipt's output paths. The existing host
policy requires Linux x86_64/Python 3.12, available capacity, installed Docker,
no inherited daemon/proxy overrides, a new private Docker config and the fixed
`unix:///var/run/docker.sock` endpoint. No settings are changed or installed.

Only the pinned official Node base is pulled. Exactly one Web image is built
with linux/amd64, no network, no pull during build, no cache, exact source revision
and an exclusive IID file. Inspect uses the immutable image ID and requires the
same revision, linux/amd64, nonroot user, `/app`, `/bin/false` entrypoint, empty
command, no volumes/healthcheck/onbuild and the expected Node/Yarn environment.
This reuses the existing Web image contract; it is not an application start.

## Cleanup, failures and receipt

All child output and time are bounded by the existing hardened command runner;
stderr is discarded and ordinary public-entry errors use one fixed redacted
code. Control exceptions propagate. The local read wrapper deliberately preserves
interruptions without changing the legacy convenience reader.

Only after a verified image does a bounded child remove this operation's private
local inputs, first verifying the recorded directory identity and using
symlink-resistant descriptor-relative removal. It has at most the reserved 60
seconds while retaining downstream time. Failure, identity mismatch or uncertain
cleanup prevents a success receipt. This does not remove any Docker image.

Before that success path, errors or interruptions retain partial private inputs
for investigation. Terminating a CLI does not establish that daemon pull/build
work stopped. There is no blind retry, image removal, prune, name-based cleanup
or inferred ownership. Failed/uncertain cleanup is never retried automatically.
A retained directory must not be reused as a new operation root.

The fixed 11-field receipt contains format/status, exact commit/immutable image
ID, source-bound context-manifest and tar SHA256, `local_inputs_removed=true`,
`application_started=false`, `database_connected=false`,
`provenance_authenticated=false`, and fixed limitations. A future caller must
validate exact keys/types and expected values, independently trust the producing
execution, and retain its own phase admission checks; imported JSON cannot prove
execution or authorize follow-on actions.

## Validation and remaining work

Regression-first: eight tests failed with the module absent, before implementation.
An additional interruption regression failed before the preserving reader existed.
A dynamic-route packing regression failed before the narrowly authorized Web-only
path validator was added; the shared migration grammar remains unchanged.
The scoped suite now covers source selection/binding, dirty/filter/wrong commit,
symlink and changed bytes, fixed receipt, private path rejection, deadline
mutation/exhaustion, compact child data, Web-only commands, exact image checks,
context/archive changes, failed acquisition/build/cleanup, no retry and interrupt
retention. Artifact packing uses tiny synthetic files, not downloaded packages.

Synchronized baseline is main `23e3153f2996d7afbc1bcb9802d062d3070895a8`.
Its CI43034751465 succeeded at 14:18:03 UTC: 3791 tests / 3122 subtests,
309 PostgreSQL cases without skips, frontend, strict Chromium and aggregate.
Artifact13862634185 SHA256
`50121eda7f2b096cc26a115849b49512e6d4f01cf9a7bb1985a96aac20d83dea`
matched with clean XML; recovery source/checkout matched main and protections
were enabled. Cloudflare production build `a34ddad2` succeeded; Actions
deploy43037153555 and continuation43037153829 skipped; Render unverified.
This is baseline evidence only; candidate CI remains pending.
Local validation passed: 20 scoped tests, 943 all-offline tests, 52 automation
tests and 126 CI guards without skips, Python compilation, progress and diff
checks. All 265 selected tracked input paths validate, including 47 dynamic-route
files; a regression packs actual tracked route bytes. Independent final review passed with no remaining code blocker: the reviewer
passed 20 focused tests, packed all 265 tracked sources with exact bytes and
archive hash, and exercised tiny owned-directory cleanup. Publication and
exact-candidate CI remain pending. No actual downloads, Docker calls, image builds, API,
HTTP, database, workflow execution, uploads or deployment occurred for this
package. Full candidate CI and independent review are separate requirements;
real same-budget Web/API/PG integration remains future separately authorized work.
