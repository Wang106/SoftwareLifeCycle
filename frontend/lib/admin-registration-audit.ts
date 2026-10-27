import 'server-only';
import { record, exactFields } from './first-command-transport';
import { validUuid } from './command-draft';
import type { RegistrationReview } from './admin-registration-draft';
import { projectHistoricalRegistrationReceipt, type HistoricalRegistrationReceipt } from './admin-registration-recovery';

// Python ensure_ascii=False UTF-8 must never silently replace a lone surrogate.
export function scalarUnicode(value: string): boolean {
  for (let i=0;i<value.length;i++) {
    const n=value.charCodeAt(i);
    if (n>=0xd800 && n<=0xdbff) {
      const next=value.charCodeAt(++i); if (!(next>=0xdc00 && next<=0xdfff)) return false;
    } else if (n>=0xdc00 && n<=0xdfff) return false;
  }
  return true;
}
export async function principalRegistrationDigest(review: RegistrationReview, issuer: string): Promise<string|null> {
  const b=review.request.body;
  const data={display_name:b.display_name,issuer,principal_id:b.principal_id,principal_type:b.principal_type,
    reason:b.reason,subject:b.subject}; // Python sort_keys order, event_no intentionally excluded.
  if (Object.values(data).some(v=>typeof v!=='string' || !scalarUnicode(v))) return null;
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(data)));
  return Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
}
/** Only original immutable registration evidence; not current status or a write capability. */
export async function projectAdminRegistrationAudit(value:unknown,review:RegistrationReview,
  actorId:string,trustedIssuer:string):Promise<HistoricalRegistrationReceipt|null> {
  const d=record(value),p=record(d?.payload),b=review.request.body,k=review.kind;
  const id=k==='PRINCIPAL'?b.principal_id:k==='GLOBAL'?b.grant_id:b.membership_id;
  const entity=k==='PRINCIPAL'?'SECURITY_PRINCIPAL':k==='GLOBAL'?'GLOBAL_ROLE':k+'_MEMBERSHIP';
  const event=k==='PRINCIPAL'?'PRINCIPAL_REGISTERED':k==='GLOBAL'?'GLOBAL_ROLE_REGISTERED':'MEMBERSHIP_REGISTERED';
  if (!d || !p || typeof d.id!=='string' || !validUuid(d.id) || !validUuid(actorId) || d.event_no!==b.event_no ||
      d.actor_principal_id!==actorId || d.declared_actor_name!==null || d.action!=='REGISTER' ||
      d.entity_type!==entity || d.event_type!==event || d.entity_id!==id || d.entity_ref!==id) return null;
  let expected:Record<string,unknown>;
  if (k==='PRINCIPAL') {
    const digest=await principalRegistrationDigest(review,trustedIssuer); if (!digest) return null;
    expected={principal_id:id,principal_type:b.principal_type,status:'DISABLED',reason:b.reason,request_digest:digest};
  } else expected={...(k==='GLOBAL'?{grant_id:id}:{scope:k,membership_id:id}),principal_id:b.principal_id,
    ...(k==='GLOBAL'?{}:{scope_id:b.scope_id}),role:b.role,status:'SUSPENDED',reason:b.reason};
  if (!exactFields(p,Object.keys(expected)) || Object.entries(expected).some(([key,val])=>p[key]!==val)) return null;
  return projectHistoricalRegistrationReceipt({kind:k,id,audit_event_no:b.event_no,applied_status:review.initialStatus,
    ...(k==='PRINCIPAL'?{}:{principal_id:b.principal_id,role:b.role,...(k==='GLOBAL'?{}:{scope_id:b.scope_id})})},review);
}
