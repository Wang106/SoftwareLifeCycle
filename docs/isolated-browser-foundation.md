# Isolated real-browser foundation (B1)

## B1 closure and subsequent UI insertion (2026-10-29)

B1 is technically closed at protected main `1be2baf41ba88afe172efb5a33ed81e6e17cd551`: main CI40876032522 and Cloudflare production buildc7779ef5 succeeded; stage1/4. Render's earlier99de backend remained live and unchanged; current runtime is not accepted from that fact. The owner's separate [priority-page-loading](priority-page-loading.md) request adds four loading/navigation/layout browser cases to the original two, so current feature report acceptance requires six exact title/file pairs. The original two-case evidence below remains historical B1 evidence, not acceptance of the new UI feature. No B2 work, runner/security/workflow or dependency change is included.

## What this package proves — and does not prove

This is the first package of the [four-package browser stage](browser-validation-stage-plan.md), based on main `ad9147366f00c68bf3f20a93e62e185eea773dc9`. It exercises actual Chromium, React hydration, Next production HTML/JavaScript, DOM links/buttons, locale persistence and native retry navigation. A real loopback HTTP fixture supplies only synthetic Batch/detail/history responses; it is **not** FastAPI, PostgreSQL, real identities or actual authorization acceptance. No production fixture/auth bypass route is added.

The two browser scenarios cover one bounded read-only business journey: navigate from Batch detail to recorded/effective correction history, preserve distinct raw notes with fixed release/snapshot, switch Chinese/English and reload, inspect the disabled correction controls; then inject a synthetic history503, verify no substitute evidence, explicitly retry and verify a fresh HTTP GET restores the expected history. This does not exercise business submission, physical flashing, production recovery or a real user's permissions. Those boundaries remain in the later stage plan.

## Reproducible execution

From `frontend`, with Node22 and the checked-in lockfile:

```sh
npm ci
npm run test:browser:fixture
# Use the approved runner's existing official Google Chrome stable installation.
# Current CI uses standard macos-26 ARM64 and verifies the existing Chrome
# bundle/signature/ownership/modes/version read-only (see the adjustment below).
# Missing or untrusted installation is a blocker; do not install or change security settings.
npm run build
npm run test:browser
```

`@playwright/test` is pinned exactly to1.62.0; its lockfile pins Playwright, not the runner's preinstalled Chrome version. The configured `chrome` channel uses the preinstalled official bundle at `/Applications/Google Chrome.app` on the approved macOS runner; CI records the actual browser and runner image versions. No browser or system-library installation is performed by this job. This is not an instruction to install anything on a company server or personal computer. No paid API or plan upgrade is required or performed. Missing browser/runtime/quota is a blocker, not permission to change security settings or billing.

The current Work cloud's standard sandbox-enabled Chromium launch was denied by its socket policy. It is not retried or bypassed. Local fixture tests, typecheck, discovery and builds are separate from actual browser acceptance. The newly approved GitHub Actions `browser` job is the executable target; a failing/blocked launch fails that job and the existing aggregate acceptance check. Never add `--no-sandbox`, disable setuid sandbox, alter host sysctls, skip the browser on error, or substitute SSR/string assertions for its result.

## Isolation and evidence

- A fresh Next process listens on127.0.0.1 with a new temporary port. Its environment is allowlisted; all checked-in browser mode gates are disabled, public API fallbacks blank, and no inherited tokens/cookies/provider configuration/NODE_OPTIONS are forwarded.
- The separate loopback API implements exact anonymous GET paths only. Unexpected/private paths, writes and credential headers are rejected and counted as violations. Fixture fault switching is in-process test control, not an application HTTP endpoint.
- Browser contexts block service workers/downloads and all other origins/methods/WebSockets. Exact synthetic app responses remain real Next responses; redirects are rejected before following them. Explicit Next speculative prefetch requests are suppressed so unrelated sidebar catalogs are outside this slice, and this exclusion is not reported as prefetch coverage. This route mediation makes no streaming latency assertion.
- Chromium sandbox is explicitly enabled, retries are zero, exclusive tests forbidden. Missing/empty/failed/skipped/flaky/retried report cases fail the report checker; the two named journeys must actually pass.
- `browser-results/` contains the JSON report and successful synthetic history screenshots and failure screenshots/traces/logs. The existing pinned artifact action retains evidence14days. These artifacts contain only synthetic local fixture values; do not run this harness against real data, identity providers or public/company URLs. Process cleanup is bounded to the test-owned child/API, no arbitrary process termination.

## CI integration boundaries

The user explicitly approved the isolated browser CI job and necessary dependencies. Existing backend/real PostgreSQL/migration and frontend/Cloudflare steps and check names remain intact. The existing `CI acceptance` retains both original success assertions and additionally requires the browser job. There are no new workflow events/schedules, repository permissions, secrets, branch protection changes, live deployment commands or notification destinations. A separate browser build avoids reusing ambiguous production artifacts; exact PR and fresh-main results must be verified separately.

No roadmap or progress milestone is raised merely for writing the harness. PackageB1 remains pending until real browser execution and the whole protected PR/main verification succeeds; the overall36/44=82% and seven-plan denominators remain unchanged. AfterB1 closure, coordinate B2 before adding another flow.

## Historical Ubuntu runner compatibility adjustment

