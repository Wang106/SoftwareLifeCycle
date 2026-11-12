# PR224 branch-only static package inspection

This diagnostic branch is based on PR224 source
`c731b4be1feb1d0d5b30efaf46a3ed56e4d13640`, whose main baseline is
`23e3153f2996d7afbc1bcb9802d062d3070895a8`. It is not an acceptance repair.
Never merge this branch-only replacement of `browser-diagnostics.yml` into main
or the application PR. No acceptance pins, existing tests or normal CI change.

The workflow and validator follow published PR210 diagnostic tooling commit
`67a283e1b819a34804545d7ff2809fc50a004424`, including its fixed-name safe error
reporting. The static inspector is unchanged and checked out separately from
the exact PR224 source. The tooling checkout is the dispatched commit; source
and tooling identities must match the validator and inputs before any download.
These consistency checks and the approval phrase are not authorization proof.

## One separately authorized execution

The owner approved one static inspection on a free GitHub standard macOS runner,
covering official Google download, signature, version, architecture, size, digest
and a small text evidence artifact, without installing or running Chrome.
Only `macos-26`, read-only repository permissions and pinned existing actions are
used. No paid runner, purchased capacity or new resource is permitted. Verify
eligibility before dispatch; stop if fees or permissions differ from approval.

Use the already registered `browser-diagnostics.yml` entry with ref
`diagnostics/pr224-pkg-inspection`. Before publication and dispatch, independently
review the complete four-file diff, verify the remote tooling commit and fixed
source, inspect existing runs and confirm none has already performed this approved
operation. Attempt1 rejects reruns but not a second new dispatch. Do not repeat
an uncertain dispatch. If the ref moves, stop and review. If GitHub rejects the
registered-entry route, stop rather than changing main or the PR176 guards.

Dispatch inputs:
- `source_head`: `c731b4be1feb1d0d5b30efaf46a3ed56e4d13640`
- `tooling_head`: the independently reviewed, published diagnostic commit
- `approval`: `static-only-no-install-no-launch`

The fixed official HTTPS URL rejects redirects. Download is capped at 1 GiB
and a total 120 seconds, with exact Content-Length and independent disk hashing.
Native pkgutil must report trusted Apple signing and the exact Google Installer
chain before expansion. Expansion is bounded to 180 seconds, 100000 members,
4 GiB sampled expanded bytes and a 1 GiB free-space floor. Sampling is not a
hard disk quota. Safe ownership/modes/symlinks and strict deep Google application
signature verification precede reading signed plist identity/version.
Package hashes are checked before and after inspection.

The unchanged inspector requires a Darwin arm64 host. Its native codesign display
reports binary architecture; the reviewer must confirm arm64 is present in the
complete output. The inspector does not independently assert the architecture
string. Missing or contradictory architecture evidence cannot approve a pin.
No installer, Distribution script, package script, Chrome launch or even Chrome
`--version` execution is permitted. No sandbox/security settings change.

The evidence uploader publishes only `pkg-inspection-evidence/static-observation.txt`
after scope validation, even if later inspection fails, with 14-day retention.
No package, extracted bundle or other binary is uploaded. A partial artifact is
not success. The private staging directory is left to runner reclamation, not
claimed as confirmed cleanup. Cancellation or runner loss leaves cleanup unknown.

## Evidence review and later repair

Require a successful exact-source/tooling run and complete text showing source,
stable digest/size, native package trust chain, strict bundle signature, signed
version, identity and architecture. The failure-log digest alone is insufficient.
Static inspection is not browser, sandbox or application acceptance. If provider
bytes change or evidence disagrees, stop rather than adopting an unverified pin.
Any later pin change is separately reviewed and must pass all unchanged normal
CI signature, executed-version, sandbox, journey, report and aggregate checks.

Local tests use synthetic metadata and mocked native operations only. The new
scope tests cover event, repository, ref, workflow, attempt, checkout, inputs and
safe errors; existing inspector tests retain their I/O guard. Existing tests of
the main DMG diagnostic describe the main workflow, not this temporary replacement;
they must not be changed to accommodate this branch. No local test constitutes
macOS trust evidence or a dispatched inspection.

Preparation validation: 11 new scope/workflow tests, 28 unchanged static-inspector
tests, 30 unchanged acceptance-guard tests and 9 unchanged PR176 event tests pass.
YAML semantic checks, Python AST parsing and whitespace checks pass. A full
discovery on this temporary diagnostic branch reports 132 test entries with
18 failures and 2 import errors, all from existing main-DMG fixtures expecting
the replaced inline diagnostic heredoc/job. Those tests remain untouched; this
branch is not a normal-CI candidate. Full original PR224-source guard discovery
passes all 126 tests, with the original workflow and acceptance pins unchanged.
