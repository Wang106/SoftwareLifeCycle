/** Grant status request preparation only; no transport, credentials or persistence. */
export type GrantScope = 'GLOBAL' | 'PROJECT' | 'SOFTWARE';
export type GrantStatus = 'ACTIVE' | 'SUSPENDED';
export type GrantTarget = Readonly<{ id: string; scope: GrantScope; status: GrantStatus;
  role: string; principalId: string; historyStatus: GrantStatus }>;
export type GrantReview = Readonly<{ target: GrantTarget; confirmed: boolean;
  request: Readonly<{ method: 'POST'; path: string; body: Readonly<{
    event_no: string; expected_status: GrantStatus; status: GrantStatus; reason: string;
  }> }> }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function prepareGrantStatus(target: GrantTarget, eventNo: string, reason: string): GrantReview {
  if (!['GLOBAL', 'PROJECT', 'SOFTWARE'].includes(target.scope) || !uuid.test(target.id) ||
      !uuid.test(target.principalId) || !target.role.trim() || target.role.length > 100)
    throw new Error('Invalid grant target.');
  if (!['ACTIVE', 'SUSPENDED'].includes(target.status) || target.historyStatus !== target.status)
    throw new Error('Refresh the grant before preparing a status change.');
  const key = eventNo.trim(), text = reason.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$/.test(key))
    throw new Error('Audit number must contain 1–50 letters, digits, dots, underscores, colons or hyphens.');
  // Python/Pydantic counts Unicode code points, rather than UTF-16 code units.
  if (Array.from(text).length < 5 || Array.from(text).length > 500 || /[\u0000-\u001f\u007f]/.test(text))
    throw new Error('Reason must contain 5–500 printable characters.');
  const exact = Object.freeze({ ...target, id: target.id.toLowerCase(), principalId: target.principalId.toLowerCase() });
  const body = Object.freeze({ event_no: key, expected_status: exact.status,
    status: exact.status === 'ACTIVE' ? 'SUSPENDED' as const : 'ACTIVE' as const, reason: text });
  const path = exact.scope === 'GLOBAL' ? '/api/v1/security/admin/global-roles/' + exact.id + '/status' :
    '/api/v1/security/admin/memberships/' + exact.scope + '/' + exact.id + '/status';
  return Object.freeze({ target: exact, confirmed: false,
    request: Object.freeze({ method: 'POST' as const, path, body }) });
}
export function confirmGrantStatus(review: GrantReview, confirmed: boolean): GrantReview {
  return Object.freeze({ ...review, confirmed });
}
export function exportGrantStatus(review: GrantReview): string {
  if (!review.confirmed) throw new Error('Confirm the exact grant and status change before copying.');
  return JSON.stringify(review.request, null, 2);
}
