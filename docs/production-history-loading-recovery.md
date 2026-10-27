# Production history loading and explicit read recovery

## Reproduced defect and bounded repair

On baseline main `478a4e9035ea292cfc38c5359860113d8f35e3f5`, Batch and Changeover
history pages awaited `apiGet` without a deadline and had no route loading boundary.
A controlled actual Next production server returned no status or bytes after the
read-only fixture API had withheld headers for1,500ms. Both pages completed only
when the fixture was released. Separate real-apiGet instrumentation confirmed no
deadline timer or abort signal for either stalled headers or a stalled JSON body.
This proves the local unbounded-wait path; it is not measured public-provider latency.

Both nested history routes now stream one bilingual accessible loading component.
The existing API helper receives its existing15-second deadline, covering headers
and body without changing the shared helper. Unavailable results keep their generic
truthful message: timeout,404,other HTTP failure,invalid JSON or mismatched projection
are not mislabeled as a known missing record. No history or current facts are invented.

A native anchor reloads the exact encoded current history route. It is deliberately
not a same-route Next Link that could reuse router state. This is an explicit new
GET only; there is no automatic retry, polling, private context request or business
write. Parent/child validation and public sample-only/read-only behavior are unchanged.
No controls, authentication, credentials, deployment settings, permissions or CI gates
are enabled or changed.

## Verification boundaries

New focused tests verify both route boundaries in Chinese/English, no loading-stage
API calls, exact15-second option, encoded native retry, no foreign-target disclosure
and no fabricated evidence. Existing API helper tests cover deadline cancellation,
body reads and late-response handling; existing history tests remain unchanged.

`node scripts/check-production-history-loading.cjs` after a production build runs
an isolated loopback read-only fixture and actual Next server. It verifies loading
arrives before releasing a held API response, header/body deadlines and upstream
cancellation, generic failure/mismatch handling, explicit subsequent GET recovery,
and both disabled workbenches without private context reads. It never uses real
identities, production data or public writes. All provider settings are omitted from
the subprocess environment.

The public deployment/history/control GET requests in this QA pass returned403.
No access restriction was bypassed or retried, and prior Chromium sandbox restrictions
were not bypassed. Consequently public visual/browser acceptance remains unverified.
Local production HTTP/SSR checks are not live Cloudflare/Render browser acceptance.
Current executor was recreated and prior local worktree was absent; latest committed
main was cloned into a new cloud workspace, without using the user's Mac or server.

This fixes a concrete read-navigation failure mode, not real-provider or company
acceptance. Completion remains36/44=82%; seven module/plan denominators unchanged.

Local final result:1,685 frontend tests passed with zero skips;172 focused history/i18n
cases and independent39 history/deadline cases passed. Typecheck,Worker configuration,
Next production build and52 automation checks passed. Actual Next runtime verification
passed28 observations with24 loopback history GETs and four disabled-workbench reads
that made zero private context calls. Header/body timeouts cancelled upstream requests;
subsequent explicit GETs recovered. Exact PR/main CI and provider evidence are tracked
in the final PR comment, separately from this local runtime evidence.
