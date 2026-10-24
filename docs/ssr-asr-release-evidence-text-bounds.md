# SSR/ASR release evidence text bounds

The shared read-only release-evidence parser feeds server rendering for both exact SSR/ASR release summaries and the demonstration release page. Runtime shape validation already rejected missing fields and oversized arrays, but it previously accepted arbitrarily long non-empty strings. A malformed upstream response could therefore amplify server-rendered HTML or generate excessively long release, Snapshot, approval, decision, change-request and DVP links.

This package aligns displayed text with the existing backend field contracts:

- release and Snapshot identities are limited to 64 characters; release versions to 100;
- release types to 20 characters and recorded states to 30;
- Snapshot numbers to 80 characters and content hashes to 128;
- approval, decision, change-request and DVP numbers to their stored 50-character limit;
- Readiness rule groups to 100 characters, rule labels to 240, evidence to 500 and effective states to 30; and
- initialized lists remain limited to 200 release rows, Readiness rules and DVP references.

If any required string exceeds its bound, the complete corresponding response fails closed through the existing unavailable state. The UI does not truncate and present ambiguous evidence, render a partial chain, invent an SSR/ASR route, or convert approval records into formal-release authority. Valid responses retain their exact text.

The package changes no API response, backend, database, migration, Seed, dependency, identity, credential, write gate, CI, scheduler or deployment setting. Public and demonstration routes remain read-only.

Local verification for implementation checkpoint `04ccca5a5ed38dc104de127b51d3ad2633eecb6b`:

- focused SSR/ASR release-evidence tests: 18 passed;
- complete frontend suite: 1555 passed, 0 failed, 0 skipped;
- TypeScript `--noEmit`: passed;
- Next.js 16.4.2 production build: passed; and
- Worker configuration check: passed.

The first complete-suite attempt occurred before the new worktree dependency tree was prepared and failed only with missing-module errors. Reusing the lockfile-identical dependency tree produced the passing result above without changing package or lock files. These checks establish defensive SSR parsing only; they do not establish approval authority, real identity, physical installation, formal release, browser/device acceptance or company-network deployment.
