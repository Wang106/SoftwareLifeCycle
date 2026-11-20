# Isolated private-upload browser storage validation

This package adds four test-only journeys to ordinary CI. It does not enable
private upload or install a test authentication bypass. A separately confirmed
minimal production correction binds the upload controller's fetch function to
its global receiver; it changes no requests, locks, permissions or limits.
The existing signed macOS ARM64 Chrome preparation, sandbox and both16-case
suites remain required. The additional suite inherits their browser configuration,
zero retries and service-worker/download restrictions.

## Execution and evidence

Run in the existing verified CI browser environment:

```sh
cd frontend
node node_modules/@playwright/test/cli.js test --config=upload-browser/playwright.config.cjs
node scripts/check-upload-browser-report.cjs browser-results/upload/results.json
```

The harness compiles the real React picker, journal/controller and server relay
using locked dependencies. Playwright intercepts only exact approved paths at
`https://upload.example.test`; Node forwards them to the fixture's fixed
127.0.0.1 listeners. Every unexpected browser request/WebSocket or upstream target
fails. Synthetic encrypted session values are injected only into this harness;
no real identity provider, business upstream or production configuration is used.

1. The browser selects65539 deterministic binary bytes (`i %256`), confirms the
   exact target/digest/reason and sends once. The API double creates an exclusive
   mode0600 file in its owned mode0700 temporary directory, syncs and closes it.
   An independent read descriptor verifies actual length, SHA-256 and original
   request UUID before success evidence is accepted. The component UUID differs
   from its definition and SSR baseline UUIDs.
2. The relay completes normally, including its RESERVED/STORED_PRIVATE receipt
   checks. Only after the full success response and independent disk verification
   does the browser route deliberately abort delivery. Refresh performs no query
   or write. An explicit original receipt lookup recovers the same UUID and disk
   evidence. Reserve, content PUT and file write each remain exactly one.
3. Disabled picker renders no file input and makes no relay/API calls.
4. A trusted32-byte admission limit rejects selection before reservation/content
   transfer; no stored file or successful storage evidence exists.

Normal upstream identity/context/receipt counts are4/3/2. Explicit recovery adds
one identity and one receipt query, giving5/3/3. Browser relay counts remain
context/reserve/content/receipt=1/1/1/0, or1/1/1/1 after recovery. They are separate
from storage counts and are never interpreted as repeated content sends.

Per-test annotations contain only synthetic IDs, counts, digest/length and cleanup
status. Strict reporting requires all four unique successful cases, zero skips,
retries or errors, the exact disk evidence and closed listener/empty pending-set/
removed-directory cleanup. Failed initialization also closes acquired resources.
The build directory is owned and removed after the suite; failure blocks CI.
Temporary payload files are outside evidence artifact directories and are removed;
only existing synthetic CI evidence retention applies, with no new upload step.

## Validation layers and limits

`node --test tests/upload-browser-fixture.test.cjs tests/upload-browser-report.test.cjs`
checks real loopback/temporary-disk relay wiring and report rejection cases without
claiming browser execution. `npm test` includes these tests. Actual browser
acceptance requires the four-case report from the verified macOS CI environment.
Local Linux compilation and unit results do not substitute for that report.

The HTTPS origin is logical routing; these tests do not verify real TLS. The API
is a test double, not FastAPI, real OIDC, company storage or deployment. Private
storage success says nothing about scanning, distribution or business approval.
No creation-page copy changes, continuous multi-version uploads, download path,
production configuration, dependencies or permissions are included.

## Confirmed native fetch receiver correction

Initial head `37e7ce67146c309fb536522eb03b52690870bfe5`, run44687313896,
passed the original16+16 but only1/4 new cases. Context was never requested in
the enabled cases. Diagnostic head `e30d02b43de7902754509221850d385e84e35d2b`,
run44688798640/job136129380240, used signed Chrome158.0.8127.37 with sandbox
enabled and zero retries. Untouched native fetch with a pre-aborted signal
returned AbortError for Window, but TypeError / Illegal invocation for a
controller-shaped receiver. Neither diagnostic intentionally sends a request.

Only after that direct evidence, the controller constructor binds fetch to
globalThis. Two receiver-sensitive regressions failed before the correction
and cover context, reserve, content and original receipt recovery after both
normal and lost responses. The browser diagnostic remains native; no fixture
replacement fetch hides the defect. The new suite runs before the original
16+16 tail so the existing exact workflow contract is unchanged. A failed new
suite stops subsequent browser steps; skipped steps are never reported passed.
The corrected candidate still requires complete exact-head CI and actual
browser-to-disk success; diagnosis alone is not successful upload acceptance.
