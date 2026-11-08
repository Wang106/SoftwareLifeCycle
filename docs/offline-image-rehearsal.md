# Manual connected image preparation and dependency rehearsal

Baseline main: `9cd5517611390b7e427b7de64e3c743a41c75d10`, 2026-11-07.
This package implements the smallest image stage from the
[image design](offline-readonly-image-rehearsal-design.md), using the existing
[30-wheel lock](offline-python-wheelhouse.md) and
[399-tarball npm collection](offline-npm-artifact-install.md). It adds dedicated
recipes, a bounded orchestration script, regression contracts and one **manual**
standard-runner workflow. The production Dockerfiles, locks, deployment workflows,
CI/branch protection and business scope are unchanged. The later strict classic-save
compatibility change below extends the preflight with one validated manifest variant.

## Initial implementation evidence (before PR192)

Official Docker Hub public HTTPS index, linux/amd64 manifest and config bytes were
retrieved and their SHA256 digests checked on 2026-11-07. Anonymous public pull
tokens were used only for the matching official registry requests; no account
credential, private registry, fee or login was used or recorded.
[`base-images.json`](../deploy/offline/base-images.json) records the immutable
platform manifests separately from the multi-platform indexes and image configs:

- Python `3.12.14-slim-bookworm`: platform manifest
  `sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a`.
- Node `22.23.4-bookworm-slim`: platform manifest
  `sha256:aaa4b5baf1ecff3b283486bb1f90405cdda225a3e6f79660d2c559fa510a7292`.

Both configs report Linux amd64, only original-preflight-allowed environment keys,
and no image-declared Volume. These are Debian Bookworm/glibc images, **not Ubuntu
images**. An Ubuntu 24.04 host does not change the container userland. HTTPS plus
hash verification is not a publisher signature, security/license review or
vulnerability clearance. Tags are recorded as provenance; builds use only digests.

This development workspace has no Docker executable. `--check-host` actually
returned `BLOCKED` before downloads, pulls, image builds or containers. New tests
are static/mocked contracts, not runnable image acceptance. The first tests failed
because the new module did not exist. Additional failure-first cases caught the
workerd module export, sensitive filename rejection and default local Docker
context before correction. **No image build/save, container smoke or real Compose
parse has passed here. The manual workflow has not been dispatched by this package.**

The original 33 new regressions and all 211 original offline regressions passed locally.
The packaging acquisition/audit function was also exercised against private copies
of the already retained **real** 30 wheels and 399 tarballs, substituting local
copy only for network acquisition. The existing pip closure passed and the real
npm archive audit exactly matched the committed 785,874,731-byte collection. This
rechecks input integration; it does not execute either Docker recipe or prove a
container runtime. Explicit Python native-extension imports prevent a pure-Python
fallback from being mistaken for a native pass.

## Authorized execution and prerequisites

Run only on an explicitly authorized disposable Linux amd64 Docker environment.
The workflow is `workflow_dispatch` only, one `ubuntu-24.04` job, 60-minute limit,
one global concurrency group, `contents: read`, checkout pinned to the existing
reviewed SHA, and `persist-credentials: false`. It contains no service database,
repository secret, login, persistent cache, artifact upload, registry push,
self-hosted/larger runner, software install or host reconfiguration. A manual run
must separately satisfy the user's permission and fee restrictions. Public standard
GitHub-hosted runner compute being free does **not** imply all repositories,
accounts, data transfer or other resources are free.

The **first step before checkout** checks existing Docker client/server, Linux
amd64, Compose >=2.30.0, existing Python 3.12/pip and >=20 GiB free on both temporary
and Docker storage filesystems. No version/capacity failure triggers an install,
upgrade, disk cleanup, security-setting change or alternate runner. The script
rechecks prerequisites before any preparation and also requires actual `config --help`
option lines for `--no-env-resolution` and `--no-interpolate`. A missing capability
stops before run-directory creation, downloads or builds; the version minimum alone
does not prove flag support. No automatic install or upgrade is attempted. It forces
the default local Docker
context, rejecting inherited target overrides. A local daemon/filesystem must be
available. The disk threshold is a conservative entry gate, not a hard bound on
image growth or proof that every future dependency set will fit. GitHub documents
14 GB SSD storage for standard Ubuntu runners; the 20 GiB free-space gate can
therefore block this workflow on a normal standard runner. This package does not
promise the selected runner can actually execute the rehearsal, lower that gate,
clean disk, or silently switch to a paid/larger runner.

For an already approved disposable host and **clean, committed** checkout:

```sh
python3 scripts/offline_image_rehearsal.py --check-host
python3 scripts/offline_image_rehearsal.py --run
```

`--run` does perform public downloads and local image/container operations. It is
not a read-only diagnostic or authorization for company-server installation.
Do not run it against a personal machine, existing service host or company target
without the appropriate approval. Do not change the daemon export/storage driver
merely to make this test pass.

## Exact inputs and connected preparation

