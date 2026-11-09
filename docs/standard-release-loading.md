# Standard release catalog loading

## PR208 second CI and real child retry correction (2026-11-09)

[CI42619068391](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42619068391)
verified head `d469e03047f45e39402fdd2b2b34cd75c6c4c915`, preview merge `cdc0faba7a2d78fb5822e85be8f4540b8be77fc1`,
and tree `ece7be372e21292da8cbf3acb86cd6666b9cf3ff`. Its 2273 frontend tests and
production build passed. Browser results remained 14 passed / 2 failed, and
component journeys did not run. The disclosure assertions now passed, including
pending-to-unavailable behavior, but both batch journeys timed out waiting for
a new document after retry. Trace and request evidence showed only the initial
one document, one parent read and one batch read; clicking merely appended the
row fragment and left the error visible. This was a real retry bug, not a reason
to weaken the response predicate or increase the timeout. The first CI backend
was ultimately cancelled and its CI acceptance failed.

The minimal correction removes the fragment only from child retry links. All
seven normalized query fields and the selected expanded row remain, as do row
anchors on ordinary child pagination. Retry does not promise the old scroll
position. A GET form with the same target fragment is not a reliable alternative:
[HTML navigation](https://html.spec.whatwg.org/multipage/browsing-the-web.html#navigate)
and [Chromium FrameLoader](https://chromium.googlesource.com/chromium/src/+/0d4c0e490b48d360f5ab6fbcdb673c3cd5a5f31e/third_party/blink/renderer/core/loader/frame_loader.cc)
also permit same-document navigation for that form. No script, redirect route,
extra query field or automatic retry is added.

The strengthened two stall assertions and a new retry/pagination contract first
failed three cases while thirteen core controls passed. After the one-line
production change, 465 selected frontend checks and 173 focused checks passed,
with TypeScript and diff checks. Independent review passed another 179 checks,
TypeScript and diff, and reproduced exactly three failures / thirteen passing
controls by restoring the old href only in memory. No blocker was found.
The browser batch journeys now begin with the
row fragment already present and still require a real new document response,
cleared document marker and an additional API read. A new exact full CI and
browser run remain required. Previous loopback FCP values are not reused as new
candidate acceptance or production performance.

[Second-run browser evidence](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42619068391/artifacts/13677025087).


## PR208 first CI and disclosure assertion correction (2026-11-09)

[PR208](https://github.com/Wang106/SoftwareLifeCycle/pull/208) published the exact
17-file tree `c7e64870baf8c9fe2e472d2723481692eeb5560e`, head `fe002f580a050ba8cc0af95c7eaa6e964a2260bd`.
[CI42617261863](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42617261863)
checked preview merge `d21768c2bad6429a2a66b213d02c23a5d8595c5f` with the same tree.
All 2265 frontend tests and the production Next/OpenNext build passed. Strict
Next browser results were 14 passed and 2 failed, with no retries, skips or flaky
results. Component journeys did not run because the preceding step failed.
Official Chrome signature verification and chromiumSandbox=true passed.

Both batch header/body journeys failed at the initial status-count assertion.
The actual traces each contained two pending/status/aria-busy nodes: the selected
native details was open and the other was closed. getByRole without includeHidden
correctly exposed only one status. The same old assumption also occurred later
after navigation without a selection; that branch was not reached in this run.
The production component's disclosure behavior is retained.

Eight new cases executing the actual browser assertion helper first failed while
37 existing fixture cases passed. The correction checks each row's pending DOM
and hidden-inclusive status count, exact native open property, and separately
requires one visible status for the selected row or zero with no selection.
Both DOM states are still mandatory. Final loading-clear checks now include
hidden status nodes too. Native retry, pagination and both stale-result journeys
remain mandatory with unchanged completed-RSC marker evidence. The regression
model is not a real browser and cannot prove native visibility by itself.
The corrected selected suite passed 464 tests, the focused fixture/report suite
passed 139, and TypeScript/diff passed. Independent read-only review checked the
actual traces and eight helper cases, reran 139 tests and TypeScript, and found
no blocker. A fresh exact candidate CI is required.

The two completed parent journeys had synthetic initial FCP 264/308 ms and four
late-data-completed results across Reset and /projects. Batch journeys stopped
before timeout/recovery evidence; LCP was not collected. These are loopback
results, not production performance or backend recovery.
[Browser evidence](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42617261863/artifacts/13672209956).

The remaining sections retain the original prepublication evidence and its
limits; this section supersedes their unpublished/unexecuted status.

## Verified baseline and remaining problem

This package starts from merged PR207 main
`7549f846cf9c65da589004eea802c8340f2a6abb`. Its complete
[main CI42596292860](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42596292860)
passed: 3486 backend cases, 2592 subtests, 306 PostgreSQL-module cases without
skips, 2192 frontend cases, 12 Next browser journeys and 16 component journeys.
Cloudflare production build `eb319c93-e130-4448-82d1-8466b4504964` succeeded with
version `688b730a-df49-47dc-8c4a-87388ead4245`. Those are baseline results, not
this candidate's CI. The continuation run was skipped; no separate Actions
deployment run was observed. Render's latest observed deploy remained PR206
`4a94e58f` with `update_failed`; this package does not restore the old database.

PR207's changes/issues production UI was observed on 2026-11-09: their titles
and filters appeared while only data remained pending, later showing explicit
unavailability and unknown counts. Those UI observations are not production
FCP/LCP or evidence of backend recovery.

The standard release route uses `supplier-release-catalog.tsx`. Before this
repair, it awaited the parent catalog and then its application batch before
returning the title, filters, parent summaries or paging. Neither read supplied
a timeout. Four no-network probes against the actual route/component/reader
confirmed that parent headers, parent JSON body, batch headers or batch JSON body
could each leave only the global loading fallback in the first stream. These
are structural reproductions, not an explanation of production cold-start time.
PR185's existing maximum two HTTP reads and five SQL queries remain unchanged.

## Bounded behavior

- The standard directory title, links, GET filters and current-filter summary
  render synchronously without starting catalog reads outside the data boundary.
- A boundary keyed by all seven supported query fields waits for the parent
  catalog. Unknown or failed parent counts remain `—`; real empty data stays zero.
- Once the parent is available, real totals, supplier groups, standard-release
  summaries and parent paging render independently of application data.
- Each application area has its own pending view but awaits one shared batch
  promise and one whole-batch validation. Rows use release IDs, not positions.
  There is no per-row request or fallback to the old N+1 path.
- A failed or invalid batch keeps the real parent visible and marks only the
  application area unavailable. Empty child pages remain distinct from failure.
- Native retry preserves normalized q, status, software_id, limit, offset,
  applications_for and application_offset. Child retry omits its fragment to
  trigger document navigation; ordinary child pagination retains row anchors.
  Unknown query fields are not copied. Existing parent/child pagination,
  selection, grouping, integer-spelling and batch-validation behavior is kept.
- All framework links in this directory explicitly set prefetch=false. Clicking
  and paging still work. This avoids unsolicited background navigation while
  the newly available shell or rows are visible; global prefetch policy is not
  changed. Native retry is not automatic retry.

### Exact timeout claim

The parent receives the existing 15000 ms header-and-body timeout option. A
monotonic deadline is recorded when its data component starts. The batch only
receives the remaining allowance after elapsed parent work; an exhausted or
invalid allowance prevents the batch from starting. It never receives a second
full 15000 ms after a slow parent.

The shared apiGet helper still awaits Next connection() before creating its
timer. Therefore this is **not a strict end-to-end 15-second deadline** covering
Next connection, SSR scheduling or delivery. It does not promise a successful
response within that time. The shared API helper/default is not modified.

## Regression and review evidence

The first 14 core tests produced 13 expected failures and one passing existing
error-semantics control before implementation. The later directory-prefetch
regression failed while the other 32 core/layout/filter cases passed, before
explicit prefetch=false was added. Six fixture/report regressions also failed
before their support was implemented.

After implementation and the pagination-fixture correction, 456 selected frontend tests passed with zero failures,
skips or cancellations. TypeScript --noEmit --incremental false, 52 automation
checks, 126 CI contract checks, diff and development-progress checks passed.
This is a selected regression run, not the complete frontend suite or a build.
The previously restricted full local npm/network operation was not repeated.

Existing layout assertions were preserved. Their final-state harness resolves
actual async server children before static rendering; synchronous localization
providers remain inside React. This avoids counting historical stream fallback
markup as final DOM. It is not streaming evidence: the new core suite separately
uses actual React streams and the real API reader with synthetic fetch/timers.
Filter tests retain their assertions and use real loading-component imports and
an allReady stream. React development key warnings in the final-state harness
are not treated as browser acceptance or hidden by changing assertions.

Independent core review found no blocker, reran 33 tests and a concurrent A/B
probe with the newer batch resolving first: no parent/child crossover, four
requests total and no remaining timers. Independent browser-evidence review
initially passed 123 mock/report tests and probes rejecting nine RSC
candidates and enforcing the shared inspection deadline, but missed a pagination
fixture contract gap. A later comparison with the real backend found that the
first fixture skipped parent pages and repeated IDs. Six new contract cases
first produced four failures and two passing controls. The fixture now uses
total 12 / limit 10: ten unique first-page parents with next offset 10, then two
distinct final-page parents with no next offset. Batch rows match each page by
ID, selected child pages cover twelve distinct rows, and late payloads retain
the same relationships. Obsolete offset 20 paths are rejected. The four browser
journeys now assert these real counts and offsets without weakening their other
checks. Final independent re-review passed 131 mock/report tests plus all parent,
child and late-payload contract probes; it supersedes the initial incomplete
clearance. Neither reviewer ran real browsers, services or databases.

## Actual browser acceptance still required

Four new production-Next journeys cover parent headers/body and batch
headers/body. The exact report requires all 16 Next journeys, including the
original 12, and preserves all 16 component journeys. Signed official browser,
enabled sandbox, no retry/skip/flaky allowance and aggregate checks are unchanged.

Each new journey exercises nonempty seven-field filters, the two loading
layers, native retry, parent and child pages, and two separate stale-result
scenarios: Reset to a new query and navigation to /projects. Proof requires
nonempty prior requests and actual terminal events. Only a completed RSC body
with its unique marker counts as delivered late data. Cancellation and
marker-free completion remain separate outcomes. No fixed sleep substitutes
for this proof, and live streams are not buffered. The inherited eight-body,
256 KiB acceptance limit and five-second inspection deadline remain; Playwright
allocates a complete response buffer before the size check, so that limit is
not a pre-allocation memory bound.

Prepared timing attachments are synthetic-loopback observations, with clocks
and missing/null values distinguished. LCP is not collected. The new journeys,
complete frontend/build, exact candidate CI and production UI have not yet run.

## Homepage and scope exclusions

A separate read-only probe composed the real homepage, root layout, language
provider and navigation provider with a held API. Both languages emitted the
sidebar, title and four fallback cards before API release; 16 existing homepage
tests also passed. There is no source evidence for another homepage-shell fix.
Current browser tooling provides UI/DOM observations but not separate production
Navigation Timing, FCP/LCP or network/trace readings. User-network first-open
latency therefore remains unmeasured, not attributed to cookies, Cloudflare or
the expired database by guesswork.

No homepage/application-directory code, backend, SQL, API defaults, dependencies,
workflow, provider settings, credentials or database is changed. Business
milestones remain 36/44 (82%), modules 100/100 demo/100 demo/100/89/60/17 and
plan 100/100/20/33/40/40/0. Next steps are normal authorized publication, exact
candidate CI and independent main/provider checks, followed by read-only UI
verification. This checkpoint is still uncommitted and unpublished.
