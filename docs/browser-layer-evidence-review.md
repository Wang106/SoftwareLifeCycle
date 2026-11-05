# Browser evidence layers after B4-A

Date: 2026-11-05 (UTC+8). Baseline main
`a460d104880e9f0a8ba6ae99bb97d3b735537f18` (PR179).
This package reconciles evidence and proposes the next bounded test package.
It adds no test, application feature, identity or environment configuration.

## Verified checkpoint

PR179 final head `250422a8003e2ef17c9bcb6e0991a1ef002551fc` passed
[CI41994348979](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41994348979)
attempt1 before normal protected merge. Independent main
[CI41998260330](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41998260330)
attempt1 passed all four jobs: frontend127146726830, backend127146727075,
browser127146727305 and aggregate127152950494. Final main tree
`33d8d97c9df3d6cda5708ccc3aaaac951bc95664` exactly matches the reviewed candidate.

Main logs prove2102 frontend tests;2846 backend tests plus26 subtests;
296 PostgreSQL-module cases without skips;52 automation and126 browser guard
contracts; single migration head0029 with SQL/PostgreSQL round trip; Next and
OpenNext builds plus disabled-auth bilingual SSR. Eight Next and fourteen
component Chromium journeys actually passed their separate strict reports with
zero failures/skips/retries. Chrome157.0.8103.39 passed the original signed
candidate checks with sandbox=true.
[Next artifact13402055038](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41998260330/artifacts/13402055038)
and [component artifact13400794063](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41998260330/artifacts/13400794063)
are retention-limited. This review inspected job logs and artifact identifiers;
it does not claim a fresh download/revalidation of archive contents.

Cloudflare check127147457375 succeeded for this exact main: production build
`b4796164-c4bb-45fb-b1be-f348f4597cae`, provider version
`0dfff69d-4093-4f2d-b9f9-d6f474a4d912`.
[Actions deployment42000150093](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42000150093)
and [continuation42000150130](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42000150130)
were skipped. Provider build/version is not live API/database/business-health
acceptance, nor is skipped Actions deployment success. No company deployment
or real identity/business writes were enabled.

## Layer-by-layer acceptance matrix

| Layer | Evidence now established | Boundary still open |
| --- | --- | --- |
| Production Next read-only browser | Original8 journeys in frontend/e2e, actual production Next DOM with synthetic loopback API, bilingual historical/read-failure/native-retry behavior | Anonymous disabled-auth fixture, not logged-in approval or real API |
| Actual React approval component |14 mandatory journeys in authorization-approval.spec.ts: original5 B2-C,3 B3 recovery and6 B4-A errors; actual workbench/transport/i18n/Next Link and Chromium events | Harness does not start Next or load browser-auth/session; capability props and responses are synthetic, not authenticated people |
| Frontend proxy/session contracts | authorization-approval-proxy.test.cjs invokes actual handler/session modules with synthetic encrypted cookies and injected API responses; fresh same USER/session, fixed routes, current actor-bound receipt, read-only recovery and backend-error redaction | Node tests, not browser cookie negotiation or real HTTPS/OIDC/API topology |
| Backend authorization/service contracts | test_authorization_approval.py and test_authorization_approval_receipt.py cover creator denial, current identity/scope/session, exact replay, trusted creator, historical receipt and middleware | Test identities/data, not configured real people or selected issuer |
| PostgreSQL concurrency/atomicity | test_authorization_approval_postgres.py covers same-key races, different-body conflict, approval/revocation ordering, current security revocation, append-only audit and cross-target keys; entire CI PG report has296 cases/no skips | Separate backend tests, not one browser-to-database approval session |
| Full Next authenticated chain | Existing code and contracts supply individual pieces | No browser proof joining trusted HTTPS, encrypted session, OIDC, proxy, authenticated FastAPI and real people; topology/session establishment remain separately designed |
| Company operations | No new evidence in this package | Actual target, roles/provider, data and operational acceptance remain outstanding |

