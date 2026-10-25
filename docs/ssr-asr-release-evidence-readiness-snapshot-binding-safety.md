# SSR/ASR release-evidence Readiness Snapshot binding safety

## Scope

The SSR/ASR release detail evidence summary and synthetic `/demo/releases` page
share one runtime parser. This package makes the parser verify that the Snapshot
identity embedded in Readiness coverage is the same Snapshot projected at the
top level of the response.

The change is read-only. It does not alter the backend projection, database,
Snapshot selection, approval or decision workflow, identity, command gates, CI,
or deployment configuration.

## Contract

When a response contains a current Snapshot:

- `readiness.coverage.snapshot_id` must equal the top-level `snapshot.id`; and
- `readiness.coverage.snapshot_no` must equal the top-level `snapshot.snapshot_no`.

When the top-level Snapshot is absent, both Readiness identity fields must be
`null` and `readiness.coverage.snapshot_match` must be `false`.

The parser does not repair, copy, normalize, or select between conflicting
values. A contradiction makes the complete affected response unavailable. The
release detail uses its existing evidence-summary unavailable state and the
demonstration uses its existing evidence-API unavailable state. Neither surface
renders the conflicting chain or confirms a formal release.

`snapshot_match: false` remains valid when a current Snapshot exists. It records
that executions belong to another Snapshot and continues to produce an
unconfirmed, reviewable response.

## Verification

Regression coverage exercises the shared parser through both server-rendered
surfaces. It rejects:

1. a Readiness `snapshot_id` that differs from the projected Snapshot;
2. a Readiness `snapshot_no` that differs from the projected Snapshot; and
3. a missing projected Snapshot whose Readiness still claims a Snapshot match.

Existing positive and deliberately unconfirmed evidence chains remain covered.

## Safety boundary

This validation establishes consistency inside one API response. It does not
attest that the underlying Snapshot or evidence records are genuine, that an
approver has a real identity or authority, or that a release is formally
published. Public and demo environments remain read-only; OIDC, real business
writes, internal deployment, and production configuration remain outside this
package.