The driver snapshots only regular files from the **exact clean Git commit** using
`git show`; it does not copy working-tree contents, Git metadata or untracked files.
The allowlist is explicit: backend `app` Python/JSON, frontend `app` TypeScript,
TSX/CSS/JSON, `components` TypeScript/TSX, `lib` TypeScript/TSX/JSON, and individually
named package/TypeScript/Next config files, locks, inventories, recipes and existing
auditors. Dotfiles, `.env*`, npmrc, credentials/secret-named files, links, executable
source files, tests, reports, local caches, operator data, migration configuration
and the production entrypoint are excluded. It records each selected source SHA256.
This is a trusted-source selection rule, not a general-purpose secret scanner or
a claim that arbitrary code cannot contain hardcoded secrets. Source review remains
necessary; no real secret/configuration is supplied by this workflow.

Before acquiring any artifact, the downloader refuses inherited proxy overrides
(case-insensitive `*_proxy`, including empty values and `no_proxy`). It emits a
fixed `BLOCKED: inherited proxy configuration requires review` diagnostic, without
printing the proxy URL, credentials or raw exception. It neither removes these
variables nor bypasses a required proxy, changes routing or retries directly.
Proxy-required environments need separate review; this guard is tested with
synthetic in-memory responses and no network connection.

Both existing inventories and lock consistency are checked before acquiring any
artifact. Up to four official HTTPS GETs run concurrently, without credentials,
redirects, retries or mirrors. Bytes are streamed into exclusive new files with
expected size/hash and time limits. A failure cancels queued requests; already
in-flight reads can finish. Exactly 30 wheels and 399 npm tarballs are required.
The original wheel validator performs its full offline pip closure check, and the
original npm archive auditor recreates and exactly compares the committed audit.
No dependency version, platform selector or checksum is regenerated.

Docker pulls only the recorded official platform digest, and its resulting config
ID/OS/architecture must match the recorded config. Builds have no cache reuse, pull
fallback, package-manager upgrade or arbitrary build arguments. Docker's ordinary
builder may still need network for the already pinned base before running stages.
The dedicated recipes use only local dependency inputs in their `RUN` commands:

- API: local wheels, `--no-index`, full `--require-hashes` lock, binary-only install
  and `pip check`; no `--no-deps` bypass. Its builder also reruns the existing full
  wheel audit/closure using the actual Python image. Final runtime copies installed
  site-packages and allowlisted `/app/app` source into the same Python base.
- Web: all local tarballs populate a new isolated npm cache with scripts suppressed
  only during cache import. `npm ci --offline` then executes actual lifecycle
  scripts with dev/optional dependencies included, followed by `npm run build`.
  The build uses an allowlisted process environment, empty npm configs, telemetry
  disabled and empty build-time API/public URLs. Final runtime keeps `.next`,
  `node_modules`, package.json and Next config at `/app`.

`npm --offline` does not prevent lifecycle scripts or Next from independently
attempting HTTPS fallback. **No `--network=none`, firewall change, network namespace
policy or physical disconnection is configured in this package.** Local-input
installation and connected preparation do not prove egress isolation.
No extra Dockerfile `ENV` or `VOLUME` is baked. Both images label the exact source
commit and set UID/GID65532. Runtime paths match the original Compose generator:
`/usr/local/bin/python`, `/app/app`, `/usr/local/bin/node`, and
`/app/node_modules/next/dist/bin/next`. Both images instead default to the fixed,
side-effect-free `ENTRYPOINT ["/bin/false"]` and empty `CMD`, immediately exiting
nonzero. A bare `docker run` cannot start the application or fall back to unsafe
application environment defaults. Only an explicitly supplied smoke or separately
approved original Compose entrypoint can start a process. No extra baked `ENV`
or weakened preflight is used to achieve this. There is no migration/seed entrypoint.

## Real archive gate, native smoke and Compose parsing

Each built immutable image ID is exported with ordinary `docker image save`, one
uncompressed archive per service. Its size, SHA256, image ID, platform and source
revision go directly to the `archive_image` validator against the original save
bytes, once. The original three-field manifest format remains supported, alongside
the strictly validated four-field `LayerSources` variant specified below. Unknown
fields are never ignored. All original config, environment, Volume, layer-digest,
archive integrity and path restrictions remain. An unsupported OCI/containerd or
registry export **fails closed**. The script does not convert archives, replace
manifest fields, modify Docker settings or retrieve layers from a network. Actual
runner export compatibility still requires a separately authorized real run.

Only after that gate does a container run fixed dependency smoke code with
`--pull=never`, UID/GID65532, read-only root, all capabilities dropped,
no-new-privileges and `/tmp:rw,noexec,nosuid,size=64m`; it also bounds process count,
memory and CPU. Existing Docker security settings remain unchanged. The API smoke
records Python/glibc, imports direct/native dependencies, checks psycopg-binary,
compiles source syntax without executing app modules, and writes synthetic bytes
only to tmpfs. The web smoke records Node/glibc, checks the built Next entrypoint,
executes SWC, ast-grep, sharp/libvips and esbuild functions, invokes workerd
`--version`, and writes synthetic tmpfs bytes. **workerd version is not a Worker
response test.** No `app.main` import, Next server, route handler, DB connection,
migration, seed or identity/business action is started by these smoke commands.
Application service commands appear only in the unchanged, separately approved
Compose profile; image defaults always refuse to run.
Next's normal build can evaluate build-time code; it receives no live API/DB URL.

