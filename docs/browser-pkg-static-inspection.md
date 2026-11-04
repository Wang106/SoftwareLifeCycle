# Static official PKG inspection candidate

This local diagnostic is separate from the fixed acceptance candidate and normal
CI. It does not update pins, install anything, execute package scripts or launch
Chrome, including `--version`. No diagnostic run has been dispatched.

The local PR176-only workflow requires a bounded first-attempt transition,
uses macos-26 with read-only repository permission and pinned actions,
and publishes only a text observation artifact. It is not a required browser
check and is not invoked by normal CI. A successful static diagnostic is not
browser, sandbox, authentication or business acceptance.

`inspect_pkg_candidate.py` downloads only the existing exact official HTTPS PKG
URL, rejects redirects, caps bytes and enforces a total child-process transfer
deadline. A valid bounded Content-Length is mandatory and must match the final
streamed count; missing/truncated responses fail. A fresh owned mode0700 directory prevents reuse. Complete streamed
SHA256/size are compared to an independent disk reread; candidate file type,
owner, permissions and stability are checked. Observations are reported without
changing or satisfying the acceptance pin.

On macOS, a successful native pkgutil signature command must report system
trust and the exact Google LLC EQHXZ8M8AV / Developer ID Certification Authority /
Apple Root CA chain. Only then may native `pkgutil --expand-full` unpack the
candidate without installation. The package is rehashed before expansion and
after inspection. Expansion is monitored for a 180-second deadline, 100000-member
and 4-GiB whole-tree budgets and 1-GiB free-space floor; failure kills and waits for
the unpack process. Sampling is not an OS-enforced hard disk quota and may
overshoot between observations. The whole expanded tree is then checked for
safe member types, modes, owners and confined symlinks. Bundle members must have bounded count, safe types/modes and
owners, confined symlinks and regular required resources. Native codesign must
pass deep strict verification with the existing Apple/Google identifier and
team requirement before signed Info.plist identity/version is reported.

The reported version is signed static metadata, not an executed binary version.
No trust repair, re-signing, xattr changes, Gatekeeper settings or alternate
browser fallback is available. The only subprocess outside the static native
allowlist is the isolated Python child running this repository's downloader;
that child never executes content from the downloaded file.

Offline tests use inert synthetic bytes and mocked native commands. An audit
hook rejects actual process/network I/O during tests. These tests establish
control-flow contracts only, not a real Apple signature or browser capability.

Before any later pin-maintenance proposal, review the actual complete artifact,
source/digest, native trust and signed version. If the provider changes again or
any evidence disagrees, stop; do not choose a pin merely to make CI green.
Any updated candidate must still pass all original normal acceptance checks,
including executed binary version, sandbox and the original eight plus five
component journeys. The current acceptance script remains unchanged by this
diagnostic package.

## Bounded PR176 execution (local implementation, not published)

GitHub requires a new workflow_dispatch file to exist on the default branch.
Rather than merge failing required CI, this separate workflow accepts only
pull_request synchronize for main and the six diagnostic paths. It does not
change the existing registered DMG diagnostic or normal CI.

Job conditions require Wang106/SoftwareLifeCycle, PR176, the same-repository
non-fork head branch docs/b2-evidence-b3-recovery, attempt1 and event.before equal
to c8f3deacfd4ab0d453fbed29f8d8cbe0f32dae94. Checkout uses the exact event head SHA,
fetch-depth2 and persist-credentials false. The repository-owned event validator
then verifies the event/repository/PR/base/head/state again, event.after and git
HEAD equal the full head SHA, and exactly one parent equal that fixed reviewed
parent. It requires exactly six added diagnostic files and rejects modifications,
missing files, duplicates, extra files and merge commits before any download.
Event values are read as JSON/data, not interpolated into shell source.

This bounds execution to one direct-child transition from the fixed parent under
normal forward-only publication. Later commits and rerun attempts cannot inspect.
The uploader must verify the parent is still current and create one non-force
commit containing precisely these six new files; a changed parent requires
separate review, not silent rebinding. Parent plus event-head binding is not an
independent cryptographic approval of arbitrary source content. The exact final
six-file diff must be reviewed before publication. This is not a persistent
once-ever registry: a maintainer force-reset/replayed event or changed workflow
could evade that operational bound. Such actions are not authorized; there is
no write token, API dispatch, reset or retry path in this workflow.

Only contents:read is granted. There are no referenced secrets, environment,
write scopes, normal-CI dependencies, new paid resources or candidate execution.
The platform still supplies its normal read-only Actions token to pinned checkout
and artifact actions; no stored credential is passed to the diagnostic process.
A text-only artifact is attempted only after scope validation succeeds, including
when static inspection fails. No package or browser binary is uploaded.

The distinct inspection job is not added to required CI or protection. Green
static metadata cannot replace a failed browser job, prove sandbox acceptance,
or authorize merging PR176. The original fixed candidate and all eight plus five
browser journeys remain unchanged. Native signature, unpack and metadata steps
have not run in this local Linux environment.

Offline validation covers exact valid transition and negative event, fork, PR,
branch, state, parent, checkout, retry and changed-file cases. Actual YAML
contracts check trigger/permissions, pinned actions, exact-head checkout,
validation ordering, static-only commands, text artifact and absence from CI.
Mutated required guards, added triggers, secret references, write permissions,
extra steps and CI dependencies are rejected. Tests use synthetic metadata and
mocked candidate I/O, never actual package/native/browser execution.

Publication and remote execution remain paused pending review of this actual
implementation. No diagnostic upload, dispatch, candidate download or browser
execution has occurred.

Local result: 126 CI contract tests passed, including 28 static-candidate tests
and 9 bounded-event/workflow tests; Python compile and whitespace checks passed.
These results do not assert any native macOS or hosted-workflow execution.
