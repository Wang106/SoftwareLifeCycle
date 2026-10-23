# SSR/ASR release evidence invariant safety

This package hardens the existing read-only SSR/ASR release evidence views. A backend `current_release_confirmed` value is necessary but is not sufficient for the UI to state that formal release evidence matches the current Snapshot.

The shared frontend projection confirms release only when every recorded invariant is simultaneously true:

- the response release type exactly matches the SSR (`STANDARD`) or ASR (`APPLICATION`) route;
- the selected Snapshot is `FROZEN`;
- current Readiness is `READY`, approval-eligible, and based on the current Snapshot;
- the Approval is `APPROVED` and bound to the current Snapshot;
- the effective Release Decision is `RELEASE`, records `READY`, and is bound to current evidence;
- the decision's recorded Snapshot UUID equals the displayed Snapshot UUID; and
- the API confirmation flag is true.

An SSR/ASR route-type mismatch makes the evidence summary unavailable. Any other contradiction keeps the recorded evidence visible for review but renders “formal release not confirmed” with a bilingual contract-mismatch warning. A false API confirmation is never upgraded by the frontend.

The same helper protects `/demo/releases` and the SSR/ASR detail summaries. It adds no request, retry, write, identity, credential, backend, database, migration, Seed, dependency, CI, scheduler or deployment behavior.

Verification for the implementation checkpoint:

- focused evidence tests: 16 passed;
- complete frontend suite: 1553 passed, 0 failed, 0 skipped;
- TypeScript `--noEmit`: passed;
- Next.js 16.4.2 production build: passed.

These checks validate client-side interpretation only. They do not establish real-world approval authority, identity, physical software installation, production release, browser/device acceptance, or company-network deployment.
