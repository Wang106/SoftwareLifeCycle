# B3 isolated manual audit recovery tests

## Scope and current state

This local candidate starts from main
`69d63e4987994981b2cad3b7daa973008ecd4e9e` (PR176). It implements only the
[bounded B3 design](browser-authorization-b3-recovery-design.md): same-origin
reload, manual audit-only recovery import, explicit original receipt lookup,
and wrong-origin/wrong-target rejection. Back/forward, cancellation, cross-tab
coordination, full permission matrices and actual authentication remain separate.

Three new fixed journeys extend the existing five component journeys to eight.
The original eight Next journeys are preserved. The strict component report
requires the exact eight titles and files, one passed attempt each, component-only
annotations, no skip, failure, retry, duplicate or missing case. Existing runner,
workflow, fixed signed browser and sandbox settings are unchanged.

The actual workbench runs in the existing loopback-only synthetic harness. No
real session, backend, database, clipboard permission or business write is used.
Recovery text is read from its displayed field, not the clipboard. An imported
envelope is unverified audit context, never authorization or execution proof.
Receipt-proxy POST is a read-only audit lookup, not a new approval command.

## Acceptance matrix

- Unknown command recovery: one explicit original approval request, preserve its
  complete serialized request bytes and displayed recovery envelope, and verify
  original target, request ID, digest, reason and scope.
- Same-origin reload: retain the fixture's origin and port; transient command and
  receipt state disappear, with no automatic API request.
- Explicit manual import: imported context is visibly unverified/audit-only;
  there is no approval send/retry capability and import makes no API request.
- Explicit receipt lookup: exactly one receipt-proxy POST using the original
  request bytes, no new context or approval request, all ten receipt fields match,
  and the historical-only disclaimer remains visible.
- Wrong origin: mutate only pasted envelope text; do not navigate or send to a
  foreign origin. Import visibly fails with zero API requests.
- Wrong target: preserve envelope structure and mutate its target; import visibly
  fails with zero API requests.

Local checks passed: 2101 frontend tests with zero failures/skips, 80 targeted
report/harness/recovery/workbench/transport/proxy contracts, 126 CI guard and
52 automation contracts, project and explicit ES2022 spec typechecking, and
discovery of exactly eight component plus eight Next journeys. Progress, exact
checkpoint-history preservation, unchanged business groups, relative links and
whitespace checks passed. Independent read-only review found no blocker and separately passed 55 targeted
contracts, typechecking and eight-case component discovery.
No new B3 browser scenario has executed: the configured verified Chrome candidate
is absent locally. No alternate browser was downloaded or substituted. Node contracts, typechecking
and discovery do not substitute for actual exact-head browser CI and strict
reports. Publication, eventual merge and main/provider checks require their own
verified evidence; the baseline results below are not this package's results.

## Verified baseline, separate from this package

[Main CI41927836403](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41927836403)
passed at the baseline SHA: frontend2098, backend2846 plus26 subtests,
PostgreSQL296 without skips, 126 browser guard contracts and migration0029
SQL/PostgreSQL round trip. Original Next8 and component5 passed with
Chrome157.0.8103.39, sandbox=true and retries=0. Jobs: frontend126916818139,
backend126916818056, browser126916817739, aggregate126923763057. Browser artifacts
are13370522240 and13370497253 respectively, subject to retention.

Cloudflare check126918012558 succeeded: production build
`0e22a61c-00b5-4540-87bb-89882eb9637d`, version
`14207e78-747c-4004-995f-31275c20b104`. Actions deployment41929901553 skipped.
Provider success is not proof of live database/business health.

PR176's description predates its diagnostic/pin additions. Use its actual final
diff and exact-head CI rather than that older description for the final scope.

## Progress boundaries

Business acceptance remains36/44=82%, increment0. Seven modules remain
100/100demo/100demo/100/89/60/17; seven plans100/100/20/33/40/40/0. Browser stage
remains conservatively1/4 until cross-layer acceptance is separately reconciled.
This small B3 subset does not close all B3 or establish real identities and
FastAPI authorization. Public sample-only/read-only mode, disabled real identity
and business writes, and the decision not to rebuild the expired database remain.
No company-server deployment or new paid resources are part of this package.
