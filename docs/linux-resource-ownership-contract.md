# Resource ownership and proc PID-view backend contract

This design and executable synthetic reference model are NOT a Linux backend.
Only tests import `scripts/ci/tests/fixtures/linux_ownership_model.py`.
`test_linux_ownership_contract.py` runs through ordinary CI contract tests.
Nothing connects the model to SampleOnce, OwnedDirectory, a launcher or runner
qualification. MODEL_PROTOCOL_COMPLETE always retains live_binding_verified,
input_authenticity_verified, atomic_snapshot and runner_qualified as false.

## Missing boundary

The existing sampler's shared token and directory adapter's injected metadata
cannot establish real proc-directory/pidfd association. A future trusted resource
broker must own the original pidfd, anchored directory and proc-view resources
exclusively throughout an attempt. It must not accept a caller's PID/token pair
as proof. Acquisition must establish ownership, for example through a separately
reviewed atomic pidfd launch or child acquisition preserving the documented
SIGCHLD/no-reaping conditions of pidfd_open. Neither is implemented here.
Python3.12 pidfd_open alone does not establish these additional invariants.

The broker must independently establish an authentic procfs instance and its PID
view and use that same retained view for fdinfo and stat. Target ns/pid is not the
reader's procfs view. Caller strings, inode numbers or shared tokens do not prove
it. FD close/dup2/replacement, transfer and reaping policies must be controlled;
a Python lock alone cannot establish control over other threads/native code.
The acquisition mechanism and supported kernel APIs require review before live
implementation. This is the concrete dependency, not a missing approval flag.

## Conditional protocol and source argument

Under a trustworthy kernel, authentic common proc-view and exclusive original
handle lifetimes, perform these fresh operations sequentially:

1. Generate bounded pidfd fdinfo. Its positive Pid must equal the expected PID
   in this proc-view. If NSpid is used, its first value must match, never an inner
   alias. Expected4123 versus Pid560/NSpid560,4123 rejects; 0/-1 also reject.
2. Only then open stat relative to the original proc directory and generate/read
   a fresh complete bounded record. Require expected PID and start ticks.
3. Generate fresh fdinfo for the same original pidfd and proc-view again and
   require the same positive PID. Cached or prefetched seq_file bytes do not count.
4. Check that original pidfd for exit. Exit, unknown, permission and I/O error
   reject. A positive fdinfo PID may represent a zombie, not proof of liveness.

proc_single_show obtains a task through its inode's retained struct pid and fails
if absent. This argument requires stat generation AFTER the first fdinfo check,
not old buffered data. The second fdinfo check rejects detached identity. Start
ticks are additional consistency evidence, not a globally unique ownership key.
No numeric-PID reacquisition or replacement of missing evidence is permitted.

Holding fdinfo open does NOT bind it to the original pidfd: fd.c seq_show resolves
the numeric FD slot when generating data. Exclusive original slot lifetime is
therefore a separate mandatory invariant. Sequential observations are not atomic;
exit or namespace changes may occur after/between checks. Cooperative deadlines
cannot interrupt arbitrary blocked kernel I/O. Existing bounded complete-record
and separate readlink rules remain in [the directory contract](linux-owned-descriptor.md).

## Executable model and backend acceptance

The fixed synthetic process is PID4123/start124 in proc-view. The model issues
its own one-time lease and ordered record receipts; arbitrary values or another
model's lease are refused. This is not protection against Python introspection
or hostile in-process code. Fixture facts/events are invented. Receipt freshness
means model call order only, not actual bytes freshly produced by a kernel.
Fault injection models detection of FD replacement/generation/view changes; it
does not implement that detection. There is no raw fdinfo parser or OS seam.

| Obligation | Synthetic regression | Live backend acceptance still required |
| --- | --- | --- |
| Exclusive ownership | foreign lease/double acquisition refuse | acquisition, concurrency, FD and reaping lifetime review |
| Original resources | replacement/generation/view fault at boundaries invalidates | actual original handle retention without numeric PID reopen |
| Same PID view | wrong view/PID/first NSpid and inner alias refuse | authenticated procfs view and fdinfo association |
| Fresh reads | replay/prefetch/foreign receipt/order/early finish refuse | new kernel-generated complete bounded bytes, no cache |
| Exit/errors | exit/unknown/permission/I/O faults refuse | actual supported pidfd polling and error mapping |
| Cleanup | only four model resources, one attempt, no uncertain-close retry | actual owned cleanup and interruption handling |
| Honest result | all verification flags remain false | no qualification or publisher claim from this model |

The caller must close after exceptions/interruption; there is no automatic cleanup
guarantee. Synthetic close only records attempts for fdinfo,pidfd,directory,view;
it performs no OS close. Failed or closed attempts cannot resume or reacquire.
A future backend must implement and demonstrate these criteria before wiring the
existing sampler. A model pass is not that backend or GitHub runner evidence.

## Primary references and limits

- [Kernel proc documentation](https://docs.kernel.org/filesystems/proc.html#process-specific-subdirectories): anchored proc FDs never redirect to a reused PID but do not prevent reuse.
- [Linux v6.8 proc/base.c](https://raw.githubusercontent.com/torvalds/linux/v6.8/fs/proc/base.c): proc_single_show and retained struct pid.
- [Linux v6.8 kernel/fork.c](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/fork.c): proc-view Pid/NSpid, detached task and separate pidfd polling.
- [Linux v6.8 proc/fd.c](https://raw.githubusercontent.com/torvalds/linux/v6.8/fs/proc/fd.c): numeric FD slot resolution during content generation.
- [Python3.12 pidfd_open](https://docs.python.org/3.12/library/os.html#os.pidfd_open) and [Linux manual](https://man7.org/linux/man-pages/man2/pidfd_open.2.html): API and conditional child acquisition guarantees.

These support a conditional design, not installed-kernel certification. No live
proc/process/browser, install/download, credentials, security/workflow changes,
rehearsal or deployment. Existing macOS4+16+16 gates stay unchanged. Historical
e2038a94 runtime images remain outside Next16.4.5 source-patch coverage; prior CI
timing causes remain unproven. Business acceptance36/44 (82%), increment0.