Smoke uses `docker create --cidfile` before `docker start --attach`, retaining the
exact full container ID in a fresh private per-smoke record before process startup.
It checks the actual container exit code and, in a `finally` block on success,
ordinary error or subprocess timeout, force-removes **only that exact CID**. There
is no name wildcard, image-wide removal or prune. A missing/invalid CID, failed
removal or unconfirmed removal emits an explicit cleanup-failed-or-unconfirmed
`BLOCKED` result, and never returns a successful rehearsal. The retained CID and
command log support operator diagnosis. A daemon-side uncertain create without a
CID cannot be safely cleaned by guessing; it is reported as unconfirmed. Process
hard-kill, machine loss or unavailable Docker daemon can prevent cleanup, so this
is not a guarantee against every host failure or workflow cancellation.

The real generated manifest is passed to the existing `compose()` helper with a
new **empty** temporary `database.env`, solely so Compose can parse its raw-env-file
shape. Normal `docker compose config --format json --no-env-resolution` retains
its project consistency checks. A second call adds `--no-interpolate` to inspect
the complete model. Both must succeed and match the original settings as specified
below, including image IDs, localhost-only commands, disabled gates, read-only policy
and bounded logging. Only the precisely observed omission of API `env_file` in the
normal project output is permitted, and only with the full model proving the exact
path, `required: true` and `format: raw`. No extra fields, mounts or builds are allowed.
The script does **not** call `validate(bundle)`, invent `operator.json`, supply a
fake password, approve a database role or run `compose up`. This proves parsing
only, not a valid operator bundle or service readiness. Any unanticipated Compose
normalization is a blocker for review, not grounds to silently relax comparison.

## Evidence, failure and remaining acceptance

The fresh private system-temporary run directory contains command logs, exact
source snapshot/hashes, downloaded inputs, build contexts, two image archives and,
only after every stage succeeds, `manifest.json` plus `evidence.json`. Standard
output reports the complete result only then. Errors emit the fixed failed stage
without raw exception/credential text; logs remain temporary on the authorized
runner for diagnosis. A successful GitHub summary contains exact source, image IDs,
archive hashes and limitations. A failed/cancelled run says no acceptance. Files,
images and logs are **not uploaded**; ordinary GitHub step logs/summary remain
visible under that repository's existing access and retention policy. Ephemeral
runner teardown eventually removes local images/files. This is not retained backup.

Success means `IMAGE_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE`, not a deployable
company bundle. Still missing: actual disconnected import/start/health/browser,
validated read-only synthetic DB and schema, app nonroot/read-only runtime behavior,
log rotation/recovery, malicious package analysis, signature/license/security
clearance, dependency/OS/bootstrap completeness, target transfer/rollback and
company installation/identity/business acceptance. The expired public database is
not rebuilt. No permissions, credentials, network/security configuration, spending
limit or branch/test gate is changed.

Business36/44=82%, delta0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser-stage1/4 and finite-plan8/8 remain unchanged.


## Safe export diagnostics follow-up

Diagnostic baseline: main `c1da9b12c9ad4aaf9f66068a9d12df24a3b07017` (PR192).
The two subsequent operator-requested manual runs
[42412440512](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42412440512)
and [42412466405](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42412466405)
failed at the original `api traditional docker-save validation` stage. The first
run reported Docker 28.0.4, 92,147,007,488 free bytes and passing host prerequisites
and 33 contracts. Those checks do not establish archive or runtime acceptance.
The stage bundled image-ID inspection, the save command, hashing and preflight;
its old fixed error did not distinguish them. The actual original failure reason
cannot be recovered from that message alone, and is not declared to be OCI.

