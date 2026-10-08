/** Preparation only: no HTTP, identity provisioning, credentials or persistence. */
export type RegistrationKind = 'PRINCIPAL' | 'GLOBAL' | 'PROJECT' | 'SOFTWARE';
export const registrationRoles = Object.freeze({
  GLOBAL: Object.freeze(['AUDITOR', 'PLATFORM_ADMIN']),
  PROJECT: Object.freeze(['PROJECT_VIEWER', 'CONTRIBUTOR', 'REVIEWER', 'RELEASE_AUTHORITY',
    'DISTRIBUTION_AUTHORITY', 'PRODUCTION_AUTHORITY', 'PRODUCTION_OPERATOR']),
  SOFTWARE: Object.freeze(['SOFTWARE_VIEWER', 'SOFTWARE_MAINTAINER']),
});
type Common = { kind: RegistrationKind; newId: string; eventNo: string; reason: string };
export type RegistrationInput =
  | (Common & { kind: 'PRINCIPAL'; principalType: 'USER' | 'SERVICE'; subject: string; displayName: string })
  | (Common & { kind: 'GLOBAL'; principalId: string; role: string })
  | (Common & { kind: 'PROJECT' | 'SOFTWARE'; principalId: string; scopeId: string; role: string });
export type RegistrationReview = Readonly<{ kind: RegistrationKind; confirmed: boolean;
  initialStatus: 'DISABLED' | 'SUSPENDED';
  request: Readonly<{ method: 'POST'; path: string; body: Readonly<Record<string, string>> }> }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Python str.strip whitespace, used by existing Pydantic validators. Opaque subject
// and name values are checked exactly; never trimmed or case-normalized.
const edgeWhitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/;
const outerWhitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g;
const controls = /[\u0000-\u001f\u007f]/;
function identifier(value: unknown): string {
  if (typeof value !== 'string' || !uuid.test(value)) throw Error('Registration identifiers must be exact UUIDs.');
  return value.toLowerCase();
}
function exactText(value: unknown, max: number, message: string): string {
  if (typeof value !== 'string' || !value || Array.from(value).length > max || edgeWhitespace.test(value) || controls.test(value))
    throw Error(message);
  return value;
}
export function prepareRegistration(input: RegistrationInput): RegistrationReview {
  if (!input || typeof input !== 'object' || !['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'].includes(input.kind))
    throw Error('Invalid registration operation.');
  const allowed = ['kind','newId','eventNo','reason', ...(input.kind === 'PRINCIPAL' ?
    ['principalType','subject','displayName'] : input.kind === 'GLOBAL' ? ['principalId','role'] : ['principalId','scopeId','role'])];
  if (Object.keys(input).length !== allowed.length || !allowed.every(key => Object.prototype.hasOwnProperty.call(input,key)))
    throw Error('Invalid registration fields.');
  if (typeof input.eventNo !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$/.test(input.eventNo))
    throw Error('Audit number must contain 1–50 letters, digits, dots, underscores, colons or hyphens.');
  const reason = typeof input.reason === 'string' ? input.reason.replace(outerWhitespace,'') : '';
  if (Array.from(reason).length < 5 || Array.from(reason).length > 500 || controls.test(reason))
    throw Error('Reason must contain 5–500 printable characters.');
  const common = {event_no:input.eventNo,reason};
  const newId = identifier(input.newId);
  let path: string, body: Record<string,string>;
  if (input.kind === 'PRINCIPAL') {
    if (!['USER','SERVICE'].includes(input.principalType)) throw Error('Invalid principal type.');
    const subject = exactText(input.subject,500,'Subject must contain 1–500 exact printable characters without surrounding whitespace.');
    const name = exactText(input.displayName,200,'Display name must contain 1–200 exact printable characters without surrounding whitespace.');
    path = '/api/v1/security/admin/principals';
    body = {...common,principal_id:newId,subject,principal_type:input.principalType,display_name:name};
  } else {
    if (!registrationRoles[input.kind].includes(input.role)) throw Error('Role does not belong to the selected scope.');
    const principalId = identifier(input.principalId);
    if (input.kind === 'GLOBAL') {
      path = '/api/v1/security/admin/global-roles';
      body = {...common,grant_id:newId,principal_id:principalId,role:input.role};
    } else {
      path = '/api/v1/security/admin/memberships/' + input.kind;
      body = {...common,membership_id:newId,principal_id:principalId,scope_id:identifier(input.scopeId),role:input.role};
    }
  }
  return Object.freeze({kind:input.kind,confirmed:false,initialStatus:input.kind === 'PRINCIPAL' ? 'DISABLED' : 'SUSPENDED',
    request:Object.freeze({method:'POST' as const,path,body:Object.freeze(body)})});
}
export function confirmRegistration(review: RegistrationReview, confirmed: boolean): RegistrationReview {
  return Object.freeze({...review,confirmed});
}
export function exportRegistration(review: RegistrationReview): string {
  if (!review.confirmed) throw Error('Confirm the exact registration before copying.');
  return JSON.stringify(review.request,null,2);
}
