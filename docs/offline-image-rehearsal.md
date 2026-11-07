# Manual connected image preparation and dependency rehearsal

Baseline main: `9cd5517611390b7e427b7de64e3c743a41c75d10`, 2026-11-07.
This package implements the smallest image stage from the
[image design](offline-readonly-image-rehearsal-design.md), using the existing
[30-wheel lock](offline-python-wheelhouse.md) and
[399-tarball npm collection](offline-npm-artifact-install.md). It adds dedicated
recipes, a bounded orchestration script, regression contracts and one **manual**
standard-runner workflow. The production Dockerfiles, locks, deployment workflows,
preflight, CI/branch protection and business scope are unchanged.

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
rechecks prerequisites before any preparation and forces the default local Docker
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
revision go directly to the unchanged `archive_image` validator. All original
manifest, config, environment, Volume, layer-digest and path checks remain.
An OCI/containerd-style save that violates the original traditional docker-save
contract **fails closed**. The script does not convert archives, replace manifest
fields, modify Docker settings or weaken the preflight. The runner's actual export
format remains a runtime risk until an approved run reaches this gate.

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
shape. `docker compose config --format json --no-env-resolution` must retain every
original service setting, image ID, localhost-only runtime command, disabled gate,
read-only policy and bounded logging option. No extra mounts/builds are allowed.
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
The unchanged preflight permits only Config/RepoTags/Layers in that record.
A synthetic docker-save tar with the additional field is still rejected. This
source-level incompatibility is not proof that either actual run reached that
specific rejection, and the extra field is **not** newly accepted or removed.

The follow-up changes only the orchestration script, its tests and this document.
It emits `BLOCKED` with one fixed, allowlisted export code and service role
(`api`, `web` or `unknown`), then exits nonzero:

- `IMAGE_INSPECT_FAILED` / `SAVE_COMMAND_FAILED`: the command wrapper reported a
  nonzero command result. No archive validation is claimed at either point.
- `IMAGE_INSPECT_TIMEOUT` / `SAVE_COMMAND_TIMEOUT`: the subprocess timed out;
  whether a daemon-side operation finished may be uncertain. Do not blindly retry.
- `IMAGE_INSPECT_ERROR` / `SAVE_COMMAND_ERROR`: another invocation, ID parsing or
  local logging error. These do not prove that the underlying command did not run.
- `ARCHIVE_READ_FAILED`: archive open/read/hash/stat or a later preflight read failed.
- `ARCHIVE_TAR_INVALID` / `ARCHIVE_JSON_INVALID`: the corresponding parser rejected
  its input. No raw parser message or input value is emitted.
- `ARCHIVE_FIELDS_REJECTED`: an exact original field-set check rejected the input;
  it does not print field names or prove which extra/missing field caused it.
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
or archive conversion is introduced. `archive_image()` remains byte-for-byte
unchanged and is still the sole acceptance gate, called once against the original
save bytes. Diagnostics expose why a check stopped, not permission to weaken it.

The 13 failure-first diagnostic regressions cover distinct inspect/save/hash and
preflight failures, timeout behavior, real synthetic tar/JSON and LayerSources
rejection, known-reason mapping, unknown-code/role fallback and private-data sentinels,
including retaining api/web without exposing a raw stage or role. Together with
the existing tests, 46 focused and 224 full offline tests pass.
These are local static/synthetic checks, not a new manual run, image build/export,
Docker acceptance, application/DB startup or company deployment. A newly reviewed
manual run is still needed to observe the actual fixed code; none is automatically
triggered by this change. Business and acceptance percentages remain unchanged.
