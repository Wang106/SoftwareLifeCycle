# Change and issue catalog loading

## Scope and evidence

The bounded repair affects `/changes` and `/issues` only. Their shared catalog
previously awaited the API before returning the page title, filters or results.
The existing global route loading screen did not supply those controls. On
2026-11-09, read-only production observation reached `/changes` promptly but still
showed only global loading at 25.9 and 56.7 seconds after the click. These are
tool-observation intervals, not browser Navigation Timing, FCP or LCP values.

An isolated React stream against main `08dae2b6` reproduced the missing heading
and filters while synthetic upstream reads were held. The new seven initial
regressions failed before the repair. No public database was contacted by the
local tests, and the expired database is not recovered or replaced by this work.

## Behavior

- The title, description, normalized GET filters and reset link are emitted
  independently of catalog data.
- Only summary counts and the result table wait inside Suspense. The boundary
  key includes the catalog kind and the complete allowlisted query, so changing
  either starts an independent pending view rather than retaining old results.
- Pending and unavailable summaries display `—`, never invented zero counts.
- Each catalog makes one no-store API read with the existing 15000 ms deadline
  covering both response headers and JSON body. Cancellation and late results
  retain the existing shared reader contract. The global reader default is not
  changed.
- Failure keeps the original unavailable explanation and adds an explicit
  native GET retry. It preserves only normalized supported query fields. There
  is no automatic retry, polling or user-data cache. A successful empty response
  remains a distinct zero-record state.

The homepage, standard releases, other catalogs, backend, database, credentials,
provider settings and deployment configuration are outside this repair. The
15000 ms deadline bounds an unsuccessful data read; it is not a promise that
business data loads in 15 seconds or that initial network latency is solved.

## Acceptance

Local regression tests use the actual components, real React streams and the
actual API helper with synthetic response/timer controls. They check the shell
before either headers or body finish, precise timeout setup and cancellation,
late success/rejection, normalization, keyed boundaries, native retry, genuine
empty data, bilingual output, and preservation of existing counts and links.

Four additional production-Next browser journeys are prepared for both catalogs
and both held phases using only a finite loopback HTTP fixture and non-buffering proxy.
They must retain the original eight required journeys, signed browser candidate,
enabled sandbox, no retries, no skips, and exact report validation. Browser
fixture execution is not production or company-site acceptance.

Record actual local/CI results and the precise tested commit before publication.
Do not substitute a successful older commit, synthetic report, build or source
inspection for a new browser result. Production cold/warm Navigation Timing,
FCP/LCP, a healthy-backend response measurement and user-network verification
remain separate, unverified work.

## Local candidate checkpoint — 2026-11-09

The isolated candidate starts at main `08dae2b6`. Before implementation, all
seven new shell/deadline/retry regressions failed on the baseline. After the
repair, the catalog suites contain 17 passing cases. The combined targeted run
passed 365 tests with zero failures, cancellations or skips. It includes the new
fixture/proxy/report cases, unchanged project-timeout and loading cases,
localization coverage, Worker configuration contracts and component-browser
report contracts. TypeScript (`--noEmit --incremental false`), `git diff --check`
and the existing development-progress checker also passed.

The extracted summary initially failed the existing localization-coverage
assertion; its original localization boundary was restored and the unchanged
assertion then passed. No test requirement was removed to obtain a pass.

Independent review found two browser-evidence gaps before publication. The new
journeys now await the actual target RSC completion/cancellation events rather
than a fixed delay, and backend release IDs distinguish a real response from a
cancelled no-op. A completed shell-only prefetch is not counted as delivered
catalog data: only a completed RSC body containing the kind-specific synthetic
late-row marker can establish that observation. The test records cancellation,
marker-free RSC completion and confirmed late-data completion separately. The
`completedShellResponses` field means marker-free completion; it does not prove
that the response contained only a page shell. The result must report
the observed branch, not claim late data arrived when the request was cancelled.

Completed-body inspection does not intercept or buffer live delivery. It retains
only size and marker metadata, accepts at most eight candidate bodies of 256 KiB
each and has a shared five-second inspection deadline. Playwright retrieves a
complete Buffer before the size check, so this is an evidence acceptance limit,
not a pre-allocation memory bound. Raw bodies are not attached.

Final independent review found no remaining blocker after these corrections.
It separately passed 148 focused tests, TypeScript and diff checks, and verified
the actual five-second inspection timeout/late-resolution behavior and rejection
of nine candidates. These remain local synthetic checks, not executed browser
journeys.

The full frontend suite, production build, exact candidate CI and actual signed
browser execution have not run for this candidate. Earlier local full-suite
execution encountered a tool restriction; it was not retried through another
entry point. The browser source prepares selected Navigation Timing and FP/FCP
observations with separate browser/Node clocks and cache conditions; no such
browser measurement has been collected yet, and LCP is explicitly uncollected.

## Alignment with PR206 main

The candidate was fast-forwarded to merged main
`4a94e58f3d46f5b3b0f4ae360a4e2a3717bc75ed` without conflicts. All original
13 candidate file hashes were unchanged at alignment. The combined365 targeted
tests, TypeScript, diff and progress checks passed again on that base. The
subsequent edits only add these checkpoint records and update the maintenance
ledger; business milestone groups remain unchanged. At the alignment check,
main CI42583155855 and Cloudflare build06687855 were still running. Neither
those baseline checks nor prior PR evidence substitutes for this candidate's
full tests, build or actual browser journeys. The candidate remains uncommitted
and unpublished at this checkpoint.

A later baseline-only check confirmed frontend CI, the existing strict browser
journey and Cloudflare build06687855 successful. Backend/PostgreSQL and aggregate
completion remained pending. The alignment/checkpoint review independently
confirmed the12 frontend hashes, prior histories, milestone groups and
previous_checkpoint were preserved; no new blocker was found.

The final pre-publication baseline check confirmed all three main CI jobs and
CI acceptance successful on `4a94e58f`. Cloudflare build `06687855` also
succeeded; Actions deploy and wake were skipped. Main is unchanged and no open
PR was present. These are baseline results only. The candidate still requires
its own full frontend/build and all 12 Next browser journeys before acceptance.
