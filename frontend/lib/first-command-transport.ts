import { blankFields, prepare, confirm, type Review } from './command-draft';

export type FirstOperation = 'snapshot' | 'actual' | 'batch';
export type FirstCommand = Readonly<{ operation: FirstOperation; target: string;
  body: Readonly<Record<string, string | number | null>> }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
export function exactFields(value: Record<string, unknown>, names: readonly string[]): boolean {
  return Object.keys(value).length === names.length && names.every(key => Object.prototype.hasOwnProperty.call(value, key));
}
export function commandReview(command: FirstCommand): Review {
  const b = command.body;
  return confirm(prepare(command.operation, { ...blankFields, target: command.target,
    release: typeof b.actual_release_id === 'string' ? b.actual_release_id : '',
    snapshot: typeof b.actual_snapshot_id === 'string' ? b.actual_snapshot_id : '',
    version: typeof b.expected_version === 'number' ? String(b.expected_version) : '',
    reason: typeof b.correction_reason === 'string' ? b.correction_reason : '',
    timestamp: typeof b.deployed_at === 'string' ? b.deployed_at : typeof b.started_at === 'string' ? b.started_at : '',
    batch: typeof b.batch_no === 'string' ? b.batch_no : '',
    changeover: typeof b.changeover_id === 'string' ? b.changeover_id : '',
    note: typeof b.note === 'string' ? b.note : '' }, b.request_id as string), true);
}
/** Exact three-operation input. No caller-selected URL, path, actor or credential. */
export function parseFirstCommand(value: unknown): FirstCommand | null {
  const d = record(value), b = record(d?.body);
  if (!d || !b || !exactFields(d, ['operation', 'target', 'body']) ||
      !['snapshot', 'actual', 'batch'].includes(d.operation as string) || typeof d.target !== 'string' ||
      typeof b.request_id !== 'string' || !uuid.test(b.request_id)) return null;
  const operation = d.operation as FirstOperation;
  const fields = operation === 'snapshot' ? ['request_id'] : operation === 'actual' ?
    ['request_id', 'actual_release_id', 'actual_snapshot_id', 'expected_version', 'correction_reason', 'deployed_at'] :
    ['request_id', 'batch_no', 'changeover_id', 'started_at', 'note'];
  if (!exactFields(b, fields)) return null;
  if (operation === 'actual' && (typeof b.actual_release_id !== 'string' || !uuid.test(b.actual_release_id) ||
      typeof b.actual_snapshot_id !== 'string' || !uuid.test(b.actual_snapshot_id) ||
      !Number.isSafeInteger(b.expected_version) || (b.expected_version as number) < 0 ||
      (b.expected_version as number) > 2147483646 || typeof b.correction_reason !== 'string' ||
      !(b.deployed_at === null || typeof b.deployed_at === 'string'))) return null;
  if (operation === 'batch' && (typeof b.batch_no !== 'string' ||
      !(b.changeover_id === null || (typeof b.changeover_id === 'string' && uuid.test(b.changeover_id))) ||
      !(b.started_at === null || typeof b.started_at === 'string') ||
      !(b.note === null || (typeof b.note === 'string' && b.note !== '')))) return null;
  try {
    const candidate = { operation, target: d.target, body: b } as FirstCommand;
    const review = commandReview(candidate);
    const target = operation === 'snapshot' ? d.target.trim().toLowerCase() : d.target.trim();
    return Object.freeze({ operation, target, body: review.draft.payload as FirstCommand['body'] });
  } catch { return null; }
}
export function firstCommandPath(command: FirstCommand): string { return commandReview(command).draft.path; }
export function firstCommandEvent(command: FirstCommand): string {
  return 'EVT-' + ({ snapshot: 'SN', actual: 'DA', batch: 'PB' }[command.operation]) + '-' +
    (command.body.request_id as string).replaceAll('-', '');
}
export type FirstReceipt = Readonly<{ operation: FirstOperation; request_id: string; target: string;
  audit_event_no: string; result: Readonly<Record<string, string | number>> }>;
