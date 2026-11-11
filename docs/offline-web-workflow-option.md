# Default-off same-run Web startup workflow option

Date: 2026-11-11. Initial preparation used main
`a66d20b2eab8d7949a67d14a8ca32f6ff1fec5fc` (PR221). Publication preparation
was safely fast-forwarded to main `48551a61a8431f58b5014e6164bf7f4762122781`
(PR222), without conflicts or changes to the reviewed workflow/test bytes.
This package connects the existing Web startup probe to the existing
manual image rehearsal. It does not execute a workflow, build an image, start a
container, or establish a defect in the application. The separate installation
manual and current public checkpoints are not changed by this package.

## Exact scope

`.github/workflows/offline-image-rehearsal.yml` gains one boolean input,
`run_web_startup`, default `false`. False does not start Web. The workflow still
performs its existing connected preparation when independently dispatched;
default-off Web does not mean the whole manual image workflow is a no-op.
The Web option is independent of `run_api_startup` and `export_bundle`.
Selecting an input is not an authorization credential. Actual Web runtime needs
its separate applicable approval; the existing API/database scope is not implied
permission for Web, browser, company installation or network changes.

The coordinator validates the Web boolean before child work and passes it only
through an environment variable, not shell interpolation. It starts Web only
after the existing successful build/receipt checks and, when requested, independent
bundle verification. The exact image ID comes from this run's Web build record;
source commit must equal the checked-out HEAD and `GITHUB_SHA`. There is no new
image/tag/URL/container-ID input or fallback to an earlier receipt.

When both API and Web are selected, the API smoke runs first. Its exact success
receipt must confirm its owned container was removed before the Web smoke can
start. Web then uses its own `network=none` container and the unchanged PR221
probe. No API service is listening at its configured loopback API address. These sequential smokes
are not Web/API/database integration. No shared container network or database is
introduced; the existing image preparation and startup implementations are unchanged.

Web success requires an exact, typed two-element return tuple with integer exit
code zero and the complete expected receipt: this Web image/source, final process
phase, both cases passed, runtime-attempt classification, confirmed removal,
unchanged limitations/provenance text, and false database-ready/API-integration/
browser-hydration/offline-acceptance flags. Missing, extra or contradictory fields,
boolean/integer aliases, wrong image/source and incomplete cleanup fail closed.
The coordinator never independently removes a container or retries an uncertain
startup/removal. The existing startup helper retains ownership and cleanup duties.

## Budget, interruption and reporting

The existing 55-minute shared budget, 60-minute job limit, 20 GiB prerequisites,
read-only token, pinned checkout action, manual trigger and concurrency are retained.
Every selected runtime reserves 240 seconds: its existing 180-second work and
35-second cleanup windows plus margin. Earlier checkout/build/verifier allowances
reserve both selected runtimes. API entry also preserves the complete Web window;
each runtime checks its own full window before and after SIGTERM-handler setup.
The final summary retains a 30-second margin. No deadline is reset or increased.

Each existing helper is invoked directly under a temporary SIGTERM handler so a
wrapper timeout cannot kill it before its owned cleanup. The previous handler is
restored in `finally`, and restoration failure prevents success. These are bounded
cooperative checks, not a hard guarantee against daemon failure, blocked host IO,
runner loss or abrupt termination. A late result cannot become a success summary.

The summary uses fixed text and validated image/source/hash values only. It reports
which stages were actually selected and never claims no application started when
Web was selected. It explicitly preserves the distinction between completed server
HTML/disabled-login checks and browser hydration, API integration, offline transfer
or company acceptance. Raw responses, arbitrary receipts and exception text are not
published. A later stage failure prevents the combined success summary; it cannot
undo an earlier completed stage.

There is no artifact upload, retained downloadable bundle, manual dispatch, image
load/push, production change, permission/credential change, dependency/migration
change, or alteration to normal CI, browser gates or branch protection in this package.

## Local validation and remaining gate

Fourteen new regression methods execute the workflow's actual embedded Python with
all preparation subprocesses, API/Web runtimes, clock and signal operations mocked.
They produced 80 failing subcases against the baseline workflow, then passed with
the new option. Coverage includes all eight option combinations, same-run inputs,
prior-stage failures, malformed receipts, budget floors, installation/restoration
failures, interruptions, cleanup uncertainty and redacted/non-integration summaries.
The original 112 image-rehearsal tests remain and pass. Shared test-harness changes
add Web mocks; they do not remove or weaken existing assertions. The new module uses
a module import so unittest does not collect the original TestCase a second time.

The separate startup probe retains its existing regression coverage. Local checks
passed: 923 offline tests, 52 automation tests, 126 CI guards, YAML parsing,
embedded-Python syntax, progress consistency and whitespace. Independent review
found no blocking issue and separately passed 173 focused tests (112 image, 28 API,
19 Web and 14 new workflow tests). Pytest is unavailable locally; its collection
and full CI were not run here. Mock results are not retained as runtime evidence.
Exact-candidate full CI and actual
Web image execution remain unperformed at this local checkpoint. No main merge,
deployment, offline handoff, three-layer or company acceptance is claimed.

Business remains 36/44=82%, increment 0; modules
100/100 demo/100 demo/100/89/60/17; plans 100/100/20/33/40/40/0;
browser stage 1/4 and finite plan 8/8 unchanged.
