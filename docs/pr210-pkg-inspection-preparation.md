# PR210 branch-only static package inspection

This local candidate replaces the already registered `browser-diagnostics.yml`
entry only on the independent diagnostic branch. It is dispatch-only, not a PR
or push job. Nothing has been uploaded or dispatched by this local preparation.
Do not merge this branch-only workflow replacement into main. Main's existing
workflow and all acceptance gates remain unchanged.

## Separate identities and authorization

The source is PR210 commit `3816b41f48fcc5b43bd44baba9db8a4f1e540488`,
not main and not the future diagnostic PR head. A diagnostic branch changes the
tooling head, not this source identity. Its activation branch is reserved as
`diagnostics/pr210-pkg-inspection`. Tooling is checked out from `github.sha`;
the original static inspector is checked out separately from the fixed source.
Before activating, verify this source actually contains the reviewed unchanged
inspector and review the final tool bytes against the approved diagnostic commit.

The validator proves only metadata/checkout consistency. A caller-supplied
`tooling_head` or approval phrase is NOT authorization. Before any dispatch the
operator must independently verify the approved remote diagnostic commit, branch,
workflow bytes, PR210 source and absence of an existing execution. If the branch
moved, stop and review again. Run attempt 1 rejects platform retries, but cannot
prevent a second new dispatch: check run history and authorize only one run.
No embedded self-referential commit hash can replace this external approval.

## Publication and one approved operation

The user approved using the existing diagnostic workflow entry on an independent
branch for one static inspection. Before publication and dispatch, the parent
must verify the exact approved four-file candidate and remote tooling commit,
source commit, dispatch ref and absence of a prior execution. Use the existing
registered `browser-diagnostics.yml` entry with the diagnostic branch selected;
no new default-branch workflow registration or merge is needed. If GitHub rejects
that route, stop rather than changing events, main or the PR176 guards.

The one-shot execution approval must cover the one macOS runner,
official Google URL download, native package signature checks, bounded extraction,
application signature validation and text evidence upload. Standard runner usage
can incur account charges; this package neither promises zero fees nor purchases
resources. No Chrome installation, scripts, browser launch or version execution.
No company database, old database, API or container is involved.

The unchanged `inspect_pkg_candidate.py` is the static observer, not
`prepare_pkg_browser.py`: it does not enforce the old acceptance byte/hash pin.
It checks the native Apple/Google package chain before extraction, then strict
application signature and signed plist version; its observed digest is not trust
by itself. Existing 1 GiB download/120 second transfer, 180 second extraction,
100000 member/4 GiB sampled tree and free-space guards remain unchanged.
The sampled extraction cap is not a hard disk quota. The inspector creates a private stage for this run but does not actively
delete it. Its later disposal depends on runner reclamation, which is not
confirmed cleanup evidence. Cancellation or runner loss also leaves cleanup
unverified. Do not claim cleanup from an absent artifact.

Successful static evidence is still NOT browser acceptance and does not prove
why the earlier download differed. It cannot verify bytes no longer retained.
Any subsequent acceptance-pin update needs the new complete evidence, separate
review and all existing signature, sandbox, journey and aggregate gates.
Original acceptance constants and the PR176 workflow remain untouched.

## Local checks

`python3 -m unittest discover -s scripts/ci/tests -p test_validate_pr210_pkg_inspection.py`
uses synthetic event/checkout values only. No download, macOS invocation or
candidate content execution is part of those tests. Validate original static
inspector and scope tests separately; no local test is a successful real run.
