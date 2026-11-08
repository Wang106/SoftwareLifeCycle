# API process startup rehearsal, without a database

## Current evidence and scope

PR199 merged as main `5229d535f682839b1aaf7b36853b90fccda0bdd1`.
The separately approved [synthetic PostgreSQL run 42494711087](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42494711087)
completed all 21 collector cases with 21 expected `CHECKLIST_MISMATCH` results and
`container_removed=true`. PUBLIC defaults remained unchanged. That establishes
collector/negative-case execution on disposable synthetic PG16, not a matching
read-only database, application startup, restoration, physical disconnection or
company deployment. The earlier [PG rehearsal document](offline-database-rehearsal.md)
records that package's development-time boundary; its “not run” statements do not
override this later, separately authorized run evidence.

PR200 added only the opt-in coordinator, mock regressions and documentation.
No Docker command, container, HTTP server, database, migration or seed was run
while developing it. That package did not change a workflow, Dockerfile, production
source, database collector, dependency, CI gate or branch protection. The later
manual-workflow integration is described below; it still has no real API runtime evidence.

The current image smoke imports dependencies and compiles Python files, without
importing `app.main`. The new, future smoke starts the real uvicorn application
and observes its actual HTTP responses. Its success requires database readiness
to remain false. It is not a deployable-stack or offline-acceptance claim.

## Exact caller inputs and trust

The script imports only standard-library code and existing side-effect-free
bounded-command/strict-JSON helpers. Import, no arguments and `--help` do not
invoke Docker. Future execution, **only after separate approval**, has this fixed
interface:

```text
python scripts/offline_api_startup_rehearsal.py --run --image-id sha256:<64 lowercase hex> --source-commit <40 lowercase hex>
```

The trusted caller/operator must independently identify the reviewed API image
from the approved local build's records and supply its complete immutable ID and
source commit. Do not obtain both “expected” values from the image being checked,
infer approval from a label, or use an arbitrary downloaded image. A malicious
image can lie about its source. The script checks consistency, not authorship,
publisher signature, artifact provenance or image-content safety.

The source commit must equal the clean checkout, and image inspection must agree
with that independently supplied ID, revision, linux/amd64, nonroot user, Python
version, fixed default entrypoint and restricted image configuration. Only the
already available local image is accepted. The script never pulls, builds, loads,
extracts or uploads an image, and accepts no registry tag, URL, credential,
external container ID, Docker argument or environment-file input. Earlier
ephemeral runner images are not assumed available. A new commit requires a
matching approved build; it cannot borrow an older image's success.

The host must already have Python 3.12 and local Linux/amd64 Docker. Daemon overrides
are rejected; commands use the fixed local Unix socket and a private empty Docker
configuration. The subprocess environment is scrubbed. Git reads disable
fsmonitor/hooks and optional locks. There is no installer or permission change.

## Fixed future runtime

- One new container, `--network=none`, no published ports, bind mounts or volumes;
  no host-network mode, Docker bridge creation or host firewall changes.
- UID/GID 65532, read-only root, all capabilities dropped, no-new-privileges,
  seccomp filtering mode verified in the process (the Docker daemon/profile remains
  trusted), 512 MiB memory/swap limit, 1 CPU, 64 PIDs,
  8 MiB shared memory and 16 MiB noexec/nosuid/nodev temporary `/tmp`.
- No automatic restart or healthcheck; logging driver `none`.
- Explicit `/usr/local/bin/python -B -m uvicorn app.main:app`, app directory
  `/app`, listener 127.0.0.1:8000. No production entrypoint, Alembic or seed.
- `READ_ONLY_MODE=true`; authentication, administrator and telemetry disabled;
  both seed flags false. The fixed no-password database URL names an intentionally
  unavailable synthetic role/database at 127.0.0.1:5432 **inside this container**.
  Connection timeout 2 seconds and default read-only transactions are requested.
- Kernel PID1 command line, UID/GID, capabilities, no-new-privileges/seccomp and
  namespace TCP/TCP6 listeners are inspected by a separate Python exec. Only the
  expected 127.0.0.1:8000 listener is accepted, including at the final check.
  Host PID and running state are observed before every exec.

Ten fixed HTTP cases run in independent Python exec processes: `/health` and
`/health/live` return 200 / API 0.18.50; `/health/ready` returns 503 with exactly
`database_unavailable`; POST/PUT/PATCH/DELETE to the fixed snapshot-command path
return 403/read_only_mode; identity GET, session creation and session revocation
return 401/oidc_not_enabled with the fixed private/no-store headers. These last
checks prove the disabled branch rejects access, **not real authentication or
an OIDC provider flow**. Four method checks are not every business command's
end-to-end acceptance.

The probe uses direct `http.client` to the fixed loopback target, no proxy or
redirect following. It checks exact status, bounded JSON bytes, duplicate keys,
types, content type/length and required private headers. Wrong status/body,
unexpected encoding/redirect, missing headers or timeout blocks the run. Only a
small fixed success receipt is returned, not raw bodies, headers or errors.

## Failure and cleanup

The run has a 180-second deadline, bounded child output, discarded stderr and a
separate 35-second cleanup window. Process readiness is bounded observation;
create/start, HTTP cases and removal are not automatically retried. Shutdown,
kernel/daemon failure or forced termination can still prevent cleanup.

