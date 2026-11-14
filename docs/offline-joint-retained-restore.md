# Fixed synthetic joint retained recovery

This package coordinates the existing PostgreSQL and software rehearsal CLIs. It
adds same-invocation pairing and a real two-component restore, not another dump
engine or a checker-only acceptance claim. Only operator-owned canonical synthetic
inputs are supported. It is not company recovery, deployment, image restoration,
RPO/RTO validation, physical disconnection or completion of `ops-restore`.

## Boundary and commands

The new standard-library entrypoint is `scripts/offline_joint_retained_restore.py`.
No arguments and `--help` only display usage. Native operations require an explicit
`--trusted-own-synthetic` flag. An already configured `TEST_POSTGRES_URL` must refer
to disposable numeric-loopback PostgreSQL with the existing temporary-database
permissions; do not put credentials on a command line. The existing tools enforce
schema0030, canonical fixture, exact PostgreSQL compatibility and owned targets.

```sh
python scripts/offline_joint_retained_restore.py produce --trusted-own-synthetic
# Retain PAIR_ID and MANIFEST_SHA256 from this successful process's stdout.
# After that process has exited:
python scripts/offline_joint_retained_restore.py recover PAIR_ID MANIFEST_SHA256 --trusted-own-synthetic
```

`produce` creates a private `/tmp/joint-rehearsal-<32hex>` directory and invokes the
unchanged DB producer, then unchanged software producer. It checks their actual
successful process exits and exact receipts. The DB producer drops its original
owned databases. Only afterward does the coordinator seal `pair.json`, binding
both independently generated component run IDs, producing DB source/checkout
commits, exact DB archive/manifest/baseline/ownership-proof hashes, and software
bundle/result hashes. The software script is executed from the same checkout;
its legacy receipt has no independent source-commit assertion. There is no API
for combining arbitrary old successful records into a new pair.

`recover` accepts only a fixed pair ID and an independently retained expected
manifest digest, not arbitrary component paths. Binding validation precedes target
allocation. It invokes the unchanged software recoverer and then unchanged DB
recoverer. Both create new targets, never restore over an existing target. It
rechecks original hashes and actual restored software bytes before joint success.
Original DBs and the producer process are not needed. Retained software bundle and
result files must still exist at their original fixed `/tmp` location.

The digest is an integrity anchor, not authentication, an untrusted-SQL sandbox,
or proof against a malicious same-UID writer. Use a trusted executor and quiescent
owned files. This is same-host retained recovery, not a portable import/export or
storage/retention system. Linux private directories, non-symlink regular files,
exact modes/ownership, single links and bounded reads are required. Child processes
use a private umask without changing global permissions or existing tools.

## Failure and completion

Only the final stdout receipt **plus process exit zero** proves coordinator
completion. Persisted recovery `result.json` is deliberately `CANDIDATE`, matching
the existing software recoverer's completion boundary. A success-looking receipt
from a nonzero child or a persisted candidate cannot establish joint success.

Binding rejection occurs before targets are allocated; it does not mean every
component's native compatibility checks occur before either target is allocated.
If software succeeds and DB recovery fails, the overall operation fails and the
new software output remains. There is no atomic rollback, automatic retry,
overwrite, retention deletion or cleanup by name search. Private `failure.json`
records only fixed stage/status and validated owned identifiers, never raw child
stdout/stderr, exceptions or connection strings. Existing DB tools may retain their
own diagnostic files inside the private root; these are not safe public summaries.
Child stdout and stderr are each limited to 64KiB during reads; stderr is discarded.
Each child has a 300-second budget and the invocation a shared 600-second budget,
with five seconds reserved for bounded termination of only the owned child. This
is a cooperative budget, not a hard wall-clock limit: filesystem calls can block.
Final persistence is followed by another deadline check before returning success.
Shutdown preserves the original exception and closes both pipes independently,
once each; a cleanup failure after an otherwise successful child still fails. No
process-name search or database cleanup follows a timeout. An interrupted or
timed-out process can leave descendants/resources with uncertain completion.
Preserve evidence and inspect the exact new ownership proof before explicit cleanup.

After a successful recovery and inspection, existing DB cleanup applies only to
its new run ID and new database evidence directory:

```sh
cd backend
python -m app.ops.postgresql_backup_restore \
  --evidence-dir /tmp/JOINT_RECOVERY_ID/database --cleanup-run-id NEW_DB_RUN_ID
```

No new cleanup authority is introduced. Do not use the original backup proof to
clean a new target. Software outputs remain for explicit inspection.

## Validation

New standard-library tests exercise argument/trust gates, strict receipts,
corruption/mixed binding, partial failures, file safety and redacted summaries.
No DB/API/container execution is performed locally. The new PostgreSQL-module
integration test runs in the existing full backend CI suite: producer exits,
original DBs are absent, a mixed software component is refused, then a separate
process restores real PostgreSQL and software contents. It verifies canonical
inventory/audit protections, immutable originals, old-proof refusal and explicit
new-target-only cleanup. Its safe summary is
`ci-results/joint-retained-restore.json` in the existing backend evidence artifact.
Native success must be established by fresh exact-head CI; local mocked tests or
historical runs are not evidence that this new joint path has run.

No CI/workflow/dependency/migration/permission/production-setting change is needed.
Business 36/44 (82%), module/plan percentages and company acceptance stay unchanged.

Local validation: the initial seven missing-capability cases failed before
implementation. Final 22 focused and 872 full offline tests pass, as do 52
automation and 126 CI guard tests. Three new Python files compile in memory;
progress and whitespace checks pass. Reproduced JSON, child-output, original-error
and final-deadline regressions were corrected after specific notices and pauses,
without removing assertions. Tiny local Python child processes test capture limits
and timeout behavior; they are not services or database execution. Independent
final review passed the 22 focused tests, six extra cleanup/interrupt probes and
a tiny-child SIGTERM-to-SIGKILL timeout check. Exact-candidate native CI remains
pending.
