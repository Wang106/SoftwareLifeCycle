export type ReleaseType = 'STANDARD' | 'APPLICATION';

export type ReleaseConfirmationInput = {
  releaseType: string;
  expectedReleaseType: ReleaseType | null;
  snapshot: { id: string; status: string } | null;
  readiness: {
    overall: string;
    approval_eligible: boolean;
    coverage: { snapshot_match: boolean };
  };
  approval: { status: string; current_snapshot_bound: boolean } | null;
  decision: {
    decision: string;
    readiness_status: string;
    snapshot_id: string;
    current_evidence_bound: boolean;
  } | null;
  currentReleaseConfirmed: boolean;
};

export function releaseConfirmationState(input: ReleaseConfirmationInput) {
  const evidenceConfirmsRelease = Boolean(
    input.expectedReleaseType
    && input.releaseType === input.expectedReleaseType
    && input.snapshot?.status === 'FROZEN'
    && input.readiness.overall === 'READY'
    && input.readiness.approval_eligible === true
    && input.readiness.coverage.snapshot_match === true
    && input.approval?.status === 'APPROVED'
    && input.approval.current_snapshot_bound === true
    && input.decision?.decision === 'RELEASE'
    && input.decision.readiness_status === 'READY'
    && input.decision.current_evidence_bound === true
    && input.decision.snapshot_id === input.snapshot.id
  );
  return {
    confirmed: input.currentReleaseConfirmed === true && evidenceConfirmsRelease,
    contractMismatch: input.currentReleaseConfirmed !== evidenceConfirmsRelease,
  };
}
