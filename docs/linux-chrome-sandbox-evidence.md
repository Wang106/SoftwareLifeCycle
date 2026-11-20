# Linux Chrome observation consistency preparation

This package provides an offline, bounded JSON evidence checker. It does not
collect evidence, launch Chrome, qualify a runner, verify Google's signature,
or enable a Linux browser CI job. A successful exit means only that supplied
observations are internally consistent. Fabricated but consistent input can pass;
this is not an attestation or an authorization gate.

The concrete benefit is a tested acceptance contract for a future separately
reviewed collector. It rejects missing process/namespace/seccomp, PID-reuse,
unsafe launch-option, non-loopback and incomplete-cleanup observations before
any report can describe them as consistent. Existing signed macOS 4+16+16
journeys and all CI gates remain unchanged.

## Input and result

`python scripts/ci/linux_sandbox_evidence.py < observations.json` reads at most
32 KiB from stdin. It never opens the paths in the input. Duplicate keys,
non-finite JSON, unknown/missing fields and malformed values are refused with a
fixed diagnostic; raw input, command lines and paths are not echoed on errors.
The synthetic fixture in `scripts/ci/tests/test_linux_sandbox_evidence.py` is the
executable schema example. Do not use its made-up version/digest/PIDs as evidence.

The accepted scope is standard x64 `ubuntu-24.04`, a positive non-root UID,
`/usr/bin/google-chrome` launcher and `/opt/google/chrome/chrome` executable.
Version, image identifier and SHA-256 are observed values, not trusted pins.
The `arguments` field currently represents the explicit additional launch
options and must be exactly `["--headless=new"]`; `chromium_sandbox` must be true.
This is NOT a complete Playwright-generated process command-line validator.

Browser/renderer start ticks must use the same host proc/boot timebase; a renderer
cannot start before its browser ancestor. Process identities include PID and start ticks; the renderer's
owned ancestry must end at the browser. Both processes use the same non-root UID.
PID and network namespaces must differ; namespace mode also requires different
user namespaces. A SUID-mode observation is accepted only with PID/network
isolation and seccomp evidence, not merely a setuid file mode. Sandbox page
observations must agree with renderer Seccomp=2 and NoNewPrivs=1. After-snapshot
PID/start ticks and executable digest must match. Loopback HTTP origin uses a
nonprivileged port; every recorded request must be the exact `/probe` URL and a
blocked external attempt must be recorded. Cleanup records browser exit, owned
listener closure and profile removal.

Result: `OBSERVATIONS_CONSISTENT`, always accompanied by
`publisher_signature_verified=false` and `runner_qualified=false`. Zero exit is
only useful for synthetic schema/consistency regression, never deployment or
browser-gate approval. Input authenticity, measurement completeness and a
blocked-attempt count cannot be established by this offline checker.

## Future collector boundary (not implemented or authorized to execute here)

A future reviewed collector must bind the launcher symlink and executable to
owned stable file descriptors, actual package metadata and independent re-read;
verify publisher provenance separately. It must capture the full process command
line (including Playwright defaults), reject sandbox-disabling/security-bypass
flags, and verify ancestry/namespace identities against live owned processes
with PID-reuse protection. Raw `chrome://sandbox` parsing and its version-specific
labels require real platform evidence, not fixture assumptions. The present
structured field contract may need a reviewed revision after those observations.

Use explicit `chromiumSandbox:true`, bounded non-root startup and a fixed owned
loopback probe. Enforce network isolation independently of a request log; do not
claim that a finite list proves absence of background networking. A future
collector must reject inability to observe or enforce isolation. No AppArmor,
sysctl, SUID permission, credential or system-trust modifications are permitted
as a workaround. It must stop/verify only its own process, listener and profile.
No Linux browser is executed by the existing unittest discovery in normal CI.

Linux provenance/sandbox qualification remains unexecuted. Real browser→Web→
FastAPI→PG/disk, real TLS/OIDC, production storage and company acceptance remain
separate. Historical e2038a94 images are not covered by the Next16.4.5 source patch.

## Baseline evidence

Merged PR253 main e285e92c1f73196fbd442a9afe9a8defe664a1e9:
CI44707991621 attempt1 backend cancelled near20 minutes/99%; cause not proven.
Attempt2 succeeded:4463 backend+3567 subtests,410 PG cases without skips,
schema0030; frontend/browser reused first-attempt success (2505 and4+16+16).
Deployment44733789608 and continuation44733789672 skipped. This does not prove
Linux Chrome qualification or resolve the first attempt's performance cause.
