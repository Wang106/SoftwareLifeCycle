/** Request preparation only. This module has no transport or persistence. */
export type Operation = 'snapshot' | 'actual' | 'batch' | 'approval' | 'decision' | 'impact' | 'acceptance' | 'resource';
export type Fields = {
  target: string; release: string; snapshot: string; version: string;
  reason: string; timestamp: string; batch: string; changeover: string; note: string;
  step: string; actor: string; action: string; decisionNo: string; readiness: string; decision: string;
  criterion: string; dvp: string; evidence: string; entityType: string; title: string; locationKind: string; location: string; description: string;
};
export type Draft = Readonly<{
  operation: Operation; path: string; payload: Readonly<Record<string, string | number | null>>;
  trace: string; audit: string;
}>;
export type Review = Readonly<{ draft: Draft; confirmed: boolean }>;
export const blankFields: Fields = {
  target: '', release: '', snapshot: '', version: '', reason: '', timestamp: '',
  batch: '', changeover: '', note: '', step: '', actor: '', action: '',
  decisionNo: '', readiness: '', decision: '', criterion: '', dvp: '', evidence: '',
  entityType: '', title: '', locationKind: '', location: '', description: '',
};
export const resourceTypes = ['SUPPLIER','CUSTOMER','PROJECT','RELEASE','SNAPSHOT','SCR','ISSUE','DVP_ITEM','TEST_RELEASE','DVP_EXECUTION'];
export const locationKinds = ['WEB_URL','LOCAL_PATH','NETWORK_PATH'];
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function validUuid(value: string): boolean { return uuidPattern.test(value); }
function uuid(value: string, label: string): string {
  const result = value.trim();
  if (!validUuid(result)) throw new Error(`${label} must be a UUID.`);
  return result.toLowerCase();
}
function identifier(value: string, label: string, max: number): string {
  const result = value.trim();
  if (!result || result.length > max || result === "." || result === ".."
      || /[\/\\\u0000-\u001f\u007f]/.test(result)) {
    throw new Error(`${label} must contain 1–${max} characters without path separators, dot segments or control characters.`);
  }
  return result;
}
function declaredText(value: string, label: string, max: number): string {
  if (!value.trim() || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error(`${label} must contain 1–${max} characters without control characters.`);
  }
  return value; // Actor/readiness/decision declarations retain exact API semantics.
}
function cleanText(value: string, label: string, max: number, required = true, controls = false): string {
  const text = value.trim();
  if (value.length > max || (required && !text) || (controls && /[\u0000-\u001f\u007f]/.test(text))) {
    throw new Error(`${label} must ${required ? 'contain nonblank text and ' : ''}use at most ${max} characters${controls ? ' without control characters' : ''}.`);
  }
  return text;
}
function resourceLocation(kind: string, raw: string): string {
  const value = cleanText(raw, 'Location', 4000, true, true);
  if (kind === 'WEB_URL') {
    // Stricter preparation subset: explicit HTTP(S) authority, no normalization/fetch.
    if (!/^https?:\/\/[^/?#]/.test(value) || /[\s\\]/.test(value)) throw new Error('Use an HTTP(S) URL without spaces or backslashes.');
    try {
      const url = new URL(value);
      if (!url.hostname || url.username || url.password || value.slice(value.indexOf('://') + 3).split(/[/?#]/, 1)[0].includes('@')
          || /[\u0000-\u001f\u007f]/.test(decodeURIComponent(value))) throw new Error('unsafe URL');
    } catch { throw new Error('Use a valid HTTP(S) URL without credentials, invalid ports or encoded controls.'); }
  } else if (kind === 'LOCAL_PATH') {
    if (!((value.startsWith('/') && !value.startsWith('//')) || /^[A-Za-z]:[\\/]/.test(value))) {
      throw new Error('Local path must be absolute POSIX or Windows drive path.');
    }
  } else if (kind === 'NETWORK_PATH') {
    if (!/^(?:\\\\|\/\/)[^\\/]+[\\/][^\\/]+/.test(value)) throw new Error('Network path must include a server and share.');
  } else { throw new Error('Select an explicit location kind.'); }
  return value;
}
function timestamp(value: string): string | null {
  if (!value.trim()) return null;
  const text = value.trim();
  // Explicit zone avoids interpreting a local browser time as UTC.
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/.exec(text);
  if (!match) throw new Error('Time must be ISO 8601 with seconds and an explicit timezone.');
  const [, year, month, day, hour, minute, second, , zone] = match;
  const days = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
  if (Number(year) < 100 || Number(month) < 1 || Number(month) > 12 || Number(day) < 1
      || Number(day) > days || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59
      || (zone !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59))) {
    throw new Error('Time is not a valid calendar date/time.');
  }
  const parsed = new Date(text);
  if (!Number.isFinite(parsed.getTime())) throw new Error('Time is outside the supported range.');
  return parsed.toISOString();
}
export function prepare(operation: Operation, fields: Fields, requestId: string): Review {
  const key = uuid(requestId, 'Request ID');
  let path: string, trace: string, audit: string;
  const payload: Record<string, string | number | null> = { request_id: key };
  if (operation === 'snapshot') {
    const target = uuid(fields.target, 'Release');
    path = `/api/v1/releases/${target}/create-snapshot`;
    trace = `/releases/${target}/snapshots`;
    audit = `/activity/EVT-SN-${key.replaceAll("-", "")}`;
  } else if (operation === 'impact' || operation === 'acceptance' || operation === 'resource') {
    payload.actor_name = cleanText(fields.actor, 'Declared operator', 120);
    payload.reason = cleanText(fields.reason, 'Reason', 4000, true, operation === 'resource');
    if (operation === 'impact') {
      const issue = identifier(fields.target, 'Issue number', 50);
      payload.release_id = uuid(fields.release, 'Release');
      payload.snapshot_id = uuid(fields.snapshot, 'Snapshot');
      if (!['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'].includes(fields.decision)) throw new Error('Select an explicit impact judgment.');
      payload.decision = fields.decision;
      payload.evidence_ref = cleanText(fields.evidence, 'Evidence reference', 2000, false) || null;
      path = `/api/v1/issues/${encodeURIComponent(issue)}/impact-assessments`;
      trace = `/issues/${encodeURIComponent(issue)}`;
      audit = `/activity/EVT-IMPACT-${key}`;
    } else if (operation === 'acceptance') {
      const request = identifier(fields.target, 'SCR number', 50);
      payload.criterion_id = uuid(fields.criterion, 'Acceptance criterion');
      payload.dvp_item_id = uuid(fields.dvp, 'DVP item');
      path = `/api/v1/changes/${encodeURIComponent(request)}/acceptance-dvp-links`;
      trace = `/changes/${encodeURIComponent(request)}/coverage`;
      audit = `/activity/EVT-AC-${key}`;
    } else {
      if (!resourceTypes.includes(fields.entityType)) throw new Error('Select an explicit resource object type.');
      payload.entity_type = fields.entityType;
      payload.entity_id = uuid(fields.target, 'Resource object');
      payload.actor_name = cleanText(fields.actor, 'Declared operator', 120, true, true);
      payload.title = cleanText(fields.title, 'Title', 240, true, true);
      payload.location_kind = fields.locationKind;
      payload.location = resourceLocation(fields.locationKind, fields.location);
      payload.description = cleanText(fields.description, 'Description', 4000, false, true);
      path = '/api/v1/resources'; trace = `/resources/${key}`;
      audit = `/activity/EVT-LK-${key}`;
    }
  } else if (operation === 'approval' || operation === 'decision') {
    const target = identifier(fields.target, 'Approval number', 50);
    const encoded = encodeURIComponent(target);
    path = `/api/v1/approvals/${encoded}/${operation === 'approval' ? 'actions' : 'release-decision'}`;
    trace = `/approvals/${encoded}`;
    audit = `/activity/${operation === 'approval' ? 'EVT-AP-' : 'EVT-RD-'}${key.replaceAll('-', '')}`;
    const actor = declaredText(fields.actor, 'Declared operator', 120);
    if (operation === 'approval') {
      if (!['APPROVED', 'RETURNED', 'REJECTED'].includes(fields.action)) {
        throw new Error('Select an explicit approval action.');
      }
      payload.expected_step_id = uuid(fields.step, 'Expected approval step');
      payload.actor = actor;
      payload.action = fields.action;
      payload.comment = fields.note || null;
    } else {
      payload.decision_no = identifier(fields.decisionNo, 'Decision number', 50);
      payload.decided_by = actor;
      payload.readiness_status = declaredText(fields.readiness, 'Recorded readiness status', 30);
      payload.decision = declaredText(fields.decision, 'Decision', 30);
      payload.notes = fields.note || null;
      trace = `/release-decisions/${encodeURIComponent(payload.decision_no)}`;
    }
  } else {
    const target = identifier(fields.target, 'Deployment number', 50);
    const encoded = encodeURIComponent(target);
    path = `/api/v1/deployments/${encoded}/${operation === 'actual' ? 'actual' : 'batches'}`;
    trace = `/deployments/${encoded}`;
    audit = `/activity/${operation === "actual" ? "EVT-DA-" : "EVT-PB-"}${key.replaceAll("-", "")}`;
    if (operation === 'actual') {
      if (!/^(0|[1-9]\d*)$/.test(fields.version) || !Number.isSafeInteger(Number(fields.version))) {
        throw new Error('Expected version must be a non-negative integer read from deployment detail.');
      }
      if (!fields.reason.trim() || fields.reason.length > 2000) {
        // Require a reason even for an initial report, so version-zero legacy corrections are safe.
        throw new Error('Report / correction reason must contain 1–2000 characters.');
      }
      payload.actual_release_id = uuid(fields.release, 'Actual release');
      payload.actual_snapshot_id = uuid(fields.snapshot, 'Actual snapshot');
      payload.expected_version = Number(fields.version);
      payload.correction_reason = fields.reason;
      payload.deployed_at = timestamp(fields.timestamp);
    } else if (operation === 'batch') {
      payload.batch_no = identifier(fields.batch, 'Batch number', 80);
      payload.changeover_id = fields.changeover.trim() ? uuid(fields.changeover, 'Changeover') : null;
      payload.started_at = timestamp(fields.timestamp);
      payload.note = fields.note || null;
      trace = `/production/batches/${encodeURIComponent(payload.batch_no)}`;
    } else { throw new Error('Unsupported operation.'); }
  }
  return Object.freeze({ draft: Object.freeze({ operation, path, trace, audit,
    payload: Object.freeze(payload) }), confirmed: false });
}
export function confirm(review: Review, checked: boolean): Review {
  return Object.freeze({ ...review, confirmed: checked });
}
export function exportRequest(review: Review): string {
  if (!review.confirmed) throw new Error('Confirm the reviewed target and content before copying.');
  return JSON.stringify({ method: 'POST', path: review.draft.path, body: review.draft.payload }, null, 2);
}
