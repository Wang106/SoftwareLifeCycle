# Injected process identity sampling protocol

`scripts/ci/linux_process_sampling.py` adds `SampleOnce(directory, probe,
expected_pid, expected_start_ticks).sample()`. It uses the existing bounded
[proc parser](linux-proc-observation-parser.md); it implements no filesystem,
pidfd, process-launch or network adapter. All current tests use in-memory data.

The caller supplies an already-bound directory and an exit probe with the same
opaque `binding` object. That token prevents accidental adapter mixing or
replacement during this protocol; it does not prove a real kernel association.
Expected PID/start ticks must come from a separately established owned identity,
not merely from the first sample. A future adapter must retain the same proc
directory descriptor, perform relative reads, and associate its pidfd with that
same identity. It must never reopen a numeric PID to replace missing evidence.

The fixed order is stat, status, ns/pid, ns/net, ns/user, stat. Each read has
before/after exit and token checks. Only an exact boolean false means the probe
reports no exit; missing/unknown/error/true refuses the sample. Initial identity
must match the expected generation before other reads. Final parsing refuses
inconsistent identity, UID or malformed fields. The instance consumes its sole
attempt before any adapter call and cannot retry after success or failure.
No partial result is returned. Errors use a fixed diagnostic without chaining
adapter paths/content into the displayed traceback.

Read limits are 4096/16384/128 bytes as appropriate (24960 bytes maximum for six
returned records). Adapters must return complete records or raise; they must not
silently truncate. This synchronous protocol bounds calls and returned data,
not an adapter's internal memory allocation or elapsed time. A future live
adapter needs separately reviewed I/O deadlines, descriptor lifetime and owned
cleanup. The caller retains ownership and cleanup responsibility on every exit;
this module does not close, signal, kill or reacquire resources.

A successful return is only a partial process observation plus
`atomic_snapshot=false`, `live_binding_verified=false`, and the existing false
runner/publisher/input-authenticity flags. Reads occur at different times; equal
before/after identities do not make namespace/status observations atomic or prove
no intervening change. Exit may occur after the last check. No caller may use
this result alone to qualify a runner or authorize execution.

Full argv, ancestry, executable identity, provenance/signatures, actual sandbox,
network enforcement and cleanup evidence remain future work. Launcher wrapper
behavior must be reviewed separately: upstream behavior can write XDG/HOME MIME
configuration before exec, and argv[0] need not equal the executable path. This
is a design warning, not evidence about an exact installed Chrome package.
No wrapper launch or environment mutation is implemented here.

Existing macOS 4+16+16 journeys and workflows are unchanged. No actual Linux
Chrome execution, proc collection, company data, TLS/OIDC or deployment acceptance
is claimed. Historical e2038a94 runtime images remain outside Next16.4.5 source
patch coverage. Business acceptance stays36/44 (82%), increment0.
