export type ReleaseType = 'STANDARD' | 'APPLICATION';

export type ReleaseEvidenceSnapshot = {
  id: string;
  snapshot_no: string;
  status: string;
  content_hash: string;
};

export type ReleaseEvidenceReadiness = {
  overall: string;
  approval_eligible: boolean;
  coverage: {
    required_dvp_total: number;
    current_snapshot_executed: number;
    current_snapshot_passed: number;
    snapshot_match: boolean;
  };
  rules: { group: string; rule: string; evidence: string; effective: string }[];
};

export type ReleaseEvidenceApproval = {
  approval_no: string;
  status: string;
  current_snapshot_bound: boolean;
};

export type ReleaseEvidenceDecision = {
  decision_no: string;
  decision: string;
  readiness_status: string;
  snapshot_id: string;
  current_evidence_bound: boolean;
};

export type ReleaseEvidenceSummary = {
  release: { id: string; version: string; release_type: string; record_status: string };
  snapshot: ReleaseEvidenceSnapshot | null;
  readiness: ReleaseEvidenceReadiness;
  approval: ReleaseEvidenceApproval | null;
  decision: ReleaseEvidenceDecision | null;
  current_release_confirmed: boolean;
};

export type ReleaseEvidenceDemoRow = {
  release_id: string;
  version: string;
  release_type: string;
  record_status: string;
  snapshot: ReleaseEvidenceSnapshot | null;
  readiness: ReleaseEvidenceReadiness;
  approval: ReleaseEvidenceApproval | null;
  decision: ReleaseEvidenceDecision | null;
  current_release_confirmed: boolean;
  change_request_no: string;
  dvp_items: { id: string; item_no: string }[];
};

export type ReleaseEvidenceDemo = {
  sample_only: true;
  initialized: boolean;
  items: ReleaseEvidenceDemoRow[];
};

type JsonObject = Record<string, unknown>;

const object = (value: unknown): JsonObject | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : null;
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const boolean = (value: unknown): value is boolean => typeof value === 'boolean';
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0;

function parseSnapshot(value: unknown): ReleaseEvidenceSnapshot | null | undefined {
  if (value === null) return null;
  const row = object(value);
  return row && text(row.id) && text(row.snapshot_no) && text(row.status) && text(row.content_hash)
    ? {id: row.id, snapshot_no: row.snapshot_no, status: row.status, content_hash: row.content_hash}
    : undefined;
}

function parseReadiness(value: unknown): ReleaseEvidenceReadiness | null {
  const row = object(value), coverage = object(row?.coverage);
  if (!row || !coverage || !text(row.overall) || !boolean(row.approval_eligible)
      || !count(coverage.required_dvp_total) || !count(coverage.current_snapshot_executed)
      || !count(coverage.current_snapshot_passed) || !boolean(coverage.snapshot_match)
      || !Array.isArray(row.rules) || row.rules.length > 200) return null;
  const rules = row.rules.map(object);
  if (rules.some(rule => !rule || !text(rule.group) || !text(rule.rule) || !text(rule.evidence) || !text(rule.effective))) return null;
  return {
    overall: row.overall,
    approval_eligible: row.approval_eligible,
    coverage: {
      required_dvp_total: coverage.required_dvp_total,
      current_snapshot_executed: coverage.current_snapshot_executed,
      current_snapshot_passed: coverage.current_snapshot_passed,
      snapshot_match: coverage.snapshot_match,
    },
    rules: rules as ReleaseEvidenceReadiness['rules'],
  };
}

function parseApproval(value: unknown): ReleaseEvidenceApproval | null | undefined {
  if (value === null) return null;
  const row = object(value);
  return row && text(row.approval_no) && text(row.status) && boolean(row.current_snapshot_bound)
    ? {approval_no: row.approval_no, status: row.status, current_snapshot_bound: row.current_snapshot_bound}
    : undefined;
}

function parseDecision(value: unknown): ReleaseEvidenceDecision | null | undefined {
  if (value === null) return null;
  const row = object(value);
  return row && text(row.decision_no) && text(row.decision) && text(row.readiness_status)
    && text(row.snapshot_id) && boolean(row.current_evidence_bound)
    ? {decision_no: row.decision_no, decision: row.decision, readiness_status: row.readiness_status,
      snapshot_id: row.snapshot_id, current_evidence_bound: row.current_evidence_bound}
    : undefined;
}

function parseEvidenceCore(value: JsonObject) {
  const snapshot = parseSnapshot(value.snapshot), readiness = parseReadiness(value.readiness);
  const approval = parseApproval(value.approval), decision = parseDecision(value.decision);
  if (snapshot === undefined || !readiness || approval === undefined || decision === undefined
      || !boolean(value.current_release_confirmed)) return null;
  return {snapshot, readiness, approval, decision, current_release_confirmed: value.current_release_confirmed};
}

export function parseReleaseEvidenceSummary(value: unknown): ReleaseEvidenceSummary | null {
  const root = object(value), release = object(root?.release);
  if (!root || !release || !text(release.id) || !text(release.version) || !text(release.release_type)
      || !text(release.record_status)) return null;
  const core = parseEvidenceCore(root);
  return core ? {release: {id: release.id, version: release.version, release_type: release.release_type,
    record_status: release.record_status}, ...core} : null;
}

function parseDemoRow(value: unknown): ReleaseEvidenceDemoRow | null {
  const row = object(value);
  if (!row || !text(row.release_id) || !text(row.version) || !text(row.release_type)
      || !text(row.record_status) || !text(row.change_request_no) || !Array.isArray(row.dvp_items)
      || row.dvp_items.length > 200) return null;
  const items = row.dvp_items.map(object);
  if (items.some(item => !item || !text(item.id) || !text(item.item_no))) return null;
  const core = parseEvidenceCore(row);
  return core ? {release_id: row.release_id, version: row.version, release_type: row.release_type,
    record_status: row.record_status, change_request_no: row.change_request_no,
    dvp_items: items as ReleaseEvidenceDemoRow['dvp_items'], ...core} : null;
}

export function parseReleaseEvidenceDemo(value: unknown): ReleaseEvidenceDemo | null {
  const root = object(value);
  if (!root || root.sample_only !== true || !boolean(root.initialized) || !Array.isArray(root.items)
      || root.items.length > 200) return null;
  if (!root.initialized) return {sample_only: true, initialized: false, items: []};
  const items = root.items.map(parseDemoRow);
  return items.some(item => !item) ? null : {sample_only: true, initialized: true,
    items: items as ReleaseEvidenceDemoRow[]};
}

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
