# SSR/ASR release evidence response-shape safety

This package hardens the two existing read-only release evidence consumers against malformed runtime responses. TypeScript response annotations are not runtime validation, so an incomplete upstream object must not throw during server rendering or be partially trusted as release proof.

The shared parser accepts only complete bounded shapes for:

- release identity and record status;
- Snapshot identity, number, state and content hash, or an explicit `null`;
- Readiness state, approval eligibility, safe non-negative coverage counts, Snapshot match and at most 200 complete rules;
- Approval state and current-Snapshot binding, or an explicit `null`;
- Release Decision state, recorded Readiness, Snapshot identity and current-evidence binding, or an explicit `null`;
- the strict boolean API confirmation flag; and
- for the demonstration list, the change request and at most 200 complete DVP references.

An initialized response with any missing or malformed field fails closed as unavailable. The UI does not render a partial record, follow invented links, retry with an unbounded endpoint, or turn a string-like truthy value into confirmation. A valid explicitly uninitialized sample response remains the separate “samples not installed” state.

The parser adds no network request, retry, write, identity, credential, backend, database, migration, Seed, dependency, CI, scheduler or deployment behavior. Public and demonstration paths remain read-only.

Local verification for the implementation checkpoint:

- focused SSR/ASR evidence tests: 18 passed;
- complete frontend suite: 1555 passed, 0 failed, 0 skipped;
- TypeScript `--noEmit`: passed;
- Next.js 16.4.2 production build: passed; and
- Worker configuration check: passed.

These checks establish defensive frontend parsing only. They do not establish approval authority, real identity, physical installation, formal release, browser/device acceptance or company-network deployment.
