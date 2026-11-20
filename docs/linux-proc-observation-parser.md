# Synthetic proc observation adapter

`scripts/ci/linux_proc_observations.py` provides pure byte parsers and
`adapt(stat_before, status, namespaces, stat_after)`. It opens no files, launches
no processes and makes no network requests. Only synthetic fixtures have been
exercised. This prepares the process fragment for the [observation consistency
contract](linux-chrome-sandbox-evidence.md), not an attestation or collector.

Inputs are bounded ASCII bytes: stat 4096 bytes, status 16384 bytes/256 lines,
and each of the exact pid/net/user namespace link texts 128 bytes. Stat accepts
only the 52-field layout, including a parenthesized comm with spaces or closing
parentheses; comm is discarded. PID/PPID and start ticks are bounded canonical
integers. Status requires unique keys and Pid/Tgid/PPid/Uid/Seccomp/NoNewPrivs;
other well-formed fields are ignored. Namespace type prefixes must match their
keys, with positive canonical inode numbers below 2**63, matching the checker. Malformed input raises ValueError
with fixed diagnostics, without echoing raw text.

The adapter requires matching before/after PID, PPID and start ticks, matching
status identity, a process leader, and four equal non-root UIDs. It preserves
Seccomp 0/1/2 and NoNewPrivs 0/1; parsing does not upgrade these observations.
The result contains a partial `process` object and `observed_ppid`, plus false
`runner_qualified`, `publisher_signature_verified`, and
`input_authenticity_verified` flags. It does not synthesize ancestry or fill
missing browser/report fields. A caller must select the browser fields or add
independently collected renderer ancestry before the full consistency checker.

Fabricated consistent bytes can pass. Matching start ticks alone does not bind
a boot, proc view, namespace snapshot, executable or actual owned process.
The [kernel proc documentation](https://docs.kernel.org/filesystems/proc.html#process-specific-subdirectories)
describes status/stat fields and the lifetime behavior of open proc descriptors.
A future reviewed collector must keep the same proc directory descriptor for
each confirmed owned process and read relative to it, not reopen a reused numeric
PID. Any pidfd exit detection must bind that same identity. Collection before/after
ordering, namespace authenticity, complete argv, ancestry, publisher provenance,
network enforcement and cleanup remain unimplemented and unverified.

No host proc access, Linux Chrome run, qualification, browser-to-real-service
acceptance, TLS/OIDC, production storage or company acceptance occurs here.
Existing macOS 4+16+16 gates and workflows are unchanged. Historical e2038a94
images are not covered by the Next16.4.5 source patch.
