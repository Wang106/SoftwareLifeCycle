/** Request preparation only. This module has no transport or persistence. */
export type Operation = 'snapshot' | 'actual' | 'batch';
export type Fields = {
  target: string; release: string; snapshot: string; version: string;
  reason: string; timestamp: string; batch: string; changeover: string; note: string;
};
export type Draft = Readonly<{
  operation: Operation; path: string; payload: Readonly<Record<string, string | number | null>>;
  trace: string; audit: string;
}>;
export type Review = Readonly<{ draft: Draft; confirmed: boolean }>;
export const blankFields: Fields = {
  target: '', release: '', snapshot: '', version: '', reason: '', timestamp: '',
  batch: '', changeover: '', note: '',
};
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
