# Software producer directory cleanup

## Scope

The producer's `Rehearsal.close()` previously stopped after its first `OSError`,
leaving remaining registered directory descriptors unattempted. It now uses the
existing retained-recoverer pattern: pop each descriptor before one close attempt,
remember the first `OSError`, continue through the remaining registry, then raise
that same error. A second cleanup sees an empty registry. Unknown close outcomes
are not retried because a descriptor number could already have been reused.
This does not guarantee every close succeeded; it guarantees remaining owned
registered descriptors receive their one attempt despite an earlier OS error.

The change is limited to this method plus new regression coverage and checkpoints.
It does not alter receipt v1, fixture bytes, input restrictions, retained evidence,
CLI redaction, workflows, dependencies, migrations, permissions or branch gates.
It does not generalize interruption handling beyond `OSError`.

## Validation

Eight new unittest cases first produced five failures against unchanged main.
All eight pass with the repair. Tests cover first, middle, last and multiple
failures, preserving the first exception object, successful/empty cleanup and no
repeat on second cleanup. A tiny real-descriptor test closes an owned descriptor
before raising, verifies the other descriptors are attempted and actually closed,
and never retries the ambiguous descriptor. The CLI main-entrypoint test performs
the real fixed-synthetic prepare/restore, injects post-close errors during final
directory cleanup, requires nonzero/redacted failure, and verifies retained
`result.json` is not removed. It does not assert that a persisted result alone
means invocation success. Test cleanup removes only its own synthetic resources.

Full local validation passed: 890 offline tests, 52 automation tests and 126 CI
guard tests, all without skips. In-memory Python compilation, progress ledger
and `git diff --check` also pass.
Independent review passed with no blocker; the reviewer independently reran all
8 new tests, 890 offline tests, progress-ledger and diff checks. Local regressions
and independent review passed; publication and exact-candidate full CI remain
pending.

Baseline is PR219 merged main `b7802f20db26e9d62953b99cb34a12df095f2c92`,
verified unchanged and protected before publication preparation; no open PR was
found at package start. [Main CI42987234765](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42987234765)
passed at 2026-11-11 08:43:20 UTC: 3750 tests / 3011 subtests, including 309
PostgreSQL cases without skips, plus frontend, strict browser and aggregate.
Backend artifact `13841550696` SHA256
`3a905f3e9457364bbbc8e658908cb67aab87e2c30d5306c9c5be28fcf446a9af`
matched; its XML has 3750 tests with no bad outcomes. Retained and joint recovery
source/checkout evidence both match this main commit with all safeguards true.
Cloudflare production build `6b6d8d10-5e62-4037-b09a-ac801671c168` succeeded.
Actions deployment42989282567 and continuation42989282715 skipped; Render remains
unverified. These are baseline evidence, not this unpublished candidate's CI or
deployment results.
No database, API, container or manual workflow was executed. Native PostgreSQL,
full backend and browser evidence must come from the candidate's CI, not baseline
PR219. The manual migrated-API run still awaits the owner's signed-in action.

## Acceptance boundary

Business 36/44=82%, increment 0; modules 100/100 demo/100 demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser stage 1/4 and finite plan 8/8 are unchanged.
This is a local resource-cleanup repair, not company recovery or deployment
acceptance. Next gate: authorized draft publication and exact-candidate full CI.