A verified compatibility risk also exists with Docker's **classic** exporter:
[Moby v28.0.4 save.go](https://github.com/moby/moby/blob/v28.0.4/image/tarexport/save.go#L310-L315)
writes nonempty `LayerSources` metadata, populated with
[layer descriptors](https://github.com/moby/moby/blob/v28.0.4/image/tarexport/save.go#L600-L605).
At PR193, the preflight permitted only Config/RepoTags/Layers in that record and
rejected a synthetic tar with the additional field. That source-level risk did not
prove which input either original run rejected. The subsequent bounded compatibility
change below accepts only independently checked descriptors, not arbitrary extras.

The PR193 diagnostic-only follow-up changed the orchestration script, its tests
and this document. The exporter emits `BLOCKED` with one fixed, allowlisted export code and service role
(`api`, `web` or `unknown`), then exits nonzero:

- `IMAGE_INSPECT_FAILED` / `SAVE_COMMAND_FAILED`: the command wrapper reported a
  nonzero command result. No archive validation is claimed at either point.
- `IMAGE_INSPECT_TIMEOUT` / `SAVE_COMMAND_TIMEOUT`: the subprocess timed out;
  whether a daemon-side operation finished may be uncertain. Do not blindly retry.
- `IMAGE_INSPECT_ERROR` / `SAVE_COMMAND_ERROR`: another invocation, ID parsing or
  local logging error. These do not prove that the underlying command did not run.
- `ARCHIVE_READ_FAILED`: archive open/read/hash/stat or a preflight read outside the
  bounded inner-tar parser failed. Inner parser failures use its fixed tar code.
- `ARCHIVE_TAR_INVALID` / `ARCHIVE_JSON_INVALID`: the corresponding parser rejected
  its input. No raw parser message or input value is emitted.
- `ARCHIVE_FIELDS_REJECTED`: the original generic field-set diagnostic, retained
  in the finite allowlist. The later change below distinguishes item/manifest and
  descriptor structural failures without printing actual field names.
- Other exact original preflight reasons map to fixed `ARCHIVE_*` codes for
  provenance, checksum/size, paths/types, metadata/image count, config digest,
  platform/revision, environment/GPG fingerprint, Volumes or layers/digests.
  The mapping is an explicit finite dictionary, not prefix/substr matching.
- `ARCHIVE_VALIDATION_FAILED`: unknown, malformed or lookalike exceptions, and any
  attempted code not in the fixed allowlist. Exception string methods are not used.

Only allowlisted code and role constants enter the public export diagnostic.
Raw exception text, command output, filenames/paths, archive values, environment
values, credentials and the raw stage/role are never interpolated into that public
message. The existing private `commands.log` still records command arguments and
stdout/stderr, which can contain paths or other raw values; it is not automatically
published. No log/archive upload, workflow change, Docker setting change, retry
or archive conversion is introduced. PR193 left `archive_image()` byte-for-byte
unchanged. The strict compatibility change below intentionally updates that gate,
which remains the sole archive validator called once against the original bytes.
Diagnostics expose why a check stopped, not permission to bypass it.

The 13 failure-first diagnostic regressions cover distinct inspect/save/hash and
preflight failures, timeout behavior, real synthetic tar/JSON and LayerSources
rejection, known-reason mapping, unknown-code/role fallback and private-data sentinels,
including retaining api/web without exposing a raw stage or role. At that checkpoint,
46 focused and 224 full offline tests passed.
These are local static/synthetic checks, not a new manual run, image build/export,
Docker acceptance, application/DB startup or company deployment. The later observed run is recorded below; further real runs still require review
and authorization and are not automatically triggered. Business and acceptance
percentages remain unchanged.


## Strict classic-save descriptor compatibility — 2026-11-08

Baseline: main `40af759bc786659a847c95a7abbfd8bbab94012b` (PR193).
Manual run [42431684221](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42431684221)
reported `role=api; code=ARCHIVE_FIELDS_REJECTED`, 46 passing regression contracts
and 92,147,191,808 free bytes. In that exact code path the exporter constructs all
six item fields, leaving the manifest record field-set check as the rejection site.
The actual extra/missing field was not disclosed or directly inspected. This is
**not proof that this run's archive contains LayerSources**, nor evidence of image,
web/native-smoke, Compose, offline or deployment acceptance.

The new supported variant is narrowly based on the Moby 28 Linux classic exporter:
[manifest creation](https://github.com/moby/moby/blob/v28.0.4/image/tarexport/save.go#L310-L315),
[local tar descriptor fallback](https://github.com/moby/moby/blob/v28.0.4/image/tarexport/save.go#L594-L607)
and the [descriptor fields](https://github.com/moby/moby/blob/v28.0.4/vendor/github.com/docker/distribution/blobs.go#L62-L86).
The `roLayer.Descriptor` implementation is
[Windows-specific](https://github.com/moby/moby/blob/v28.0.4/layer/ro_layer_windows.go);
normal Linux classic-save fallback hashes the local uncompressed TarStream and
records its byte size. A registry compressed-blob digest is **not** an uncompressed
`rootfs.diff_ids` value and is never accepted as equivalent.

The preflight is intentionally changed, not byte-for-byte unchanged:

- Each manifest record has exactly `Config`, `RepoTags`, `Layers`, optionally plus
  exactly `LayerSources`. Missing required fields, `Parent` and every other unknown
  field are rejected. The original three-field branch keeps its existing behavior.
- In the four-field branch, `LayerSources` is a nonempty map with exactly the config's
  unique, normalized lowercase `sha256:<64 hex>` diff IDs as keys. Layers and diff IDs
  bind in their original order; missing, extra, repeated or crossed mappings fail.
- Every descriptor has exactly `mediaType`, `digest`, `size`. Only
  `application/vnd.oci.image.layer.v1.tar` is allowed. `urls`, `annotations`, `platform`,
  `data` and unknown fields are rejected even when empty; gzip/zstd, foreign and other
  media types fail. No URLs are followed and no network layer lookup is performed.
- Map key = config diff ID = descriptor digest = the actual SHA256 of that layer's
  bytes. Size is a positive integer, never bool/string/float, equal to the exact
  archive member byte length. Config and layers use the canonical
  `blobs/sha256/<matching digest>` paths in this new branch only.
- After hashing, every new-variant layer is read as an **uncompressed** tar using
  `tarfile` mode `r:`. Gzip/non-tar/truncated bytes with mutually consistent hashes,
  sizes and a false uncompressed media type still fail. This only validates tar
  structure: no extraction, decompression or filesystem writes. Parser reads are
  bounded to the remaining layer bytes and at most 1 MiB before allocation; GNU/PAX
  extension payloads are limited to 64 KiB and nested header processing to 64 levels.
  Every actual ordinary/GNU/PAX header is counted: at most 100,000 per layer and
  500,000 across all layers of one image archive. Cumulative parser-read bytes are
  limited to 64 MiB per layer and 256 MiB per image, including headers, extension
  payloads/padding, boundary probes and the first terminator. These logical budgets
  bound parser work, not exact Python process RSS. An explicit sequential `next()`
  loop releases each processed TarInfo cache entry immediately; inherited global-PAX
  dictionaries cannot accumulate per historical file in `tarfile.members`. Global
  PAX state itself remains available to subsequent entries. Ordinary large file
  payloads are skipped by a bounded seek, not charged as metadata; integrity hash
  reads and final zero-tail scans are separately chunked and not charged either.
  Image budgets reset between API/web archives, so a fixed two-image operator bundle
  has at most twice the per-image totals. These conservative support limits may
  reject an unusually large valid image; they are never automatically raised. Layers are 512-byte aligned with at least two zero termination
  blocks and only zero padding afterward. Numeric, recursive and other parser
  exceptions become the same fixed Invalid/tar code; process interrupts propagate.
  Empty tar layers and valid inner whiteouts, devices and links remain supported.
  Outer archive links,
  devices, traversal/duplicates and all original environment/Volume checks still fail.
- Classic archives can also carry OCI helper metadata such as `index.json` and
  `oci-layout`. As before, unused regular members are checked for safe outer names
  and types but do not become acceptance authorities. Only the checked docker-save
  manifest, config and local uncompressed layer bytes count. Pure OCI layouts and
  arbitrary compressed registry exports remain unsupported. Hashes/labels/format
  checks establish internal consistency, not trusted provenance or safe image code.

New finite diagnostics distinguish `ARCHIVE_ITEM_FIELDS_REJECTED`,
`ARCHIVE_MANIFEST_RECORD_REJECTED`, `ARCHIVE_MANIFEST_FIELDS_MISSING` and
`ARCHIVE_MANIFEST_FIELDS_REJECTED`. Descriptor diagnostics are
`ARCHIVE_LAYER_SOURCES_MAPPING_REJECTED`, `ARCHIVE_LAYER_SOURCES_PATH_REJECTED`,
`ARCHIVE_LAYER_SOURCE_FIELDS_REJECTED`, `ARCHIVE_LAYER_SOURCE_MEDIA_TYPE_REJECTED`,
`ARCHIVE_LAYER_SOURCE_DIGEST_MISMATCH`, `ARCHIVE_LAYER_SOURCE_SIZE_MISMATCH` and
`ARCHIVE_LAYER_SOURCE_TAR_REJECTED`. These are fixed categories, not the observed
field names or values. Existing role allowlisting, unknown-error hiding, strict
fail-closed behavior and private-command-log boundaries are unchanged.

Failure-first tests cover valid multi-layer descriptors and preserved three-field
acceptance, exact field sets/mappings/order, forbidden descriptor fields/media types,
digest/size/type corruption, compressed bytes falsely labeled as tar, empty/special
inner layers, oversized and recursive GNU/PAX headers, bounded pre-allocation reads,
end blocks/trailing data/alignment, flat and extension header limits, per-layer and
cross-layer metadata budgets, released member caches and correct global-PAX
inheritance, normal large file and extension metadata,
malformed/duplicate JSON, original safety rejections and public error redaction.
At the descriptor checkpoint, 57 preflight and 52 rehearsal tests (109 combined),
and all 269 offline tests passed locally with no skips. A Linux child with a 256 MiB address-space
limit also parses 9,000 empty files inheriting 1,000 global-PAX fields successfully;
the failure-first version exhausted that budget. This is a bounded synthetic
regression, not an RSS guarantee for every possible archive. These synthetic archives are not runnable image evidence.
No Docker build/save, new workflow, app/DB startup or offline acceptance is run by
this change; required exact-head CI and independent review remain separate gates.
The next real run can still expose a different unsupported format or later blocker.


## Strict Compose project/model verification — 2026-11-08

Baseline: main `1ec3a576fca54701ac7561649903989363aed770` (PR194).
The operator's [run 42446770307](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42446770307)
reached `Compose parse only` and then failed. Its source-stage order establishes that
both API/web builds, traditional saves, strict archive checks, dependency-only native
smokes and their precise container cleanup returned successfully before that stage.
It does **not** establish full rehearsal success, retained image evidence, application/
DB startup, disconnected operation or deployment. The old fixed stage message alone
did not identify the Compose rejection.

The run's exact [runner-image software list](https://github.com/actions/runner-images/blob/ubuntu24/20261101.360/images/ubuntu/Ubuntu2404-Readme.md)
reports Docker Compose 2.38.2. With explicit approval, the official standalone
[2.38.2 Linux x86_64 asset](https://github.com/docker/compose/releases/tag/v2.38.2)
was downloaded to a new temporary directory. Its 75,108,694-byte size and SHA256
`486b3ffc0f806ca2efbc430cef89955386011662f0c76bad17c103d059cfa9cf` matched both release
metadata and the official checksum file. It was not installed into the system.
Only version/help/config commands were executed with an empty isolated HOME/Docker
configuration and a process-local Docker target pointing at a nonexistent Unix
socket; the default daemon socket was also absent. No image pull/build, daemon,
container, registry, app or database operation was used in this local reproduction.
An optional syscall trace was denied by the environment and was not bypassed, so
there is no claim of an observed zero-connect syscall count.

The exact binary reproduced the original function's `raw env-file policy changed`
rejection: its normal project JSON **omits API env_file entirely**, while every other
field and the top-level document match. It does not produce the path-string variant
considered during source inspection. Adding `--no-interpolate` produces a model
identical to the complete generated document. This direct evidence supersedes the
earlier serialization hypothesis. A normal project call rejects a synthetic
`network_mode`/`networks` conflict that the non-interpolated model call accepts,
confirming why the model cannot replace the project's consistency checks.

The bounded fix changes only the rehearsal script, its tests and this document:

- Keep the normal project command and require success. Never add `--no-consistency`,
  `--no-normalize`, digest resolution, a fallback startup or an automatic retry.
- Also require the non-interpolated model command to succeed. Its entire document
  must exactly match `compose()` output. The normal project must match either that
  full document or precisely the same document with only API `env_file` omitted.
  Path strings, null/empty env-file values, omission in the model, changed raw/required/
  path fields, additional services and all other extra/missing/changed fields fail.
- Comparison is recursive and type-sensitive, so JSON `1` cannot stand for `true`.
  Duplicate JSON keys, malformed input and nonfinite numeric tokens are rejected.
  The original generator, archive preflight, recipes, workflow, locks, localhost
  behavior, read-only restrictions, identity/business gates and permissions are unchanged.
- Probe the two required flag capabilities before any run-directory creation,
  dependency acquisition or image build. Unsupported or malformed help fails closed;
  neither an older version nor an unavailable flag triggers an upgrade or download.
- Every Compose subprocess is limited to 30 seconds. Failures use only fixed
  `COMPOSE_COMMAND_FAILED`, `COMPOSE_COMMAND_TIMEOUT`, `COMPOSE_COMMAND_ERROR`,
  `COMPOSE_JSON_INVALID`, `COMPOSE_POLICY_REJECTED`, `COMPOSE_CAPABILITY_MISSING`,
  `COMPOSE_PREPARE_FAILED` or `COMPOSE_VALIDATION_FAILED` codes. Phase is one of
  capability/prepare/project/model/unknown, role is api/web/unknown, and field is
  a fixed known policy key or unknown. Constructor and emitter both sanitize these
  dimensions. Raw exception text, stage, paths, keys, values and command output are
  not copied into public diagnostics. Existing private command-log boundaries remain.
  Process interrupts propagate, rather than being converted into acceptance.

The 18 failure-first regression methods cover both required calls, the sole supported
omission, every service policy field in both views, unknown fields, exact JSON types,
duplicate/nonfinite JSON, command failures/timeouts, safe preparation/diagnostics,
process interrupts and capability failure before directories/downloads. All 70
rehearsal tests and 287 offline tests pass locally with no skips; compile/diff checks
also pass. These static/synthetic regressions include additional subcases; they are
not new runnable-image evidence.
The already approved official binary also rechecked the implemented function:
normal generated configuration passes; eight real config-only negative cases fail,
including missing raw, optional env file, changed path, missing env file, disabled
read-only mode, extra privilege, unknown extension and conflicting network settings.
The normal consistency rejection still prevents model-only success.

This package does not trigger a new full image rehearsal or upload its files. Exact
candidate CI, independent review and any later separately authorized complete run
remain distinct requirements. A future Compose version may produce another shape;
it must fail closed until specifically investigated, rather than silently broadening
the two supported variants. Business and deployment acceptance percentages do not change.


## Optional local handoff retention — 2026-11-08

Main `b471decc85495ff88dbe9c2f5419a0092b133cef` completed
[manual run 42463491932](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42463491932):
70 contracts, both builds/saves and strict archive gates, both read-only nonroot
native dependency smokes, and normal project plus complete model Compose checks.
This is complete connected rehearsal evidence, not application/DB startup, physical
network isolation, retained backup or company deployment. No image artifact was
uploaded; those ephemeral runner images are not available to a new local export.

A new optional `--export-bundle /absolute/existing-parent/new-handoff` argument to
`--run` retains only that new run's successfully validated `api.tar`/`web.tar`, a
strict handoff manifest and reconstructed safe evidence. Export happens after all
smoke and both Compose stages return successfully. Default runs remain temporary
only, and `--check-host` cannot export. At introduction this did not change the
workflow; its later opt-in wiring is described below. The new
tool is included among the exact-commit snapshot's required tool source files.

The destination is exclusively new. Copies use bounded IO and exact hashes;
directory/file descriptors and identity checks prevent pathname substitution from
redirecting reads/writes. Revalidation uses the unchanged strict archive gate with
a pinned-FD adapter, not rewritten archives or a relaxed preflight. An additional
bounded outer-tar scan limits header/extension processing and the inherited PAX
state the unchanged validator will cache; actual file size is checked before it.
Outer sparse-envelope expansion is rejected, without changing inner-layer policy.
A fixed 16 GiB
two-archive support limit and 1 GiB free-space reserve are conservative checks, not
real peak-size guarantees. The final empty `COMPLETE` marker is created only after
payload checks and closes; earlier failures leave partial output without it. Final
commit/close/response interruptions can instead be uncertain and are explicitly not
reported as success or automatically retried. Their fixed safe diagnostic includes
only the commit/hash expectations already constructed by the trusted exporting
process, enabling read-only recovery without trusting a hash from the uncertain
bundle. Completion-window interrupts still stop execution without raw exception
text. No partial directory is deleted.

The separate read-only verifier requires externally trusted expected commit and
manifest SHA256, checks all files and the original archive contracts, and never
runs Docker, extracts, connects or writes. Checksums prove integrity against those
expectations, not signatures or image safety. No command log, raw native output,
credentials, database configuration, source paths or operator approval enters the
handoff evidence. See [the image bundle contract](offline-image-bundle.md) for exact
files, invocation, schema, IO/path assumptions, incomplete/uncertain handling and
acceptance limits. The implementation and regressions do not execute a real
full-sized handoff or a new Docker rehearsal; all operational acceptance remains
separate.


## Manual workflow option — 2026-11-08

The manual `offline-image-rehearsal.yml` workflow now offers the boolean
`export_bundle` input, **default false**. Leaving it off keeps the existing single
rehearsal with no bundle export or separate verifier. Enabling it adds
`--export-bundle` to that same rehearsal, then invokes the read-only bundle verifier
in a **new Python process**, only after the rehearsal returned success. This change
implements and mock-tests the option; it does not dispatch or run the workflow.

The coordinator accepts only the exact environment values `true` and `false`.
The GitHub expression is assigned to an environment variable, never interpolated
into shell/Python source or appended as arbitrary arguments. Before running the
rehearsal it requires a lowercase full `GITHUB_SHA` and an exact matching checked-out
Git HEAD. An enabled export gets a randomly named absolute destination beneath
`RUNNER_TEMP`. A collision, including a dangling symlink, fails; the exporter
exclusively creates the directory, and no existing path is overwritten, reused,
removed or retried. No bundle path is printed in the public summary.

The successful run's status, source commit, image records and Compose result must
match the fixed contracts. The coordinator validates an exact export receipt and
reconstructs its expected manifest from that trusted run result to bind the digest
to those same image records. It never reads the bundle to obtain trusted expected
values. The separate verifier receives the run's commit and manifest SHA256 as
arguments; its exit status and exact returned status/commit/hash must all agree.
Missing, duplicate-key, nonfinite (including numeric exponent overflow), malformed,
oversized or contradictory results,
nonzero exits, timeouts and process interrupts fail the job. There is no verifier
fallback, export retry or cleanup of a partial/uncertain destination.

Child stdout is captured in a new private temporary file, with parsing limited to
4 MiB for the rehearsal result and 64 KiB for the verification receipt. A local
finite-float parsing hook rejects overflow even in unused nested metadata, without
a second recursive traversal; finite numeric exponents remain supported. These are
read/parser limits, not live capture-file disk quotas. Child stderr and raw
exceptions are not published. Failures show only a fixed phase diagnostic, and
failed/uncertain export output is not promoted to a verification receipt. The
summary is assembled only after every requested stage succeeds; it contains fixed
statuses/limitations plus validated commit, image IDs, archive hashes and, when
requested, manifest SHA256. Raw host/native output, local paths, logs, supplied
limitations and credentials cannot be copied into that summary.

Export creates an additional temporary copy of the two images and revalidates them;
the independent verifier reads them again. This costs extra disk and processing time.
The existing 20 GiB host prerequisite, standard ubuntu-24.04 runner, read-only
repository permissions, serialization and **60-minute job limit** are unchanged.
The export still enforces its separate 16 GiB combined-archive support limit and
1 GiB reserve. Neither limit guarantees enough peak capacity or completion within
the job timeout. A default run does not acquire the export-only capacity limit.
An oversized/slow run fails rather than increasing resources, timeouts or limits.

The bundle remains on the **temporary runner only**. There is no artifact upload,
persistent cache, registry publication, transfer or downloadable handoff. The
summary is an integrity record, not a retained backup, signature, security/license
clearance, offline test or deployment approval. No application/database startup,
physical disconnection or company-server acceptance is added.

The actual earlier successful run remains
[42463491932](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42463491932)
on `b471decc85495ff88dbe9c2f5419a0092b133cef`; it did not execute this export option.
The baseline for this package is `95837a409f46bd2f9029a6778beb30a23ee3016a` (PR196),
whose full [main CI 42478537666](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42478537666)
passed. That CI is not an actual large-image export/verification run. Tests execute
the exact embedded coordinator with mocked children, including default/opt-in paths,
boolean injection, malformed and contradictory receipts, cross-commit substitution,
child failures, collisions and summary privacy. A later separately authorized
manual run is still needed for real large-image export and independent verification.

## Optional isolated API startup — 2026-11-09

Baseline PR200 is merged as main `be30990a8c7edbedb8fa5c7f6789b20d32b37937`.
Its [main CI 42497949946](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42497949946)
passed: 3,308 backend tests plus 1,336 subtests, 296 PostgreSQL cases without
skips, 2,116 frontend tests and the strict 8 Next + 16 component browser cases.
That validates PR200's script and tests, not a real API-process rehearsal.
Cloudflare build `a5901285-5304-450e-91b1-cf4bc41eebc1` / version
`7b446524-f8e9-4229-a9f1-df902d4446ae` succeeded; Render
`dep-dbo9qpgae00c739fems0` ended `update_failed`, not backend recovery.

This follow-up connects the existing API script to the same manual workflow with
`run_api_startup`, a boolean **default false**, independent of `export_bundle`.
There is still no push, pull-request or scheduled trigger. Developing, testing or
merging this option does not dispatch it or authorize a future runtime. Actual
use needs separate approval for this exact run's image preparation and API
container startup/isolation/owned-container cleanup. Earlier runner images were
not retained and are not reused.

The normal image preparer is unchanged. It still builds both images, saves and
validates their unchanged archives, runs dependency-only native smoke and parses
both Compose views. With export enabled, its temporary handoff and independent
verifier must also succeed before the optional API stage. With startup disabled,
no API module runtime function is called and no application is started. With
both options enabled, the order is preparation, independent bundle verification,
API process, final summary. Any requested stage's failure stops later stages;
there is no fallback or automatic retry.

### Source and receipt boundary

Both booleans reach Python only as environment data and must be exactly `true`
or `false`. No caller-supplied image/tag, commit, target URL, Docker arguments or
runtime environment is added. The coordinator uses the already validated
`images.api.image_id` from this successful build process and the checked
`GITHUB_SHA`. Git HEAD, the preparation receipt and both image source commits
must agree. Native-smoke evidence must have exactly the `api` and `web` keys and
nonempty string values regardless of either option. These values are never
published. A successful child exit and the fixed preparation status remain
necessary; strings alone cannot establish that a build or smoke happened.

The caller does not read an image label, archive directory or prior run summary
to invent its own expected identity. The API script independently rechecks the
clean checkout, exact available image ID and restricted image/container
configuration. This is consistency within the reviewed build on a trusted local
runner and Docker daemon, not a signature or authenticated publisher provenance.
A compromised runner or altered trusted coordinator remains outside that claim.

The workflow imports the existing API script only after all preceding gates and
calls `run_rehearsal(image_id, source_commit)` once. Only an exact two-element
tuple containing an integer zero exit code and the complete typed success record
can pass: fixed `API_PROCESS_SMOKE_PASSED_DATABASE_NOT_READY` status,
`FINAL_PROCESS`, 10/10 cases, `container_removed=true`, `database_ready=false`,
matching image/commit and fixed provenance/limitations. Missing/extra fields,
partial progress, a web-image substitution, cross-commit identity, unknown status,
boolean/numeric aliases, exceptions and interrupts fail closed.

Compose's `application_started=false` still describes its parse-only stage; it is
not overwritten to represent the separately requested API runtime. The final
summary is built only when every requested stage succeeds. An enabled success
explicitly reports the temporary API startup, 10/10 checks, confirmed removal and
unavailable database; a disabled summary explicitly says startup was not
requested. Raw receipts, native output, error text, local paths or supplied
limitations are not copied into public output.

### Shared time budget and cleanup

The first prerequisite step records `time.monotonic_ns()` before Docker checks
in `GITHUB_ENV`. The coordinator accepts only a bounded positive decimal value
that is not in the future or already 55 minutes old. Linux processes on this
runner share that monotonic clock. This environment value is local timing
bookkeeping, **not tamper-proof evidence or authentication**. It includes time
spent on prerequisites, checkout and contract tests before orchestration.

Every stage uses one 3,300-second soft deadline, not independent additive
3,300 + 600 + API timeouts. Before preparation, the coordinator reserves 600
seconds when bundle verification is requested, 240 seconds when API startup is
requested, and 30 seconds for the final summary. Child timeouts are the smaller
of their existing cap and the time remaining after those reservations. The
verifier likewise retains the API and summary reservations. If time is exhausted,
the job fails rather than changing the option or skipping a requested gate.

Before invoking the API function, at least the complete 240-second runtime/cleanup
window plus 30 seconds must remain. The API script retains its own 180-second
work deadline and separate 35-second cleanup window. The workflow does not put
that function in a `subprocess.run(timeout=...)` child that could be hard-killed
before its finally block. During the call SIGTERM becomes KeyboardInterrupt,
allowing the script's existing cleanup path; the previous handler is restored in
a finally block, including exceptions and rejected receipts. The final budget
is checked again after the handler has been restored and before summary output.

The 60-minute job hard limit, standard runner, 20 GiB prerequisite, read-only
repository permission and serialization remain unchanged. The soft deadline
leaves headroom; it cannot guarantee completion or cleanup under runner loss,
forced cancellation, repeated signals or a failed daemon. Only the API script
may remove its own verified full CID. Uncertain cleanup blocks success and keeps
its existing private custody record; the workflow never retries removal, looks
up containers by name, prunes, or deletes an uncertain exported directory.
No installer, capacity increase, host setting change, cache, registry push or
artifact upload is added.

### Development evidence and remaining acceptance

Regression tests execute the actual embedded coordinator with mocked preparation,
verification and API calls. Coverage includes all four option combinations,
receipt/source/type rejections, native-smoke evidence independent of export,
invalid timing markers, remaining-budget exhaustion, signal-handler restoration,
API exceptions, uncertain cleanup and summary privacy. The first 12 new tests
failed against the old coordinator before implementation. Independent review
then identified the export-disabled native-smoke gap; its regression was recorded
before the bounded correction. Exact validation totals are recorded in the
current repository checkpoints after the final rerun.

This package has not dispatched the manual workflow, acquired image layers,
started Docker/API/PostgreSQL, or exercised a real HTTP server. Existing
[API runtime constraints](offline-api-startup-rehearsal.md) remain in force.
Database readiness, real identity, frontend/browser startup, migrations, backup
restoration, physical disconnection and company deployment remain unaccepted.
Business and plan percentages are unchanged.
