# SSR/ASR demonstration release-evidence Snapshot status parity

The read-only SSR/ASR release-evidence parser requires every non-null Snapshot to carry its identity, number, recorded status and content hash. The exact release summary already supplied all four fields, but `/api/v1/demo/release-evidence` omitted `snapshot.status`. A valid backend demonstration response was therefore indistinguishable from a malformed response and `/demo/releases` had to fail closed.

This package restores the existing contract without weakening the parser:

- each non-null demonstration Snapshot now projects its stored `status`;
- backend tests require all seeded evidence Snapshots and the HTTP response to report `FROZEN`;
- the frontend regression explicitly proves that an absent Snapshot status still makes the initialized response unavailable; and
- no status is inferred from Readiness, approval, Release Decision, version, record status or the demonstration seed name.

The endpoint remains a bounded read-only sample projection. The change creates no approval, decision, Snapshot, deployment or business write and does not enable identity, credentials, OIDC, submission, CI, scheduler or provider configuration.

Local verification for the implementation checkpoint:

- focused SSR/ASR frontend evidence tests: 18 passed;
- complete frontend suite: 1555 passed, 0 failed, 0 skipped;
- Python source/test compilation: passed;
- TypeScript `--noEmit`: passed;
- Next.js 16.4.2 production build: passed; and
- Worker configuration check: passed.

The local Python environment did not contain pytest, so the backend test file was compiled but not executed locally. The PR's exact-head Backend/PostgreSQL CI must independently execute the full backend and real-PostgreSQL suites. These checks do not establish approval authority, formal release, browser/device acceptance, public performance or company-network deployment.
