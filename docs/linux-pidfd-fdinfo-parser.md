# Pure pidfd fdinfo byte parser

`scripts/ci/linux_pidfd_fdinfo.py` adds `parse_fdinfo(raw)` and
`match_expected_proc_pid(raw, expected_pid)`. Both operate only on supplied bytes.
No proc/pidfd access, resource acquisition, process launch, collection CLI or
integration into SampleOnce/OwnedDirectory/the ownership model is added. This
closes the raw-record parsing gap in the [ownership contract](linux-resource-ownership-contract.md),
not the missing trusted backend or actual process association.

## Explicit supported profile

The conservative profile is the generic four headers plus pidfd Pid/NSpid emitted
by the inspected Linux6.8 and6.12 x64 sources with CONFIG_PID_NS. Input must be an
exact bytes object,1..4096 bytes, ASCII, six LF-terminated lines. Each field occurs
once with colon+tab separation; field order is immaterial. Unknown/missing/repeated
fields, CRLF, blank lines, noncanonical numbers and a missing final LF reject.
Absent NSpid on CONFIG_PID_NS-disabled kernels, extra fields and future formats
are unsupported, not silently accepted. This is not a universal fdinfo parser.

| Field | Accepted representation and bound |
| --- | --- |
| pos | canonical unsigned decimal,0..2^63-1 |
| flags | literal0 plus canonical octal,0..2^32-1; zero emits00 |
| mnt_id | canonical unsigned decimal,0..2^31-1 |
| ino | canonical unsigned decimal,0..2^64-1 |
| Pid | -1,0,or canonical positive decimal up to2^31-1 |
| NSpid | 1..33 tab-separated IDs; first must equal Pid |

These are conservative wire bounds, not configured pid_max or permission checks.
Negative generic metadata is unsupported. Levels0..32 permit33 namespace IDs.
Visible entries must all be positive signed pid_t values. For Pid0/-1, NSpid must
contain only that same sentinel. Metadata cannot prove identity or permissions.

Parsing returns metadata, PID chain and supplied-byte classification: `visible`
(positive), `not_visible`(0), or `detached`(-1). It does not prove a real pidfd or
process. Positive Pid may describe a zombie, so visible does not mean alive.
Errors use a fixed message without echoing input. A syntactically complete record
may still be forged, stale or cut at a valid boundary; parsing cannot establish
kernel EOF, freshness, or the installed kernel's version/authenticity.

## Same-view numeric comparison only

expected_pid must be an exact positive int below2^31, expressed in the same
independently established procfs PID view. The helper reparses raw bytes, rejects
0/-1 and compares Pid (already equal to first NSpid). Expected4123 against
Pid560/NSpid560,4123 rejects; inner namespace aliases never establish binding.
No caller token or boolean can prove the common view. Even success keeps
common_view_verified, input_authenticity_verified, live_binding_verified,
atomic_snapshot and runner_qualified false. numeric_match=true means only the
supplied numbers match conditionally and cannot authorize execution/collection.

Exclusive FD lifetime, authentic proc-view, fresh complete records, original
pidfd exit checks, generation continuity, owned cleanup and I/O deadlines still
require the future trusted broker. An open fdinfo descriptor alone does not bind
the original pidfd slot. No numeric PID reacquisition or live adapter is added.
Existing sampler/descriptor/ownership contracts remain unchanged.

## Primary sources and validation

- [Linux6.8 generic headers](https://raw.githubusercontent.com/torvalds/linux/v6.8/fs/proc/fd.c) and [Linux6.12 headers](https://raw.githubusercontent.com/torvalds/linux/v6.12/fs/proc/fd.c): decimal metadata, octal flags and numeric FD-slot resolution.
- [Linux6.8 pidfd fields](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/fork.c) and [Linux6.12 fields](https://raw.githubusercontent.com/torvalds/linux/v6.12/fs/pidfs.c): Pid/first NSpid use the procfs instance's PID namespace;0/-1 cannot establish binding.
- [Namespace depth](https://raw.githubusercontent.com/torvalds/linux/v6.8/include/linux/pid_namespace.h) and [creation limit](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/pid_namespace.c): maximum level32, including level0.

13 synthetic methods cover source-shaped records, syntax, missing/duplicate/
contradictory fields, sentinel states, numeric boundaries,33/34 namespace entries,
inner aliases, strict expected IDs and fixed errors. Regression failed before
implementation; all194 contract tests pass from CI's backend directory.
Independent review and exact-head ordinary CI evidence are recorded in the PR.
No actual Linux proc/pidfd/browser exercise, live identity, TLS/OIDC, production
storage, company acceptance or sandbox qualification is claimed. Existing signed
macOS4+16+16 gates stay intact. Historical e2038a94 images remain outside
Next16.4.5 source-patch coverage; prior CI timing causes remain unproven.
Business acceptance36/44 (82%), increment0.
