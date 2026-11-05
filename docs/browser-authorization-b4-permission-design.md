# B3 evidence closeout and B4-A permission-boundary design

Date: 2026-11-05 (UTC+8). Baseline main
`818c25bf23a25852ba93af7428cfb3b93583cea2`. This package changes documentation
and evidence metadata only. The proposed B4 cases are not implemented or run.

## B3 bounded subset: verified, not full stage closure

PR177 final head `a018fbbf2d9cc0d1ec763fd0acd2fa43bd4572b7` passed
[CI41931853881](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41931853881)
and merged normally. Separate
[main CI41933756666](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41933756666)
succeeded: frontend2101, backend2846 plus26 subtests, PostgreSQL296 without skips,
126 browser guard contracts and migration0029 SQL/PostgreSQL round trip. Jobs:
frontend126936917074, backend126936916886, browser126936916426,
aggregate126941721875. Original Next8 and component8 actually passed their strict
reports with zero failures/skips/retries, Chrome157.0.8103.39 and sandbox=true.
[Next artifact13373850027](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41933756666/artifacts/13373850027)
and [component artifact13373740234](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41933756666/artifacts/13373740234)
are subject to retention.

The new three cases prove same-origin reload/manual audit-only import/explicit
original request lookup, foreign-origin rejection and valid wrong-target rejection
in the actual workbench with synthetic loopback responses. They do not complete
all B3 cancellation/back-navigation/cross-tab scenarios or real authentication.

Cloudflare check126937945635 succeeded: production build
`7cdbe4a1-878e-47cc-a0d0-3c1d90f405ff`, version
`cc15dc98-06ca-46f7-8581-eaad34251b69`. Actions deployment41935197399 and
continuation41935197373 skipped. These are not live database/business-health
acceptance. Prior PR177 local/unexecuted snapshots are historical; baseline
success is not this new document commit's CI.

## B4-A: six representative synthetic response cases

1. Context session unavailable: explicit context load returns 401/session_required.
   Assert the generic context-unavailable status, no private context/reason/review/
   confirmation/result, and exactly one context POST with the existing target.
   No approval or receipt request follows.
2. Context permission denied: explicit load returns 403/submission_forbidden.
   Require the same generic fail-closed UI and exact one-request evidence. Retain
   the existing creator-denial case; this fixture response alone does not identify
   a real role or establish why authorization was denied.
3. Context target unavailable: explicit load returns 404/target_not_found.
   Require the same generic UI and one context POST. Say target unavailable, not
   proven cross-project enforcement: missing and hidden targets are indistinguishable.
4. Permission lost after review: valid context, prepare/confirm, then one explicit
   first approval POST returns 403/submission_forbidden. Assert rejected phase,
   exact error code and rejection guidance, no receipt/audit link, no automatic
   lookup/retry, and unchanged command/request ID. Send/retry controls are absent;
   explicit query and reload controls remain available. Exactly context POST then
   approval POST with the frozen command bytes, no further requests.
5. Imported recovery session unavailable: import a valid same-origin/exact-target
   envelope without network; explicit audit lookup returns 401/session_required.
   Require exactly one receipt-proxy POST, unknown phase, exact error, unchanged
   scope/request/digest/reason and byte-identical command. No receipt, send/retry,
   context reload, preparation or reset control; explicit query stays available.
6. Imported original receipt unavailable: same import/query flow returns
   502/outcome_unknown. Preserve unknown rather than infer rejection or success,
   keep frozen bytes, no new business ID or automatic retry, and the same audit-only
   controls. This models the proxy's redacted result for failed backend receipt
   lookup, not a direct browser 403/404 claim.

Each case must assert no unexpected requests, page errors or server violations.
Do not infer actual cookie expiry, identity validity or backend scope enforcement
from these rendered fixture responses. No login or real actor is introduced.

## Actual layer mapping that the fixture must preserve

At this baseline, [browser-session.ts](../frontend/lib/browser-session.ts)
lines1073–1089 maps context failures to browser 401/session_required,
403/submission_forbidden,404/target_not_found. Lines1100–1117 enforce current
session/creator checks and map known initial-submission denials.

Receipt handling differs: lines1124–1128 collapses every non-200 backend receipt
GET into 502/outcome_unknown. The
[proxy contract](../frontend/tests/authorization-approval-proxy.test.cjs) explicitly
checks backend receipt401/403/404/409 all become502. A direct browser recovery401
is valid when current-session resolution fails before lookup (lines1100–1101);
a direct403 can arise from creator identity (line1102), not from backend scope
rejection. The transport defensively accepts other error shapes, but that does
not change the actual proxy mapping or justify false browser-layer claims.

[Workbench](../frontend/components/authorization-approval-workbench.tsx)
lines53–66 displays a generic context failure, not the individual context code.
Lines14–25 distinguish rejected/unknown and show result codes; lines133–146 govern
send/retry/query/reset. [Transport](../frontend/lib/authorization-approval-transport.ts)
lines78–94 preserves unknown after uncertain/recovery responses; only a first
known denial without uncertainty becomes rejected.
[Recovery](../frontend/lib/authorization-approval-recovery.ts) lines36–43 exposes
an audit-only facade without send. Imported data is not identity or success proof.

## Minimal future implementation and exit criteria

Extend only endpoint-specific response overrides in the existing
[component spec](../frontend/component-browser/authorization-approval.spec.ts),
reset every test. Preserve its fixed endpoints, exact-body/origin/credential
checks, held-response mechanism and defaults; reuse prepare/recoveryFixture.
No new page path, harness server handler, cookie, identity provider, application
feature flag, dependency, runner or workflow is required by this design.

Preserve all current8 component and original8 Next journeys. If these six cases
are implemented, the strict component title set and negative report contracts
must require14 cases, not merely a reported count. Original Next stays8. Keep
signed fixed browser, sandbox=true, retries=0 and all existing CI/aggregate gates.
Run local relevant contracts, typecheck and discovery, independent review, then
actual exact-head browser/full CI and strict reports. After protected merge,
verify main CI and provider separately. A discovery count is not execution.

B4-A is one bounded permission-error subset, not full B4 completion. Broader B2
real-session/actor boundaries, remaining B3 interruption cases and actual company
operations stay explicitly separate. Business36/44=82%, increment0, modules
100/100demo/100demo/100/89/60/17 and plans100/100/20/33/40/40/0 remain unchanged.
Browser stage stays conservatively1/4 pending a separately justified cross-layer
closeout. No company-server deployment, real identity/business writes, expired
public database rebuild, fees or relaxed security is authorized by this design.

## Local document-package checks

80 existing recovery/workbench/proxy/harness/report contracts,126 CI guards and52
automation contracts passed. Progress, exact historical-checkpoint preservation,
unchanged business groups, relative links and whitespace checks also passed.
Independent read-only review found no blocker and separately reran all80
targeted Node contracts successfully. No new B4 browser execution or full frontend/backend build
was run for this document-only package.
