# Dashboard loading and unavailable-state presentation

Baseline: PR183 main `1fcf1c6ce253038646a6c3b8f6f00fa963714565`.
This bounded package addresses homepage presentation during a slow/unavailable API,
not recovery of backend data or a demonstrated reduction in network latency.

## Evidence and limits

The user reported blank homepage content and loading during navigation while other
sites were fast. Read-only inspection of https://softwarelifecycle.whf969.com/
observed the framework/loading state followed by unavailable dashboard data. A
project navigation showed loading around 291ms and unavailable content by a later
20.9s observation; that interval is not an exact completion-time measurement.
Render logs showed startup migration failing to resolve the expired database host,
with no listening service port. The owner explicitly declined keeping/rebuilding
that database. No service setting, database, identity or payment action is taken.

The homepage already had a Suspense boundary and real React streaming regression;
the heading could be sent before summary data. Shared apiGet uses no-store and only
has a deadline when explicitly supplied. Homepage15s, project15s and demo10s budgets
remain unchanged. Navigation prefetch is already restricted. No evidence supports
changing these budgets or increasing concurrency as a cure for backend failure.
Standard catalog N+1 reads are a separate observed inefficiency, not modified here.

## Bounded behavior

The homepage's own pending fallback shows the four known navigation cards with
unknown metrics (—), a busy/read indicator and an explanation that data is pending.
It neither claims zero records nor starts extra reads. Existing heading/sidebar
remain. Successful delayed data replaces the fallback using the same request.
A failed/unavailable summary explicitly distinguishes unavailable current-release
and recent-activity sections from a successful empty result. Native dashboard
reread remains the only retry; failed requests do not unlock background prefetch.

The actual dashboard still uses exactly one summary request and the existing 15s
header/body deadline, cancellation and late-result handling. Shared api.ts, router,
provider settings, identity/write permissions and database are untouched. All
existing success/empty-data and precise record links are preserved.

This is a user-visible loading/error clarification, not a claim that the whole
website is faster, that origin streaming is never buffered, or that live records
are available. Tests must separately cover pending, slow success, successful empty,
HTTP/network/JSON failure and deadline outcomes, in Chinese and English. Node React
streaming evidence is not a new actual homepage browser performance benchmark.

## Validation and continuation

Regression-first implementation and independent review are required. Keep existing
8 Next plus 16 component browser journeys, signed browser/sandbox/zero retry and
full frontend/backend/PG/aggregate gates. Candidate exact-head and merged-main CI
must be checked separately from baseline PR183. No new browser journey count or
business milestone is claimed solely from this presentation package.

After closure, prioritize evidence-based performance work and offline dependency,
image, diagnostic/logging and backup/restore preparation. Real runtime infrastructure
and company acceptance remain unverified; do not rebuild the old public database
or silently substitute sample metrics for unavailable live data.
Business36/44=82%,delta0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser-stage1/4 and finite-plan8/8 unchanged.

## Local candidate evidence

All seven new regressions failed against the baseline before implementation.
After the bounded change: 14 homepage/priority tests and 30 combined homepage,
shared deadline and project-catalog tests passed; full frontend2110/2110 passed
without skips/failures. TypeScript, unchanged8+16 browser discovery,126 guards,
52 automation, both15-case offline suites, progress/links/history/unchanged business
groups and whitespace checks passed. Independent review found no blocking issues
and separately passed16 focused cases, TypeScript, progress and whitespace checks.
Discovery is not execution; no new homepage browser timing measurement is claimed.
The candidate is still local and awaits publication/exact-head full CI.
