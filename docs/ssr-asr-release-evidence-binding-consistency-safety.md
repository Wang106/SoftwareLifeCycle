# SSR/ASR release-evidence binding consistency safety

## Scope

The SSR/ASR release detail evidence summary and the synthetic `/demo/releases`
page share one runtime parser. This package makes that parser reject responses
whose binding flags contradict the evidence objects they describe.

The change is read-only. It does not alter the backend projection, database,
approval or decision workflow, identity, credentials, command gates, CI, or
deployment configuration.

## Contract

An evidence response is structurally valid only when all asserted binding
relationships can exist:

- `approval.current_snapshot_bound: true` requires a current Snapshot.
- `decision.current_evidence_bound: true` requires a current Snapshot and an
  Approval that is itself marked as bound to that Snapshot.
- A Decision marked as bound must carry the exact current Snapshot `id` in its
  `snapshot_id` field.

False binding flags remain valid evidence. They continue to show an unconfirmed
release and preserve reviewable records. The parser does not infer a binding or
change a false value to true.

If an asserted binding violates these relationships, the complete response
fails closed. A release detail renders the existing evidence-summary unavailable
state; the demonstration renders the existing evidence-API unavailable state.
Neither page displays the contradictory Approval or Decision as bound, and
neither confirms a formal release.

## Verification

Regression coverage exercises the shared parser through both server-rendered
surfaces. It rejects:

1. a bound Approval without a current Snapshot;
2. a bound Decision whose Approval is not bound; and
3. a bound Decision whose `snapshot_id` differs from the current Snapshot.

The normal exact Snapshot/Readiness/Approval/Decision chain and deliberately
unbound evidence remain covered by the existing suites.

## Safety boundary

This validation establishes consistency inside one API response. It does not
attest that the underlying records are genuine, that an approver has a real
identity or authority, or that a release is formally published. Public and demo
environments remain read-only; OIDC, real business writes, internal deployment,
and production configuration remain outside this package.
