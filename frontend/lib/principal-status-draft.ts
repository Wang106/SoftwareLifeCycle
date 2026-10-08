/** Local identity status preparation only; no transport, credentials or persistence. */
export type PrincipalStatus = 'ACTIVE' | 'DISABLED';
export type PrincipalTarget = Readonly<{ id: string; principalType: 'USER' | 'SERVICE';
  status: PrincipalStatus; historyStatus: PrincipalStatus; protectedAdministrator: boolean;
  issuerMatchesConfiguration: boolean }>;
export type PrincipalReview = Readonly<{ target: PrincipalTarget; confirmed: boolean;
  request: Readonly<{ method: 'POST'; path: string; body: Readonly<{
    event_no: string; expected_status: PrincipalStatus; status: PrincipalStatus; reason: string;
  }> }> }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function principalPreparationError(target: PrincipalTarget): string | null {
  if (!uuid.test(target.id) || !['USER', 'SERVICE'].includes(target.principalType) ||
      typeof target.protectedAdministrator !== 'boolean' || typeof target.issuerMatchesConfiguration !== 'boolean')
    return 'Invalid identity target.';
  if (target.protectedAdministrator) return 'Protected administrator identities require the separate recovery procedure.';
  if (!['ACTIVE', 'DISABLED'].includes(target.status) || target.historyStatus !== target.status)
    return 'Refresh identity detail and history before preparing a status change.';
  return null;
}
export function samePrincipalTarget(a: PrincipalTarget, b: PrincipalTarget): boolean {
  return a.id === b.id.toLowerCase() && a.principalType === b.principalType && a.status === b.status &&
    a.historyStatus === b.historyStatus && a.protectedAdministrator === b.protectedAdministrator &&
    a.issuerMatchesConfiguration === b.issuerMatchesConfiguration;
}
export function preparePrincipalStatus(target: PrincipalTarget, eventNo: string, reason: string): PrincipalReview {
  const error = principalPreparationError(target);
  if (error) throw new Error(error);
  const key = eventNo.trim(), text = reason.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$/.test(key))
    throw new Error('Audit number must contain 1–50 letters, digits, dots, underscores, colons or hyphens.');
  if (Array.from(text).length < 5 || Array.from(text).length > 500 || /[\u0000-\u001f\u007f]/.test(text))
    throw new Error('Reason must contain 5–500 printable characters.');
  const exact = Object.freeze({ id: target.id.toLowerCase(), principalType: target.principalType,
    status: target.status, historyStatus: target.historyStatus, protectedAdministrator: target.protectedAdministrator,
    issuerMatchesConfiguration: target.issuerMatchesConfiguration });
  const body = Object.freeze({ event_no: key, expected_status: exact.status,
    status: exact.status === 'ACTIVE' ? 'DISABLED' as const : 'ACTIVE' as const, reason: text });
  return Object.freeze({ target: exact, confirmed: false,
    request: Object.freeze({ method: 'POST' as const, path: '/api/v1/security/admin/principals/' + exact.id + '/status', body }) });
}
export function confirmPrincipalStatus(review: PrincipalReview, confirmed: boolean): PrincipalReview {
  return Object.freeze({ ...review, confirmed });
}
export function exportPrincipalStatus(review: PrincipalReview): string {
  if (!review.confirmed) throw new Error('Confirm the exact identity and status change before copying.');
  return JSON.stringify(review.request, null, 2);
}
