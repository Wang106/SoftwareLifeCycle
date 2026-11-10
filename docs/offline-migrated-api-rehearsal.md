# Default-off migrated API execution entrypoint

## Scope and current evidence

PR213 is merged as main `024849675a93e663cbf22ea17074bc906896bb14`.
[Main CI42779028387](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42779028387)
passed with 3609 backend tests, 2832 subtests, 308 PostgreSQL-module cases without
skips, 2274 frontend tests and strict 16+16 browser journeys. Cloudflare production
build `2b587544-8b39-4baa-b935-ee9c0e1cd510`, version
`99e6e693-69a1-4c3d-8ed6-a6b2a6d7b6fd`, succeeded. Actions deployment and continuation
were skipped; Render was not checked. This is baseline evidence, not new candidate
CI or a real migrated API lifecycle run.

This package only adds a thin CLI, an independent manual workflow, mocked
contracts and documentation. Existing CLI, workflows, coordinator, preparation,
probe, Dockerfiles, dependencies, migrations, production code and CI gates are
unchanged. The older migration-only entrypoint and workflow remain available and
do not gain an API option. All current development calls to acquisition, Git source
subprocesses, Docker, API and database operations in entrypoint tests are mocked.
A real Python subprocess tests CLI/module/signal behavior but never starts a service.

The CLI requires both `--run` and an exact lowercase 40-character
`--expected-commit`. Import, help, missing flags and unknown arguments do not enter
source validation or runtime work. It accepts no database target, image receipt,
external CID, credentials, arbitrary command or retry option.

The new workflow is `.github/workflows/offline-migrated-api-rehearsal.yml`.
It has only `workflow_dispatch`, with the boolean input `run_migrated_api` defaulting
to false. The entire runtime job is skipped unless the input is true. No push,
pull-request, schedule or workflow-completion event starts it. Creating/merging
this workflow or passing normal CI does not dispatch it.

## Authorization and limits

Before any actual invocation, obtain specific approval for same-run dependency/
base acquisition, migration/API image builds, owned isolated containers, temporary
postgres superuser trust and namespace sharing, original DDL in a new empty tmpfs
PG, API startup/five read-only/refusal probes, and exact-owned-CID cleanup. Selecting
an input or supplying `--run` is not an authorization credential. No actual manual
workflow or lifecycle operation has been executed for this package.

Use only the already-reviewed synthetic lifecycle. There is no old/company
DB, role grant, real identity, production write, image export, artifact upload,
cache, prune, automatic retry, new paid resource or security-setting change.
The existing [lifecycle limitations](offline-api-lifecycle-integration.md) remain:
selected schema/count observations and five API checks do not establish complete
schema, SELECT-only roles, physical isolation, business acceptance or deployment.

## Canonical modules and source binding

The thin script imports `offline_migration_database_rehearsal` under its canonical
module name. It does not execute the coordinator as `__main__` or copy its classes.
This matters because the probe requires the exact live coordinator OwnedContainer
type; two module instances would break the custody check.

Before runtime, the entrypoint checks its own location and the canonical coordinator
location. It compares its own and the new workflow's bytes to the requested commit,
using fd-anchored repository reads, no-follow regular-file checks, bounded output,
and a sanitized local Git command. Global/system Git config, lazy fetch, replacement
objects, fsmonitor and hooks are disabled for these reads. The existing coordinator
and builders retain their separate helper/source/clean-checkout checks.

The new reads use the existing bounded-command primitive with per-call timeouts
limited by the original remaining budget, rather than changing or monkeypatching
the legacy fixed-timeout source reader. These checks are consistency under the
trusted checkout/local daemon assumptions, not authenticated provenance or hostile
same-user protection.

## Time, signals and workflow resources

An existing `MIGRATION_REHEARSAL_STARTED_NS` is required. The entrypoint never creates
or refreshes it and rejects a marker changed during its source validation. Each new
Git read is capped at 20 seconds and by remaining time after reserving 1330 seconds
plus the shared 30-second final margin. The budget deadline itself is checked for
mutation. Admission is checked again before the canonical coordinator is called.
That coordinator reconstructs the same original start, not a new 55-minute window.

This bounds the newly added source validation. It does not rewrite every legacy
helper's source-read/cleanup timing behavior or claim a hard aggregate deadline
inside all legacy operations. API preparation's existing 630-second reserve can
still finish too late for the later 1330-second admission floor. That path rejects
before PG creation; this package does not extend time or disguise the limitation.

SIGTERM is temporarily translated to KeyboardInterrupt before validation or
acquisition. The previous handler is restored in finally on success, ordinary
failure, interruption and SystemExit. Successful JSON is emitted only after handler
restoration. Install/restore errors cannot emit a successful receipt. SIGKILL,
repeated interruptions and host/daemon loss remain cleanup-uncertainty boundaries.

The manual job uses the existing standard `ubuntu-24.04` runner, 60-minute hard
limit, shared 55-minute marker set before checkout, contents-read-only token and
pinned checkout with credentials not persisted. Its concurrency group is the same
as the older migration/database workflow and does not cancel an active run. This
avoids simultaneous old/new workflow jobs in that group; it is not a global lock
against unrelated workflows or manual processes. All scoped mock contracts run
before the actual step, within the same budget. No cache/artifact step or expanded
permissions are added. Standard-runner use is not a guarantee that an account has
no other charges.

## Local verification

The initial 16-contract suite failed before implementation, then all 16 passed.
Contracts cover default/import/help/no-run behavior, malformed arguments/markers,
source and module mismatch, exact bounded Git settings, shrinking allowances of
3/2 seconds, exhausted/mutated budget, changed marker, linked source rejection,
canonical coordinator identity in a real Python process with mocked work, signal
restoration and default-off/manual-only workflow limits.

Independent review also checked actual-process handler restoration on failure and
interruptions, and mocked-Git hardlink/FIFO/oversize rejection. Full offline,
automation/CI guards, compilation, YAML/shell syntax and final review evidence are
recorded in the current checkpoint. Shell syntax checks do not execute workflow
commands. Exact-candidate CI and any real lifecycle operation remain separate.

Business 36/44 = 82%, increment 0; modules 100/100 demo/100 demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser stage 1/4 and finite plan 8/8 unchanged.

## PR214 CI fixture correction

The first candidate `ede55a5c` failed CI42783262210 only in the new expired-marker
subcase: 3625 backend passed, one subcase failed. `max(1, now - 3301 seconds)`
created a valid marker on a newly booted runner, so the runtime correctly accepted
it. An unchanged-test reproduction with 100-second paired clocks failed the same
case. The test-only repair uses paired 4000-second clocks and marker 699 seconds,
whose age is genuinely 3301 seconds, plus valid-marker controls on young/old hosts.
Runtime, workflow and all budget/gate behavior are unchanged. No old-candidate rerun.

Final local repair evidence: 17 focused tests pass via discovery/direct invocation,
763 offline, 52 automation, 126 CI guards and progress/diff checks pass. Independent
review reran 17+20+35 focused/related cases, reproduced the old failure in memory and
verified the repaired case under both ambient clocks. New exact-head CI remains
separate and no real lifecycle operation was executed.
