# Synthetic bounded-byte ownership coordination

`tests/fixtures/linux_binding_fixture.py` (under scripts/ci) connects existing
OwnedDirectory complete-record reads, the #259 fdinfo parser, parse_stat, and
#258 OwnerModel. It is imported only by synthetic contract tests. There is no
CLI, live backend, sampler activation, proc access or qualification entrypoint.
The strict Linux6.8/6.12 x64 CONFIG_PID_NS parser profile remains unchanged.

## What this adds

A one-use session issues its own opaque fixture root tokens and model lease.
Injected operations must use those tokens; no numeric PID open or retry exists.
The virtual `record` entry is a fixture-only bounded stream, not a Linux fdinfo
pathname. Its subclass reuses OwnedDirectory's reader and cleanup unchanged.
Actual stat uses the existing fixed stat entry. Positive short reads continue;
EOF is required, with an extra positive-size read at the limit. A read failure,
overlong stream or absent EOF never supplies partial bytes to the parser.

The sequence is fdinfo read/match, anchored stat read/PID/start match, second
fdinfo read/match, then exit check with the original fixture pidfd token. Each
stage consumes the existing model's fresh receipt only after byte validation.
No stage can continue after mismatch, model view/generation/replacement fault,
unknown/exit, read error or parser failure. No successful result is returned
before all owned cleanup attempts complete. Each acquired record and each of
four fixture roots receives one close attempt, with no uncertain-close retry.
An interrupted attempt still cleans its roots; cleanup failure is explicit.
No partial result is stored on the session; a second run is rejected.

## Evidence versus assumptions

The model supplies invented PID4123/start124 and common-view facts. Injected
operations and model events cannot authenticate bytes, ensure exclusive OS FD
lifetime, detect a real view change, or prove that a fresh read generated new
kernel data. The final original-token check only verifies fixture call identity;
it is not real pidfd polling or binding. A malicious/cooperating injected backend
can lie. The coordinator is not a security boundary against in-process code.
MODEL_PROTOCOL_COMPLETE retains all authenticity, binding, common-view,
freshness, atomicity and runner-qualification flags false.

These sequential observations are not atomic. No hard I/O deadline is claimed.
A future trusted broker must establish authentic common procfs view, exclusive
original handles, fresh noncached record generation and original pidfd liveness.
Holding an fdinfo descriptor alone does not bind its numeric FD slot to a pidfd.
See [ownership contract](linux-resource-ownership-contract.md) and
[parser profile](linux-pidfd-fdinfo-parser.md). Before a separately authorized
live preflight, record the runner and offline guest's actual kernel and
architecture separately; this package does not require an ISO replacement.

## Validation and limits

Initial regressions failed for the missing coordinator. The later token-replacement
regression separately failed before its fix. All eleven now pass. All205 existing-plus-new contract tests pass from the backend cwd.
The first read-only-sandbox suite attempt could not create temporary fixtures;
rerunning with approved temporary-file access passed without code changes.
Independent review and exact-head ordinary CI are recorded in the draft PR.
Existing macOS4+16+16, signatures, sandbox, CI and production code are unchanged.
No live proc/pidfd/process/browser exercise, install, workflow/security changes,
credentials, deployment or company data. Business36/44=82%, increment0.

Independent review reproduced public exit-token replacement. A failing regression
now covers read-time and cleanup-time replacement; the property is read-only,
and exit/cleanup retain the original internal token. Python private-field
introspection remains outside this synthetic contract, not a security boundary.