Before start/exec/removal, the full CID, random ownership label/name, immutable
image, source label and security configuration must match this run. Only the
newly recorded full CID may be removed. Missing/malformed/symlink CID files,
ownership mismatch or an uncertain removal preserve the private custody record
for manual review and return `BLOCKED`, never success. No deletion by name,
container search, prune or broad resource cleanup occurs. The generated private
`slc-api-startup-*` directory contains only this run's custody/CID and empty Docker
configuration; it is removed after confirmed cleanup, otherwise retained locally.
Reports do not print that path or arbitrary command output. A trusted operator can
locate the private directory in the invoking host's temporary directory if review
is necessary. Do not retry an uncertain operation blindly.

Only all 10 cases plus initial/final process checks and confirmed cleanup yield
`API_PROCESS_SMOKE_PASSED_DATABASE_NOT_READY` and `database_ready=false`.
An image label alone, 200 liveness, mock test or partial result is insufficient.

## Authorization and remaining work

Development/mock testing does not authorize execution. A future run needs approval
covering this exact reviewed image, container startup/isolation and removal of
that container. Obtaining a missing image is a separate scope. No real credential,
role/grant change, company system, paid resource, file upload or host network
change is included. Container `network=none` is not physical host disconnection.

The API image deliberately contains `app/` but not `alembic.ini` or the migration
directory. A later database package must provide separately reviewed, trusted
migration source or a one-time migration-tool image and actually execute the full
schema 0029 chain in a newly approved disposable database. Filling in
`alembic_version` manually cannot substitute for migrations. Database/role/grant
setup, real SELECT behavior, backup/restore, frontend/browser acceptance and
company deployment remain separate. No collector rule is relaxed to obtain
`CHECKLIST_MATCHED`.

Local validation commands (no Docker, API or database):

```sh
python -m unittest discover -s backend/tests -p test_offline_api_startup_rehearsal.py -v
python -m unittest discover -s backend/tests -p 'test_offline*.py' -v
python -m unittest discover -s scripts/automation/tests -v
python -m unittest discover -s scripts/ci/tests -v
python scripts/report_development_plan_progress.py --check
git diff --check
```

Development validation: 28 focused and 459 all-offline tests (zero skips),
2,116 frontend tests, TypeScript/Worker configuration checks, 52 automation
contracts, 126 browser guards and Python compilation passed. Initial independent
review found no blockers and ran 994 synthetic adversarial checks; final review
is pending. Docker/HTTP/proc behavior in these tests is mocked. Full backend,
real PostgreSQL and browser acceptance require the exact candidate CI.

Business 36/44=82%, delta 0; modules 100/100demo/100demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser-stage 1/4 and finite-plan 8/8 unchanged.


## Manual-workflow integration — 2026-11-09

PR200 is now merged at main `be30990a8c7edbedb8fa5c7f6789b20d32b37937`.
[Main CI 42497949946](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42497949946)
passed 3,308 backend tests plus 1,336 subtests, 296 PostgreSQL cases without skips,
2,116 frontend tests and strict 8 + 16 browser cases. These checks do not start
this API rehearsal. Cloudflare's same-commit build/version succeeded; Render
`dep-dbo9qpgae00c739fems0` failed. No backend recovery is claimed.

The existing manual image workflow now offers `run_api_startup`, default false.
This is integration code and mock testing only. The API script, isolation flags,
10 HTTP cases, failure cleanup and production code are unchanged. A separately
approved run first performs the existing full image preparation, then any
requested independent bundle verification, then invokes this script's
`run_rehearsal` function exactly once. Export and API startup are independent
options. No existing or historical image is presumed available.

The workflow supplies the exact API image ID from that same successful trusted
build receipt and the matching `GITHUB_SHA`; it does not infer expected identity
from a label. Both image receipts and clean checkout must match that commit.
Native smoke requires exactly API/web nonempty-string records regardless of the
export option. The complete API result must then match the fixed 10/10 success
contract, including `container_removed=true`, `database_ready=false` and the same
image/commit. The fixed provenance value still means build consistency only,
not authenticated authorship or independent security clearance.

The new wrapper uses a shared 55-minute soft deadline inside the unchanged
60-minute job limit. A runner-local monotonic timestamp covers prerequisites,
checkout and tests too. The environment timestamp is bookkeeping, not a
security boundary. A full 240-second API/cleanup window plus 30 seconds for the
summary must remain before startup. No hard-kill subprocess timeout is added
around this script. SIGTERM is temporarily converted to KeyboardInterrupt;
the prior handler is restored in finally before receipt/budget validation.
The script retains its own 180-second work and 35-second cleanup deadlines.
Forced runner termination can still leave cleanup uncertain; no workflow
fallback removes containers or retries an uncertain operation.

See the [workflow option and budget contract](offline-image-rehearsal.md#optional-isolated-api-startup--2026-11-09)
for the four-option matrix, strict receipts, failure reporting and tests.
The summary distinguishes API process success from its intentionally unavailable
database and from the earlier parse-only Compose stage. Development/CI is not
runtime approval. No manual workflow, actual API server, database, migration,
identity flow, backup/restore, physical isolation or company deployment was run
by this integration package; all acceptance percentages remain unchanged.