Sources: [B2 original matrix](browser-authorization-b2-design.md),
[component spec](../frontend/component-browser/authorization-approval.spec.ts),
[harness](../frontend/component-browser/harness.cjs),
[proxy tests](../frontend/tests/authorization-approval-proxy.test.cjs),
[service tests](../backend/tests/test_authorization_approval.py),
[receipt tests](../backend/tests/test_authorization_approval_receipt.py),
[PG tests](../backend/tests/test_authorization_approval_postgres.py).

B2-C's five component requirements are met at their stated layer. This does not
close the original two-person authenticated browser flow. B3 has same-origin
reload/manual import/query and invalid-envelope rejection, not all interruption
behaviors. B4-A covers six representative rendered errors, not actual cookie
expiry, exhaustive roles or cross-project browser enforcement. A context404 is
unavailable, not proof of foreign-project denial. Recovery502 is the real proxy's
redaction of non200 backend receipt results, not a direct browser403/404 claim.
Layered successes must not be joined into a fictional end-to-end login session.

Consequently browser-stage remains1/4, finite-plan8/8, business36/44=82%, delta0.
Modules100/100demo/100demo/100/89/60/17 and plans100/100/20/33/40/40/0 are unchanged.
No denominator, completion criterion or original scope is reduced to raise progress.

## Next concrete candidate: two B3 interruption/retry cases

These two cases are proposed, not implemented or executed by this document.
Use the same component spec/harness and fixed synthetic endpoints. No production
code, new dependency, server route, workflow or security configuration is needed
by the proposed scope; if inspection finds otherwise, stop and review that change.

1. **Cancel an unknown-state reload.** Prepare/confirm, send once and receive the
   existing unknown response. Save exact rendered command/export and request
   bytes. Initiate same-origin reload; assert the actual beforeunload dialog and
   dismiss it. Assert the original document marker, URL, unknown phase, full
   command/request ID/digest/reason and recovery text remain unchanged, with no
   extra context/approval/receipt request. A rejected navigation promise alone
   is not proof of retained state. This tests cancelling navigation, not cancelling
   a backend business operation. Existing accepted-reload recovery stays intact.
2. **Explicit unknown-result retry preserves original bytes.** Prepare/confirm,
   send once and return unknown. Observe no automatic retry/query. Reset the synthetic hold/release promise for a genuinely held second
   response, explicitly double-click Retry original authorization approval and
   require exactly one additional approval POST byte-identical to the first.
   Assert sending phase, absent send/retry controls during the in-flight request
   and unchanged review; release one valid
   original receipt, then assert exact receipt/historical warning and confirmed
   state, with no receipt lookup or third approval request. This checks component
   behavior, not real backend idempotency; existing backend concurrency evidence
   remains separate.

Keep every current14 component and8 Next journey, fixed signed browser,
sandbox=true, retries=0, exact-title reports and aggregate gates. A future
implementation would require16 component titles, individual missing-case/legacy14
negative report contracts, local contracts/typecheck/discovery, independent review,
then exact-head browser/full CI and separately verified merged-main/provider.
Back/forward, cross-tab coordination, full HTTPS authentication and real actors
remain outside these two cases. This design does not authorize upload or those
broader changes.

## This document package's validation

Local validation passed:81 targeted workbench/transport/recovery/proxy/harness/
report contracts,126 browser guard contracts,52 automation contracts, progress
consistency, relative links and whitespace checks. Programmatic comparison
confirmed every earlier checkpoint and all non-maintenance JSON groups unchanged.
Independent read-only review passed with no blocking findings. It checked
layer claims against source, historical/JSON preservation and feasibility of the
two proposed cases; external CI/provider facts above are the verified baseline
record, not a second independent network verification.
The baseline CI above is completed historical evidence, not CI for this new
unpublished document candidate. No new browser run, backend/PG suite or production
build is claimed for this document-only package.
