# Isolated real-browser foundation (B1)

## What this package proves — and does not prove

This is the first package of the [four-package browser stage](browser-validation-stage-plan.md), based on main `ad9147366f00c68bf3f20a93e62e185eea773dc9`. It exercises actual Chromium, React hydration, Next production HTML/JavaScript, DOM links/buttons, locale persistence and native retry navigation. A real loopback HTTP fixture supplies only synthetic Batch/detail/history responses; it is **not** FastAPI, PostgreSQL, real identities or actual authorization acceptance. No production fixture/auth bypass route is added.

The two browser scenarios cover one bounded read-only business journey: navigate from Batch detail to recorded/effective correction history, preserve distinct raw notes with fixed release/snapshot, switch Chinese/English and reload, inspect the disabled correction controls; then inject a synthetic history503, verify no substitute evidence, explicitly retry and verify a fresh HTTP GET restores the expected history. This does not exercise business submission, physical flashing, production recovery or a real user's permissions. Those boundaries remain in the later stage plan.

## Reproducible execution

From `frontend`, with Node22 and the checked-in lockfile:

```sh
npm ci
npm run test:browser:fixture
# Use the approved runner's existing official Google Chrome stable installation.
# CI verifies its package, original binary and existing AppArmor profile read-only.
# Missing installation/policy is a blocker; do not install or change security settings.
npm run build
npm run test:browser
```

`@playwright/test` is pinned exactly to1.62.0; its lockfile pins Playwright, not the runner's preinstalled Chrome version. The configured `chrome` channel uses the original official package at `/opt/google/chrome/chrome`; CI records the actual package/browser and runner image versions. No browser or system-library installation is performed by this job. This is not an instruction to install anything on a company server or personal computer. No paid API or plan upgrade is required or performed. Missing browser/runtime/quota is a blocker, not permission to change security settings or billing.

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

## Approved runner compatibility adjustment

The first PR execution failed before either browser case could start: downloaded Chromium headless shell could not obtain a sandbox on the Ubuntu24.04 runner. The failure is retained, not retried with weaker flags. After explicit owner approval, the job uses Playwright's supported `chrome` channel with `chromiumSandbox: true`, zero retries and the same two original journeys/assertions. It checks the existing official package ownership/version, original binary and root-owned non-writable `/etc/apparmor.d/chrome`, plus AppArmor enabled state, read-only. No downloaded binary is copied into an allowlisted path; no executable-path override, profile load/change, sysctl, SUID setup or fallback is used. These presence checks do not prove effective policy or sandbox operation: missing evidence or actual launch failure still fails the job and acceptance.

References: [Playwright stable channels](https://playwright.dev/docs/browsers#google-chrome--microsoft-edge), [Chromium's existing Chrome profile explanation](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md), [actual failed runner image manifest](https://github.com/actions/runner-images/blob/ubuntu24/20261012.334/images/ubuntu/Ubuntu2404-Readme.md).
