import { preparePrincipalStatus, confirmPrincipalStatus, exportPrincipalStatus,
  type PrincipalReview, type PrincipalStatus } from './principal-status-draft';

export type PrincipalStatusCommand = Readonly<{ principal_id: string; event_no: string;
  expected_status: PrincipalStatus; status: PrincipalStatus; reason: string }>;
// Browser input never selects an API URL, actor, credential or observed protection flag.
export function parsePrincipalStatusCommand(value: unknown): PrincipalStatusCommand | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const d = value as Record<string, unknown>;
  const fields = ['principal_id', 'event_no', 'expected_status', 'status', 'reason'];
  if (Object.keys(d).length !== fields.length || !fields.every(key => Object.prototype.hasOwnProperty.call(d, key)) ||
      typeof d.principal_id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(d.principal_id) ||
      typeof d.event_no !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$/.test(d.event_no) ||
      !['ACTIVE', 'DISABLED'].includes(d.expected_status as string) ||
      !['ACTIVE', 'DISABLED'].includes(d.status as string) || d.expected_status === d.status ||
      typeof d.reason !== 'string' || Array.from(d.reason.trim()).length < 5 ||
      Array.from(d.reason.trim()).length > 500 || /[\u0000-\u001f\u007f]/.test(d.reason)) return null;
  return Object.freeze({ principal_id: d.principal_id.toLowerCase(), event_no: d.event_no,
    expected_status: d.expected_status as PrincipalStatus, status: d.status as PrincipalStatus, reason: d.reason.trim() });
}
export type PrincipalStatusReceipt = Readonly<{ principal_id: string; audit_event_no: string;
  applied_status: PrincipalStatus; current_status: PrincipalStatus; replayed: boolean; revoked_browser_sessions: number }>;
export function projectPrincipalStatusReceipt(value: unknown, command: PrincipalStatusCommand,
  upstream = false): PrincipalStatusReceipt | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const d = value as Record<string, unknown>;
  const identifier = upstream && typeof d.principal_id === 'string' ? d.principal_id.toLowerCase() : d.principal_id;
  if (identifier !== command.principal_id || d.audit_event_no !== command.event_no ||
      d.applied_status !== command.status || !['ACTIVE', 'DISABLED'].includes(d.current_status as string) ||
      typeof d.replayed !== 'boolean' || !Number.isSafeInteger(d.revoked_browser_sessions) ||
      (d.revoked_browser_sessions as number) < 0 || (command.status === 'ACTIVE' && d.revoked_browser_sessions !== 0)) return null;
  return Object.freeze({ principal_id: command.principal_id, audit_event_no: command.event_no,
    applied_status: command.status, current_status: d.current_status as PrincipalStatus,
    replayed: d.replayed, revoked_browser_sessions: d.revoked_browser_sessions as number });
}
export type PrincipalSubmissionError = 'principal_submission_disabled' | 'cross_origin_request' | 'read_only_mode' |
  'submission_forbidden' | 'session_required' | 'principal_not_found' | 'invalid_request' | 'request_too_large' |
  'json_required' | 'audit_event_conflict' | 'principal_status_conflict' | 'admin_principal_protected' |
  'submission_conflict' | 'outcome_unknown';
const denials: Readonly<Record<number, readonly PrincipalSubmissionError[]>> = Object.freeze({
  400: ['invalid_request'], 401: ['session_required'],
  403: ['cross_origin_request', 'read_only_mode', 'submission_forbidden'], 404: ['principal_not_found'],
  409: ['audit_event_conflict', 'principal_status_conflict', 'admin_principal_protected', 'submission_conflict'],
  413: ['request_too_large'], 415: ['json_required'], 422: ['invalid_request'], 503: ['principal_submission_disabled'],
});
export type PrincipalSubmissionState = Readonly<{ phase: 'idle' | 'sending' | 'unknown' | 'rejected' | 'confirmed';
  review: PrincipalReview; error: PrincipalSubmissionError | null; receipt: PrincipalStatusReceipt | null }>;
async function readResponse(response: Response): Promise<unknown> {
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' ||
      Number(response.headers.get('content-length') || '0') > 16384) {
    await response.body?.cancel(); throw Error('invalid_receipt');
  }
  const reader = response.body?.getReader(); if (!reader) throw Error('missing_receipt');
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const part = await reader.read(); if (part.done) break;
      size += part.value.length;
      if (size > 16384) { await reader.cancel(); throw Error('oversized_receipt'); }
      chunks.push(part.value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}

/** Memory-only original command. No automatic retry, credential or persistent storage. */
export class PrincipalSubmission {
  private current: PrincipalSubmissionState;
  private uncertain = false;
  private readonly command: PrincipalStatusCommand;
  private readonly body: string;
  constructor(review: PrincipalReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact identity and status change before sending.');
    exportPrincipalStatus(review);
    const canonical = confirmPrincipalStatus(preparePrincipalStatus(review.target,
      review.request.body.event_no, review.request.body.reason), true);
    if (JSON.stringify(canonical.request) !== JSON.stringify(review.request)) throw Error('invalid_review');
    const command = parsePrincipalStatusCommand({ principal_id: canonical.target.id, ...canonical.request.body });
    if (!command) throw Error('invalid_review');
    this.command = command; this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase: 'idle', review: canonical, error: null, receipt: null });
  }
  get state(): PrincipalSubmissionState { return this.current; }
  private update(phase: PrincipalSubmissionState['phase'], error: PrincipalSubmissionError | null,
    receipt: PrincipalStatusReceipt | null = null) {
    this.current = Object.freeze({ phase, review: this.current.review, error, receipt }); return this.current;
  }
  async send(enabled: boolean, fetcher: typeof fetch = fetch): Promise<PrincipalSubmissionState> {
    if (this.current.phase === 'sending' || this.current.phase === 'confirmed') return this.current;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected', 'principal_submission_disabled');
    this.update('sending', null);
    try {
      const response = await fetcher('/auth/principal-status', { method: 'POST', body: this.body,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(15000) });
      const value = await readResponse(response);
      const receipt = response.status === 200 ? projectPrincipalStatusReceipt(value, this.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed', null, receipt); }
      const error = value && typeof value === 'object' ? (value as Record<string, unknown>).error : null;
      if (typeof error === 'string' && denials[response.status]?.includes(error as PrincipalSubmissionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected', error as PrincipalSubmissionError);
    } catch { /* A lost or invalid response cannot prove whether the backend committed. */ }
    this.uncertain = true;
    return this.update('unknown', 'outcome_unknown');
  }
}
export const principalSubmissionMessages: Record<PrincipalSubmissionError, string> = {
  principal_submission_disabled: 'Identity status submission is disabled in this environment.',
  cross_origin_request: 'The request origin was rejected.',
  read_only_mode: 'This environment is read-only.',
  submission_forbidden: 'Administrator permission is required for this operation.',
  session_required: 'Sign in again before retrying the original request.',
  principal_not_found: 'The exact identity was not found.',
  invalid_request: 'The submitted request was rejected as invalid.',
  request_too_large: 'The submitted request is too large.',
  json_required: 'The server requires a JSON request.',
  audit_event_conflict: 'The audit number conflicts with an existing operation.',
  principal_status_conflict: 'The identity status changed. Review current detail and history.',
  admin_principal_protected: 'Protected administrator identities require the separate recovery procedure.',
  submission_conflict: 'The server reported a submission conflict.',
  outcome_unknown: 'The outcome is unknown. Keep the original audit number and exact request.',
};
