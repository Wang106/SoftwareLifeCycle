import { prepareRegistration, confirmRegistration, exportRegistration, type RegistrationInput,
  type RegistrationReview, type RegistrationKind } from './admin-registration-draft';

// Browser envelope is the exact preparation input, never a caller-selected API path.
export function registrationInput(review: RegistrationReview): RegistrationInput {
  const b = review.request.body;
  const common = { kind: review.kind, newId: review.kind === 'PRINCIPAL' ? b.principal_id :
    review.kind === 'GLOBAL' ? b.grant_id : b.membership_id, eventNo: b.event_no, reason: b.reason };
  if (review.kind === 'PRINCIPAL') return { ...common, kind: 'PRINCIPAL',
    principalType: b.principal_type as 'USER' | 'SERVICE', subject: b.subject, displayName: b.display_name };
  if (review.kind === 'GLOBAL') return { ...common, kind: 'GLOBAL', principalId: b.principal_id, role: b.role };
  return { ...common, kind: review.kind, principalId: b.principal_id, scopeId: b.scope_id, role: b.role };
}
export type RegistrationReceipt = Readonly<{ kind: RegistrationKind; id: string; audit_event_no: string;
  applied_status: 'DISABLED' | 'SUSPENDED'; current_status: 'ACTIVE' | 'DISABLED' | 'SUSPENDED'; replayed: boolean;
  principal_id?: string; scope_id?: string; role?: string; revoked_browser_sessions?: number }>;

// Shared exact-target validator. Upstream extras (including subject and credentials)
// are projected away before the browser sees a response.
export function projectRegistrationReceipt(value: unknown, review: RegistrationReview,
  upstream = false): RegistrationReceipt | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const d = value as Record<string, unknown>, b = review.request.body, kind = review.kind;
  const expectedId = kind === 'PRINCIPAL' ? b.principal_id : kind === 'GLOBAL' ? b.grant_id : b.membership_id;
  const id = upstream ? d[kind === 'PRINCIPAL' ? 'principal_id' : kind === 'GLOBAL' ? 'grant_id' : 'membership_id'] : d.id;
  if (id !== expectedId || (!upstream && d.kind !== kind) || d.audit_event_no !== b.event_no ||
      d.applied_status !== review.initialStatus || typeof d.replayed !== 'boolean' ||
      !(kind === 'PRINCIPAL' ? ['ACTIVE','DISABLED'] : ['ACTIVE','SUSPENDED']).includes(d.current_status as string)) return null;
  const common = { kind, id: expectedId, audit_event_no: b.event_no, applied_status: review.initialStatus,
    current_status: d.current_status as RegistrationReceipt['current_status'], replayed: d.replayed };
  if (kind === 'PRINCIPAL') {
    // Registration never revokes sessions; principal-status commands are separate.
    if (d.revoked_browser_sessions !== 0) return null;
    return Object.freeze({ ...common, revoked_browser_sessions: 0 });
  }
  if ((upstream && d.scope !== kind) || d.principal_id !== b.principal_id || d.role !== b.role ||
      (kind !== 'GLOBAL' && d.scope_id !== b.scope_id)) return null;
  return Object.freeze({ ...common, principal_id: b.principal_id, role: b.role,
    ...(kind === 'GLOBAL' ? {} : { scope_id: b.scope_id }) });
}
export const registrationDenials: Readonly<Record<number, readonly string[]>> = Object.freeze({
  400: ['invalid_request'], 401: ['session_required'],
  403: ['cross_origin_request','read_only_mode','submission_forbidden'],
  404: ['registration_target_not_found'],
  409: ['audit_event_conflict','principal_registration_conflict','global_role_registration_conflict',
    'membership_registration_conflict','recipient_inactive','recipient_issuer_mismatch','admin_recipient_protected','submission_conflict'],
  413: ['request_too_large'], 415: ['json_required'], 422: ['invalid_request'],
  503: ['registration_submission_disabled','configured_issuer_required'],
});
export type RegistrationSubmissionState = Readonly<{ phase: 'idle' | 'sending' | 'unknown' | 'rejected' | 'confirmed';
  review: RegistrationReview; error: string | null; receipt: RegistrationReceipt | null }>;
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

/** Memory-only transport foundation; no automatic retries or persistence. */
export class RegistrationSubmission {
  private current: RegistrationSubmissionState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: RegistrationReview) {
    exportRegistration(review);
    const input = registrationInput(review), canonical = confirmRegistration(prepareRegistration(input), true);
    if (JSON.stringify(canonical.request) !== JSON.stringify(review.request) ||
        canonical.initialStatus !== review.initialStatus) throw Error('invalid_review');
    this.current = Object.freeze({ phase: 'idle', review: canonical, error: null, receipt: null });
    this.body = JSON.stringify(input);
  }
  get state(): RegistrationSubmissionState { return this.current; }
  private update(phase: RegistrationSubmissionState['phase'], error: string | null, receipt: RegistrationReceipt | null = null) {
    this.current = Object.freeze({ phase, review: this.current.review, error, receipt }); return this.current;
  }
  async send(enabled: boolean, fetcher: typeof fetch = fetch): Promise<RegistrationSubmissionState> {
    if (this.current.phase === 'sending' || this.current.phase === 'confirmed') return this.current;
    if (!enabled) return this.update(this.uncertain ? 'unknown' : 'rejected', 'registration_submission_disabled');
    this.update('sending', null);
    try {
      const response = await fetcher('/auth/admin-registration', { method: 'POST', body: this.body,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(15000) });
      const value = await readResponse(response);
      const receipt = response.status === 200 ? projectRegistrationReceipt(value, this.current.review) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed', null, receipt); }
      const error = value && typeof value === 'object' ? (value as Record<string, unknown>).error : null;
      if (typeof error === 'string' && registrationDenials[response.status]?.includes(error))
        return this.update(this.uncertain ? 'unknown' : 'rejected', error);
    } catch { /* A lost response cannot prove whether registration committed. */ }
    this.uncertain = true;
    return this.update('unknown', 'outcome_unknown');
  }
}

export const registrationMessages: Readonly<Record<string,string>> = Object.freeze({
  registration_submission_disabled: 'Registration submission is disabled in this environment.',
  cross_origin_request: 'The request origin was rejected.',
  read_only_mode: 'This environment is read-only.',
  submission_forbidden: 'Administrator permission is required for this operation.',
  session_required: 'Sign in again before retrying the original request.',
  registration_target_not_found: 'The exact registration recipient or target was not found.',
  invalid_request: 'The submitted request was rejected as invalid.',
  request_too_large: 'The submitted request is too large.',
  json_required: 'The server requires a JSON request.',
  audit_event_conflict: 'The audit number conflicts with an existing operation.',
  principal_registration_conflict: 'The principal UUID or configured issuer and subject is already registered.',
  global_role_registration_conflict: 'The global grant UUID or recipient and role is already registered.',
  membership_registration_conflict: 'The membership UUID or recipient, target and role is already registered.',
  recipient_inactive: 'The recipient is inactive.',
  recipient_issuer_mismatch: 'The recipient belongs to a different identity issuer.',
  admin_recipient_protected: 'A platform administrator cannot receive project or software membership through this operation.',
  submission_conflict: 'The server reported a submission conflict.',
  configured_issuer_required: 'The backend requires an approved configured identity issuer before registration.',
  outcome_unknown: 'The outcome is unknown. Keep the original audit number and exact request.',
});
