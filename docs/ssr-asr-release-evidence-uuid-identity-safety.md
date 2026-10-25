# SSR/ASR release evidence UUID identity safety

## Scope

The shared SSR/ASR evidence parser consumes read-only API data before it creates links to releases, Snapshots, and DVP items. Those identities are UUID database keys. A merely non-empty string is therefore not sufficient evidence for a route or a binding claim.

The parser now requires the canonical lowercase hyphenated UUID representation for:

- the summary release ID and every demonstration release ID;
- the current Snapshot ID;
- the Readiness coverage Snapshot ID when present;
- the Release Decision Snapshot ID;
- every demonstration DVP item ID.

Any malformed, uppercase, compact, or otherwise non-canonical identity rejects the complete summary or demonstration response. The existing unavailable state is shown, no route is generated from the invalid value, and no formal release is inferred.

## Preserved behavior

- Snapshot numbers, approval numbers, decision numbers, change request numbers, and DVP item numbers remain their existing bounded business identifiers rather than UUIDs.
- A missing current Snapshot still uses the existing `null` representation, including the existing Readiness consistency checks.
- UUID version bits are not restricted; the parser validates canonical representation and leaves UUID generation policy to the backend.
- Existing count, hash, text, rule identity, binding, initialization, cross-row identity, and release-confirmation checks remain unchanged.

## Safety boundary

This is client-side validation of bounded read-only responses. It does not prove database authenticity, identity authority, approval authority, deployment, or production release. Public and demonstration environments remain read-only.

## Verification

`frontend/tests/release-evidence-summary.test.cjs` and `frontend/tests/release-demo-evidence.test.cjs` use canonical UUID fixtures and cover malformed release, Snapshot, Readiness, Decision, and DVP identities. Each malformed response must fail closed without rendering evidence or a formal-release confirmation.