The first PR execution failed before either browser case could start: downloaded Chromium headless shell could not obtain a sandbox on the Ubuntu24.04 runner. The failure is retained, not retried with weaker flags. At that checkpoint, after explicit owner approval, the job used Playwright's supported `chrome` channel with `chromiumSandbox: true`, zero retries and the same two original journeys/assertions. That historical Ubuntu guard checked the existing official package ownership/version, original binary and root-owned non-writable `/etc/apparmor.d/chrome`, plus AppArmor enabled state, read-only. No downloaded binary is copied into an allowlisted path; no executable-path override, profile load/change, sysctl, SUID setup or fallback is used. These presence checks do not prove effective policy or sandbox operation: missing evidence or actual launch failure still fails the job and acceptance.

References: [Playwright stable channels](https://playwright.dev/docs/browsers#google-chrome--microsoft-edge), [Chromium's existing Chrome profile explanation](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md), [actual failed runner image manifest](https://github.com/actions/runner-images/blob/ubuntu24/20261012.334/images/ubuntu/Ubuntu2404-Readme.md).

## Approved macOS runner adjustment (2026-10-29)

The Ubuntu guard rejected the installed Chrome binary's mode 0777 before launch. The owner approved moving only the browser job to standard `macos-26` ARM64 with the preinstalled Chrome channel. No browser is installed and no permission or system-security setting is changed. The read-only guard now checks macOS/ARM64, the fixed Chrome bundle/executable, bundle-member ownership and modes, contained framework symlinks, Google Developer ID chain/team `EQHXZ8M8AV` and `com.google.Chrome` identifier with deep strict codesign validation, and bundle/binary version equality. Root or current ephemeral-runner ownership accounts for the official image's Homebrew cask installation; group/world-writable members are rejected.

SIP and Gatekeeper are recorded read-only, including command exit status. Hosted-runner settings can differ from an ordinary Mac. Signature/file checks do not establish runtime sandbox effectiveness or production security acceptance. The original sandbox-enabled, zero-retry journeys and all acceptance gates remain mandatory; verification or launch failure stops the job without a weaker fallback. The implementation-head CI evidence below is now verified; later documentation-head and fresh-main results remain separate, not inferred from the manifest or local syntax tests. Standard public-runner minutes do not authorize any paid upgrade or artifact-quota overage.

Sources: [GitHub runner labels](https://github.com/actions/runner-images#available-images), [official Chrome installation script](https://github.com/actions/runner-images/blob/main/images/macos/scripts/build/install-chrome.sh), [Apple requirement verification](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements), [Chromium Google Developer ID requirement](https://chromium.googlesource.com/chromium/src/+/3b731edeef246408d7cf9c0a3247e08c9f9b3e10).

## Verified implementation-head evidence (2026-10-29)

Implementation head `6da7ec0f12bc1841c4dbdbf0de391f177550ded5` passed [CI run 40868393983](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/40868393983), which tested merge ref `75eee958bbb4b7e70369ff24769858b4f78f28aa` against main `ad9147366f00c68bf3f20a93e62e185eea773dc9`. All four workflow jobs succeeded: backend/PostgreSQL/migrations (2846 tests + 26 subtests, 296 PostgreSQL-module cases), frontend/Cloudflare build (2024 tests), isolated browser (2 tests), and aggregate acceptance. No test skips/failures; browser retries zero. The two named journeys actually ran, and the downloaded report independently passed the checked-in report validator.

- Actual runner: macOS 26.6.2 ARM64, image `macos-26-arm64` version `20261013.0424.1`; Chrome `155.0.8059.40`. Deep strict Google signature and the 734-member bundle guard passed; recorded owner IDs were 0 and 501. `chromiumSandbox: true`. SIP reported disabled; Gatekeeper reported assessments enabled. No setting was changed, and this evidence is not a production security certification.
- [Browser artifact 12894009958](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/40868393983/artifacts/12894009958), SHA256 `20b0cadd21137b8adbbb5cda07bfada60c30e8b78c825c3be94cd693a882bcb7`: downloaded digest verified; contains `results.json` and `runner-browser.txt`. The two successful synthetic PNG screenshots are embedded as base64 attachments in the JSON. Stats: expected 2, skipped 0, unexpected 0, flaky 0, errors empty; each result passed once with retry 0.
- [Backend artifact 12895502196](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/40868393983/artifacts/12895502196), SHA256 `cab45262fe9cd89aab9b21b03f17b350b8dc20d860805ea0b342536ece9783fa`: downloaded digest verified; JUnit failures/errors/skips zero, suite count 2872 includes 26 subtests. Migration head `0029_changeover_batch_history` and PostgreSQL round trip passed. Artifact retention remains 14 days; links are not permanent storage.
- Exact-head Cloudflare Workers Builds check succeeded, build `3452b36a-39e7-4f71-9707-50085e7e6b8b`. This proves the PR preview build, not live runtime, Render, or fresh-main deployment.

This later docs-only reconciliation does not claim its own future head CI. Verify the final exact head, protected merge, then fresh main CI and each provider separately without recursively committing CI-only refreshes. At this checkpoint PR #170 is draft/unmerged, current main is unchanged, and B1 remains 0/4 pending protected closure. Actual FastAPI/identity/company acceptance remains outside this synthetic browser slice. Historical failed Ubuntu runs above are retained, not relabeled as successes.
