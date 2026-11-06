# B3 bounded cancelled-reload and explicit-retry tests

Date: 2026-11-05 (UTC+8). Baseline main
`07278bc53ced14950b36df9d075c361bf26f82f5` (merged PR180), no open PR at start.
Implements only the two cases designed in
[browser-layer-evidence-review.md](browser-layer-evidence-review.md).

## Baseline evidence

Independent [main CI42027812570](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42027812570)
attempt1 passed frontend2102, backend2846 plus26 subtests,296 PostgreSQL cases
without skips,52 automation/126 guards and0029 SQL/PG round trip. Original8 Next
plus14 component journeys passed strict reports with signed Chrome157.0.8103.39,
sandbox=true, retries0. Cloudflare production build
`cf998632-7516-4786-b772-60175c981569`, version
`1c6bd499-0ba4-47b1-aa8c-206886f37407` succeeded. Actions deployment42030162686
and continuation42030162895 skipped. This is baseline evidence, not execution
of the two new cases or acceptance of live database/real identity/company operations.

## Two new journeys

1. Prepare/confirm and send once into synthetic unknown. Capture the original
   command bytes, request ID, scope/digest/reason and rendered recovery envelope.
   Put a test-only marker on the current document. Reload, assert the actual
   beforeunload dialog and dismiss it. Verify the actual dismissed warning AND retained
   document marker/URL/unknown error/full scope/reason/command/export. Explicit
   retry and query remain enabled; reset, receipt and audit link remain absent.
   Exact API request list stays context then one approval, including a bounded
   idle observation. This cancels navigation, not a backend business operation.
2. Enter unknown after one approval. Observe no automatic retry/query, then reset
   the synthetic held-response promise and explicitly double-click the retry.
   Exactly one additional approval POST uses identical original serialized bytes.
   While genuinely held, result is sending and send/retry/query/reset are absent,
   command/export stay frozen and no receipt exists. Release one valid original
   receipt, verify all receipt fields, historical warning and original audit link,
   confirmed state and no further approval or receipt query.

Original14 component test bodies and original8 Next journeys remain unchanged.
The strict component report requires all16 title/file pairs; individual omissions
and old14 reports fail even if the claimed total is16. Existing missing/duplicate/
wrong-file/errors/retries/skips/discovery-only checks remain. Shared route, origin,
credential, body, page-error and server-violation guards apply to the new cases.
The200ms idle checks are bounded observations, not indefinite guarantees.

No application code, dependencies, server handler, CI workflow, browser candidate,
sandbox, identity, business-write mode, database or company target changed.
Back/forward, cross-tab coordination and the real HTTPS/OIDC/actor chain are not
covered. Stage remains1/4 and business36/44=82%, delta0, modules100/100demo/100demo/
100/89/60/17, plans100/100/20/33/40/40/0 and finite-plan8/8 unchanged.

## Candidate validation

Local validation passed: full frontend2103/2103 (no failures/skips),82 targeted
workbench/transport/recovery/proxy/harness/report contracts,126 CI guards,52
automation contracts,TypeScript,16 component plus8 Next discovery,progress/link/
whitespace checks and exact preservation of14 original test bodies/history/business
groups. Independent code review found no blocker and separately passed29 report
contracts,typecheck and16+8 discovery. Independent documentation consistency review also passed.
Linux lacks
the fixed signed macOS Chrome; new16-case browser execution remains pending and
discovery does not count. No alternate executable or security relaxation is used.
No backend/PG or production build is claimed locally for this test-only candidate.
After publication, require exact-head full CI and strict8+16 browser reports;
after an authorized protected merge, verify new-main CI/provider separately.


## First exact-head browser attempt and bounded correction

PR181 head `f99c18fd1c14ffe568ab181ab28c1d8dbab24862`,
[CI42039749777](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42039749777):
original8 Next passed; component15 passed and cancelled-reload case failed at
60-second test timeout. Explicit retry passed. The test waited for Playwright's
reload completion promise after dismissing beforeunload; that promise only
rejected during timeout cleanup, so the subsequent URL assertion saw a closed
page. This is not evidence that retained-state assertions passed.

The correction schedules native window.location.reload in the page and waits
for the actual beforeunload dismissal, then directly checks all existing URL,
document marker, frozen state/export and exact-request assertions. No navigation
completion/rejection is used as cancellation proof. Timeout/retry policy, the
16 mandatory titles, production code and security gates remain unchanged. New
head execution is required; this failed head cannot certify the correction.

Downloaded component artifact13419648678 trace confirms beforeunload occurred,
dismiss completed at trace time25822.48ms, and reload has no normal completion
record. Independent review also checked Playwright's cancelled-navigation
handling: dismissal need not settle a pending page.reload promise. The correction
passed full frontend2103/2103 without failures/skips,82 targeted contracts,
TypeScript and16-case discovery; actual fixed-head
browser execution remains pending.

Initial CI42039749777 subsequently completed/failure: frontend and backend
succeeded, browser and CI acceptance failed. It was not rerun unchanged.

## Verified publication and merged-main checkpoint — 2026-11-06

The corrected PR181 head `0ff8e256aa35210c192ed9f829ad45d0d8cf57a4`
passed [CI42042337722](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42042337722)
attempt1, including actual8+16 browser journeys. It was not an unchanged rerun.
Normal protected squash merge produced main `e6e03b76f8e662652cf0ad321912eeac885ee9e1`;
tree `55185792709268f546468f06ed1a3a59ffe15855` matches the reviewed local candidate.
Independent [main CI42134422605](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42134422605)
attempt1 succeeded: browser127618824577, frontend127618824695,
backend127618824290 and aggregate127624513499. Logs prove2103 frontend tests,
2846 backend plus26 subtests,296 PostgreSQL cases/no skips,52 automation and126
guard contracts, migration0029 SQL/PostgreSQL round trip. Backend pytest took773.84s.
Actual8 Next plus16 component journeys passed strict reports, zero failures/skips/
retries, signed Chrome157.0.8103.39 and sandbox=true. Retention-limited artifacts:
[Next13464986841](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42134422605/artifacts/13464986841),
[component13465580135](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42134422605/artifacts/13465580135).
This checkpoint inspects logs and artifact identifiers, not fresh archive contents.

Cloudflare check127619794117 succeeded: production build
`2f18577e-ce94-425b-8906-6383ed343d18`, version `e6be5ffe-2ac6-48c9-a7ba-638e839d4360`.
Actions deployment42136123760 and continuation42136123717 skipped. This is not
live database/business-health acceptance. Earlier pending paragraphs are historical;
B3 remains bounded, not full authentication/back-forward/cross-tab acceptance.
