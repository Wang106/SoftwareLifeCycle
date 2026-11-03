# B2 component browser CI integration candidate

This local-only follow-on starts from PR #175 head
`a470a5f1ce1326c862fd9df08502accb1240b581`. Its existing CI run
`41637422663` succeeded: frontend 2098 tests, backend 2846 plus 26 subtests,
296 PostgreSQL cases without skips, original browser eight journeys, and
aggregate acceptance. That run did **not** execute the five component journeys.
The earlier component design and handoff describe that pre-integration snapshot.

## Minimal change

- Keep the existing `browser` job, macos-26 runner, pinned actions, fixed signed
  Chrome PKG preparation, sandbox, original eight journeys/report and aggregate
  dependency unchanged.
- After the original browser command succeeds, run the independent five-case
  component config, followed by its strict report validator. Normal GitHub
  Actions shell failure propagation stops the step on either failure. There is
  no skip condition, retry, continue-on-error, executable override or fallback.
- Save `frontend/component-browser-results/` as a separate
  `component-browser-evidence` artifact, with missing files treated as errors and
  14-day retention, following the existing non-cancelled evidence convention.
  The original `browser-evidence` artifact remains unchanged. Both suites use
  the same runner and already-verified browser, whose diagnostic record remains
  in the original artifact. No duplicate browser download or new job is added.
- The existing aggregate requires `browser=success`, so a component run, report
  or artifact failure blocks acceptance without changing branch protection.

The offline workflow contract checks exact command order, independent output,
mandatory report validation and unchanged aggregate. Negative controls reject
missing/duplicate steps, discovery-only execution, retries, conditions, relaxed
shell failure behavior, environment overrides and incorrect artifact settings.

## Validation boundary

Local checks on 2026-11-03: 86 CI guard contracts passed (including the new
positive contract and 15 negative mutations); 29 component harness/report
contracts passed with zero failures/skips; TypeScript noEmit passed; Playwright
discovered exactly five scenarios. Progress-ledger and whitespace checks passed.
Removing only the two added workflow steps restores the PR175 workflow
byte-for-byte. Independent read-only review found no blocking issue and reran
the 86 guard contracts and 24 report/config tests successfully.

This candidate has not been uploaded and has not triggered CI. Local discovery
is not execution. The five component journeys remain unexecuted until the
approved runner completes both execution and strict report validation.
Existing 15-minute browser timeout is preserved; actual runtime margin must be
checked after an authorized CI run rather than assumed from local contracts.

No production code, dependencies, real identity, business data, database writes,
browser security configuration or existing test/report gates are changed.
Synthetic component evidence still cannot prove authenticated actor correctness
or replace backend/real identity acceptance. B2 completion and milestone counts
remain unchanged.
