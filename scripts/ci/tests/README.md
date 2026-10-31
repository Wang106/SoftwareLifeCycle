# Browser diagnostic platform contracts

Run from the repository root with Python 3.12 (standard library only):

```sh
python -m unittest discover -s scripts/ci/tests -v
```

The tests read the repository-relative `.github/workflows/ci.yml` diagnostic
Python heredoc. Missing, duplicated or renamed delimiters fail rather than skip.
They compile only function definitions and the terminal diagnostic control flow;
they never execute the download, platform probes or mount setup. All native
commands in exercised code receive synthetic results. An audit hook rejects
native process execution and socket operations as an additional fail-closed
boundary. Run these tests in their own Python process; the audit hook lasts for
that process. `python -O` is rejected because the source guard uses assertions.

There are **24 unittest methods**, not 49 independent unit tests:

- 17 diagnostic-summary tests: a platform with no Python xattr APIs, fixed
  macOS `/usr/bin/xattr` list and `-p -x` read forms, missing command, nonzero,
  timeout, empty values, malformed hex, attribute-name injection, individual
  failures, independent plist/resource/signature summaries and path confinement.
- 2 mount/control-flow tests: missing/null disk metadata, readonly/not-readonly/
  unknown, absent/invalid `ST_RDONLY`, nonmount, shadow observations, and **32
  combinations** of disk projections, mount states, strict outcome and detach
  outcome. Original strict exceptions remain the same objects; successful
  verification still ends in the intentional diagnostic-only failure.
- 5 harness/negative-control tests: malformed heredoc, external-I/O denial,
  reintroducing `os.listxattr`, dropping the final failure, and removing the
  not-readonly rejection. Each mutation must be caught by the relevant test.

The fixtures create only synthetic files inside `TemporaryDirectory`; escaping
symlinks point to other synthetic fixture paths. No Chrome, macOS command,
network connection, real database or user data is used. Attributes are checked
as names/length/hash summaries, not logged raw values.

These contracts do **not** validate a real Apple signature, attest a downloaded
package, establish sandbox operation or replace the six browser acceptance
cases. The original strict guard is not repaired or weakened here. The actual
PR172 diagnostic evidence remains separate: at head
`f9e98034cd0ad562205badca3290028cc7cf252d`, run `41235874779` collected summaries
but strict verification still rejected FinderInfo on `app_mode_loader`.
This test-only local package does not resolve that rejection or authorize a
new download/CI run. No automatic workflow hook is added in this package.

The prior scratch tests depended on `/tmp` and PyYAML. This version has neither
dependency and should evolve with the diagnostic schema; do not silently skip
tests when the diagnostic is later removed or replaced. Keep mock contract
results distinct from actual macOS runtime evidence. Business progress remains
82%, browser-stage technical closure remains 1/4, and no database recovery is
claimed.
