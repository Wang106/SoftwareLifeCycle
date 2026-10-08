import { prepareGrantStatus, confirmGrantStatus, exportGrantStatus, type GrantReview, type GrantStatus } from './grant-status-draft';

export type GrantReceipt = Readonly<{ grant_id: string; scope: string; audit_event_no: string;
  applied_status: GrantStatus; current_status: GrantStatus; replayed: boolean }>;
export type SubmissionError = 'grant_submission_disabled' | 'cross_origin_request' | 'read_only_mode' |
  'submission_forbidden' | 'session_required' | 'grant_not_found' | 'invalid_request' | 'request_too_large' |
  'json_required' | 'audit_event_conflict' | 'membership_status_conflict' | 'global_role_status_conflict' |
  'recipient_inactive' | 'recipient_issuer_mismatch' | 'last_active_admin_protected' | 'submission_conflict' | 'outcome_unknown';
export type SubmissionState = Readonly<{ phase: 'idle' | 'sending' | 'unknown' | 'rejected' | 'confirmed';
  review: GrantReview; error: SubmissionError | null; receipt: GrantReceipt | null }>;
const denied: Record<number, readonly SubmissionError[]> = {
  400: ['invalid_request'], 401: ['session_required'],
  403: ['cross_origin_request', 'read_only_mode', 'submission_forbidden'],
  404: ['grant_not_found'], 409: ['audit_event_conflict', 'membership_status_conflict',
    'global_role_status_conflict', 'recipient_inactive', 'recipient_issuer_mismatch',
    'last_active_admin_protected', 'submission_conflict'],
  413: ['request_too_large'], 415: ['json_required'], 422: ['invalid_request'],
  503: ['grant_submission_disabled'],
};
async function readReceipt(response: Response): Promise<unknown> {
  if (!response.headers.get('content-type')?.includes('application/json') ||
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
function projectReceipt(value: unknown, review: GrantReview): GrantReceipt | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (data.grant_id !== review.target.id || data.scope !== review.target.scope ||
      data.audit_event_no !== review.request.body.event_no || data.applied_status !== review.request.body.status ||
      !['ACTIVE', 'SUSPENDED'].includes(data.current_status as string) || typeof data.replayed !== 'boolean') return null;
  return Object.freeze({ grant_id: review.target.id, scope: review.target.scope,
    audit_event_no: review.request.body.event_no, applied_status: data.applied_status as GrantStatus,
    current_status: data.current_status as GrantStatus, replayed: data.replayed });
}

/** Memory-only reviewed command. Never automatically retry or persist credentials/data. */
export class GrantSubmission {
  private current: SubmissionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: GrantReview) {
    exportGrantStatus(review); // Explicit confirmation is required before any transport.
    const canonical = confirmGrantStatus(prepareGrantStatus(review.target,
      review.request.body.event_no, review.request.body.reason), true);
    if (JSON.stringify(canonical.request) !== JSON.stringify(review.request)) throw Error('invalid_review');
    this.current = Object.freeze({ phase: 'idle', review: canonical, error: null, receipt: null });
    this.body = JSON.stringify({ scope: canonical.target.scope, grant_id: canonical.target.id,
      ...canonical.request.body });
  }
  get state(): SubmissionState { return this.current; }
  private update(phase: SubmissionState['phase'], error: SubmissionError | null, receipt: GrantReceipt | null = null) {
    this.current = Object.freeze({ phase, review: this.current.review, error, receipt }); return this.current;
  }
  async send(enabled: boolean, fetcher: typeof fetch = fetch): Promise<SubmissionState> {
    // Set the lock synchronously, before yielding; double clicks cannot race React rendering.
    if (this.current.phase === 'sending' || this.current.phase === 'confirmed') return this.current;
    if (!enabled) return this.update(this.uncertain ? 'unknown' : 'rejected', 'grant_submission_disabled');
    this.update('sending', null);
    try {
      const response = await fetcher('/auth/grant-status', { method: 'POST', body: this.body,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(15000) });
      const value = await readReceipt(response);
      const receipt = response.status === 200 ? projectReceipt(value, this.current.review) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed', null, receipt); }
      const error = value && typeof value === 'object' ? (value as Record<string, unknown>).error : null;
      if (typeof error === 'string' && denied[response.status]?.includes(error as SubmissionError))
        return this.update(this.uncertain ? 'unknown' : 'rejected', error as SubmissionError);
    } catch { /* A lost response cannot establish whether the backend committed. */ }
    this.uncertain = true;
    return this.update('unknown', 'outcome_unknown');
  }
}

export const submissionMessages: Record<SubmissionError, string> = {
  grant_submission_disabled: 'Grant submission is disabled in this environment.',
  cross_origin_request: 'The request origin was rejected.',
  read_only_mode: 'This environment is read-only.',
  submission_forbidden: 'Administrator permission is required for this operation.',
  session_required: 'Sign in again before retrying the original request.',
  grant_not_found: 'The exact grant was not found.',
  invalid_request: 'The submitted request was rejected as invalid.',
  request_too_large: 'The submitted request is too large.',
  json_required: 'The server requires a JSON request.',
  audit_event_conflict: 'The audit number conflicts with an existing operation.',
  membership_status_conflict: 'The membership status changed. Review current detail and history.',
  global_role_status_conflict: 'The global role status changed. Review current detail and history.',
  recipient_inactive: 'The recipient is inactive.',
  recipient_issuer_mismatch: 'The recipient belongs to a different identity issuer.',
  last_active_admin_protected: 'The last active administrator cannot be suspended.',
  submission_conflict: 'The server reported a submission conflict.',
  outcome_unknown: 'The outcome is unknown. Keep the original audit number and exact request.',
};
