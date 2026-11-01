# Current PKG candidate contracts

Normal browser CI now selects `scripts/ci/prepare_pkg_browser.py` and the fixed
ordinary Chrome PKG candidate described in
[docs/browser-pkg-candidate.md](../../../docs/browser-pkg-candidate.md).
The retained CfT guard is historical contract coverage, not the active browser
source. The original 24 diagnostic methods and manual-only diagnostic workflow
remain; diagnostic execution still intentionally fails and is not part of this
package's acceptance run.

The [owner's latest authorization](https://github.com/Wang106/SoftwareLifeCycle/pull/172#issuecomment-6550487902)
supersedes the one-shot/nonpaid approval wording in the historical record below.
Ordinary project work and necessary verification may continue; new fees require
approval. Required strict signatures, sandbox, six journeys, report validation
and aggregate failures remain mandatory.

PKG tests use synthetic files and mocked native commands. They cover the fixed
source/digest/size and bounded transfer, package trust before expansion, failure
before candidate execution, and the app identity/version/configuration gates.
They do not download or install Chrome, execute package scripts, verify a real
Apple signature or establish macOS sandbox behavior. The historical 57 methods
passed both locally and in previous-head CI41239803373; that run's real browser
job nevertheless failed strict CfT verification and did not execute its six
cases. Current local discovery and an independent rerun passed **84 methods**
(57 retained +27 PKG).
The exact-head native CI remains pending; prior successful jobs and these
synthetic results do not certify this candidate.

Run all retained and current contracts from the repository root:

```sh
python -m unittest discover -s scripts/ci/tests -v
```

The existing backend CI invokes this discovery command, so newly added contract
files run automatically. A successful synthetic suite cannot replace the
required native browser job. Any real package/app trust or browser failure
keeps aggregate validation failed.

---

## Historical CfT recovery and diagnostic evidence

# Browser diagnostic platform contracts

Run from the repository root with Python 3.12 (standard library only):

```sh
python -m unittest discover -s scripts/ci/tests -v
```

The tests read the repository-relative `.github/workflows/browser-diagnostics.yml` diagnostic
Python heredoc. Missing, duplicated or renamed delimiters fail rather than skip.
They compile only function definitions and the terminal diagnostic control flow;
they never execute the download, platform probes or mount setup. All native
commands in exercised code receive synthetic results. An audit hook rejects
native process execution and socket operations as an additional fail-closed
boundary. Run these tests in their own Python process; the audit hook lasts for
that process. `python -O` is rejected because the source guard uses assertions.

The retained diagnostic suite has **24 unittest methods**, not 49 independent unit tests:

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
cases. The original strict guard is not repaired or weakened here. The exact prior
PR172 diagnostic at head `29bffa68cbdd045280a78762ab6ca5089f562b54`, run
`41237281462`, collected summaries but strict verification still rejected
FinderInfo on `app_mode_loader`; all six browser cases were unexecuted.

The owner separately approved one fixed official CfT ZIP recovery package and
one publication/complete CI on the same draft PR. Normal CI now executes this
standard-library suite from its backend job. Failure propagates to the required
aggregate; these tests never substitute for real browser acceptance. The moved
diagnostic workflow is manual-only, has a different name, requires its exact
ref and first attempt, and still deliberately fails. It is not dispatched in
this package; future diagnostic runs require separate one-shot approval.

The approved candidate is the complete `chrome` mac-arm64 ZIP for
`156.0.8078.80` from the exact URL listed by
https://googlechromelabs.github.io/chrome-for-testing/ . The fixed URL, redirect
rejection, total120s parent-enforced download timeout, archive bounds and
confinement (including local/central metadata, physical record coverage and
independent bounded raw-deflate length/CRC checks), metadata-preserving extraction and member-content comparison all
precede original deep strict Google/Apple verification. Only after trust, exact
bundle version and configured path checks may the binary execute `--version`.
The signature requirement uses CfT's `com.google.chrome.for.testing`, Google
Team `EQHXZ8M8AV` and the original Apple Developer ID chain. No metadata repair,
permission repair, re-signing or alternate candidate is allowed. ZIP availability
and computed hashes are not an independent signature attestation.

The prior scratch tests depended on `/tmp` and PyYAML. This version has neither
dependency and should evolve with the diagnostic schema; do not silently skip
tests when the diagnostic is later removed or replaced. Keep mock contract
results distinct from actual macOS runtime evidence. Business progress remains
82%, browser-stage technical closure remains 1/4, and no database recovery is
claimed.

## Local evidence and limits for the recovery package

Final local and independent review: **57 methods passed, zero skips** — 24
retained diagnostic contracts, 5 workflow contracts and 28 candidate contracts.

All candidate and workflow tests use synthetic files and mocked native commands;
none downloads Chrome or invokes macOS tools. The original 24 diagnostic methods
remain intact, including the 32-case flow matrix and three negative controls.
The added workflow tests reject automatic diagnostic triggers and weakened
browser/aggregate gates. Candidate tests exercise exact URLs, total transfer
limits, hostile ZIP paths/metadata/compressed streams, extraction completeness,
strict failure before launch, fixed identity/version/configuration and ordering.

The unchanged report-checker suite had 41 logic checks pass locally; its one CLI
subprocess test could not complete because this Work runtime returned EPERM from
Node child_process. No assertion was changed. Direct execution through the
available command tool independently verified the same CLI's valid synthetic
report and rejection/redaction for empty, malformed, error-bearing, oversized
and missing reports. This is synthetic report validation, not six actual browser
journeys, and not a claim that the entire 42-test Node invocation passed.
Required full frontend tests and real macOS browser evidence remain the exact
new-head CI's responsibility. No local full backend/frontend build is claimed.
