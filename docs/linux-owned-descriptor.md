# Injected owned-descriptor adapter

`OwnedDirectory` in `scripts/ci/linux_owned_descriptor.py` implements the directory
side of [SampleOnce](linux-process-sampling.md) through injected `DescriptorOps`.
There is no OS implementation, default backend, path-based acquisition, pidfd
creation, process launch or live proc access. All evidence is synthetic.

The constructor accepts an already-owned unique `object()` directory token,
expected device/inode tuple and shared sampling binding token. Ownership transfers
only after successful construction. Raw numeric FDs, strings and other value
handles are refused. Operations must map each token to exactly one resource and
never reuse or alias tokens; returned record tokens must be new and cannot equal
the directory token. This is an interface requirement, not a verified OS property.
The caller must use the context manager or close explicitly. Record tokens are
closed once in finally; the directory token is closed once on context exit.
An uncertain close is never retried. Cleanup failure explicitly rejects even a
previously complete read and takes precedence over another error or interruption.
No broad cleanup, signalling or recovery-open operation exists.

Only stat=4096, status=16384 and ns/pid, ns/net, ns/user=128 are accepted, with
exact limits. Reads stay relative to the original directory token. Injected
device/inode observations are checked before/after each chunk or link operation.
These checks detect supplied metadata changes; they do not bind an actual kernel
process generation. SampleOnce separately compares supplied PID/start ticks to
its independently supplied expected generation and checks its separate exit probe.
The adapter does not implement real proc-directory acquisition or pidfd binding.

Ordinary records accumulate positive short reads until actual empty-byte EOF.
Each request has positive size. At the exact limit, a one-byte request must return
EOF; a valid-looking limit prefix followed by one extra byte is rejected. An
oversized chunk, invalid/empty record, interrupted or failed read returns no
partial bytes to the parser. Each stream uses at most limit+1 read calls and
retains at most limit+1 bytes before rejecting. Namespace links use a distinct
single readlink capacity of limit+1, rejecting capacity-sized/overlong results;
there is no fictitious link EOF probe. A future backend must honor these bounds
without silently truncating or fabricating completeness.

An alive same-UID fixture with readable status can still lack permission to read
namespace links. The first such denial records `permission_denied`, returns no
sample, and causes no later namespace read. Exit-probe refusal remains a separate
sampler event, not a permission diagnosis. Failed adapters become unavailable.
Diagnostic reasons contain no raw paths/content, and displayed exception chains
suppress underlying operation errors. In-memory exception internals are not a
safe logging interface; do not serialize them or arbitrary adapter state.

No elapsed-time deadline is implemented. Bounded call/data counts do not bound
kernel blocking time; a future cooperative deadline would not itself interrupt a
blocked syscall. Actual deadlines, OS read-only/no-follow semantics, descriptor
ownership, genuine process-generation association, non-atomic sampling races,
namespace authenticity and network enforcement need separately reviewed live work.
Result qualification/authenticity remains false through the existing sampler.
This package does not prove a runner, publisher signature or Linux Chrome sandbox.
Existing signed macOS4+16+16 gates/workflows remain unchanged.

Baseline PR256 merged at6af467515686b21e6c063a4fa87a18fea76452df; main
CI44843874184 passed, Workers production build passed, Actions deployment44845786460
and continuation44845786500 skipped. Separate confirmed read-only Render lookup
found no matching PR256 deployment; newest service record remained PR253 e285e92c
update_failed. No provider action was taken. Historical e2038a94 runtime images
remain outside Next16.4.5 source patch coverage. Acceptance stays36/44 (82%).