/** Browser accepts only the server's actor-bound atomic-audit projection. */
export function projectFirstReceipt(value: unknown, command: FirstCommand): FirstReceipt | null {
  const d = record(value), r = record(d?.result), key = command.body.request_id as string;
  if (!d || !r || d.operation !== command.operation || d.request_id !== key || d.target !== command.target ||
      d.audit_event_no !== firstCommandEvent(command)) return null;
  let result: Record<string, string | number>;
  if (command.operation === 'snapshot') {
    if (r.id !== key || r.release_id !== command.target || r.status !== 'FROZEN' ||
        typeof r.snapshot_no !== 'string' || !/^SNAP-[0-9]{4,}-[0-9a-f]{8}$/.test(r.snapshot_no) ||
        !Number.isSafeInteger(r.snapshot_number) || (r.snapshot_number as number) < 1 ||
        (r.snapshot_number as number) > 2147483647 ||
        typeof r.content_hash !== 'string' || !/^[0-9a-f]{64}$/.test(r.content_hash) ||
        r.snapshot_no !== 'SNAP-' + String(r.snapshot_number).padStart(4, '0') + '-' + command.target.slice(0, 8)) return null;
    result = { id: key, release_id: command.target, snapshot_no: r.snapshot_no, status: 'FROZEN',
      snapshot_number: r.snapshot_number as number, content_hash: r.content_hash };
  } else if (command.operation === 'actual') {
    if (typeof r.id !== 'string' || !uuid.test(r.id) || r.id !== r.id.toLowerCase() ||
        r.deployment_no !== command.target || !['MATCH', 'MISMATCH'].includes(r.status as string) ||
        r.actual_release_id !== command.body.actual_release_id || r.actual_snapshot_id !== command.body.actual_snapshot_id ||
        r.actual_version !== (command.body.expected_version as number) + 1) return null;
    result = { id: r.id, deployment_no: command.target, status: r.status as string,
      actual_release_id: r.actual_release_id as string, actual_snapshot_id: r.actual_snapshot_id as string,
      actual_version: r.actual_version as number };
  } else {
    if (r.id !== key || r.batch_no !== command.body.batch_no || r.deployment_no !== command.target || r.status !== 'ACTIVE' ||
        !['release_id', 'snapshot_id'].every(k => typeof r[k] === 'string' && uuid.test(r[k] as string) && r[k] === (r[k] as string).toLowerCase())) return null;
    result = { id: key, batch_no: r.batch_no as string, deployment_no: command.target, status: 'ACTIVE',
      release_id: r.release_id as string, snapshot_id: r.snapshot_id as string };
  }
  return Object.freeze({ operation: command.operation, request_id: key, target: command.target,
    audit_event_no: firstCommandEvent(command), result: Object.freeze(result) });
}
export type FirstError = 'first_submission_disabled' | 'cross_origin_request' | 'json_required' | 'request_too_large' |
  'invalid_request' | 'session_required' | 'read_only_mode' | 'submission_forbidden' | 'request_conflict' |
  'version_conflict' | 'submission_conflict' | 'outcome_unknown';
const denials: Readonly<Record<number, readonly FirstError[]>> = {
  400: ['invalid_request'], 401: ['session_required'], 403: ['cross_origin_request', 'read_only_mode', 'submission_forbidden'],
  409: ['request_conflict', 'version_conflict', 'submission_conflict'], 413: ['request_too_large'],
  415: ['json_required'], 422: ['invalid_request'], 503: ['first_submission_disabled'],
};
export type FirstState = Readonly<{ phase: 'idle' | 'sending' | 'checking' | 'unknown' | 'rejected' | 'confirmed';
  review: Review; command: FirstCommand; error: FirstError | null; receipt: FirstReceipt | null }>;
async function readResponse(response: Response): Promise<unknown> {
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' ||
      Number(response.headers.get('content-length') || '0') > 16384) {
    await response.body?.cancel(); throw Error('invalid_response');
  }
  const reader = response.body?.getReader(); if (!reader) throw Error('missing_response');
  const chunks: Uint8Array[] = []; let size = 0;
  try { for (;;) {
    const part = await reader.read(); if (part.done) break;
    size += part.value.length; if (size > 16384) { await reader.cancel(); throw Error('oversized_response'); }
    chunks.push(part.value);
  } } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
/** Memory-only frozen original request. Recovery reads its audit; it never repeats the write. */
export class FirstSubmission {
  private current: FirstState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const target = review.draft.operation === 'snapshot' ? review.draft.path.split('/')[4] :
      decodeURIComponent(review.draft.path.split('/')[4] || '');
    const command = parseFirstCommand({ operation: review.draft.operation, target, body: review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = commandReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit ||
        JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase: 'idle', review: canonical, command, error: null, receipt: null });
  }
  get state(): FirstState { return this.current; }
  private update(phase: FirstState['phase'], error: FirstError | null, receipt: FirstReceipt | null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled: boolean, fetcher: typeof fetch = fetch): Promise<FirstState> { return this.run('submit', enabled, fetcher); }
  recover(enabled: boolean, fetcher: typeof fetch = fetch): Promise<FirstState> { return this.run('recover', enabled, fetcher); }
  private async run(mode: 'submit' | 'recover', enabled: boolean, fetcher: typeof fetch): Promise<FirstState> {
    if (['sending', 'checking', 'confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected', 'first_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking', null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/first-command' : '/auth/first-command-receipt', {
        method: 'POST', body: this.body, headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(15000) });
      const value = await readResponse(response);
      const receipt = response.status === 200 ? projectFirstReceipt(value, this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed', null, receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as FirstError))
        return this.update(this.uncertain ? 'unknown' : 'rejected', error as FirstError);
    } catch { /* Neither a lost response nor a missing audit proves that the write did not commit. */ }
    this.uncertain = true; return this.update('unknown', 'outcome_unknown');
  }
}
