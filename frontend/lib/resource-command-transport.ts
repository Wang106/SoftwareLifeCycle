import { blankFields, prepare, confirm, validUuid, type Review } from './command-draft';
import { record, exactFields, readCommandResponse, type FirstError } from './first-command-transport';

export const resourceDigestFields = ['request_id','entity_type','entity_id','title','location_kind','location','description','actor_name','reason'] as const;
export type ResourceBody = Readonly<Record<string,string>>;
export type ResourceCommand = Readonly<{ operation:'resource'; target:string; body:ResourceBody }>;
export function resourceReview(command:ResourceCommand):Review {
  const b=command.body;
  return confirm(prepare('resource',{...blankFields,target:command.target,entityType:b.entity_type,
    title:b.title,locationKind:b.location_kind,location:b.location,description:b.description,
    actor:b.actor_name,reason:b.reason},b.request_id),true);
}
/** Fixed resource registration only; locations are data, never fetched by this transport. */
export function parseResourceCommand(value:unknown):ResourceCommand|null {
  const d=record(value),b=record(d?.body);
  if(!d || !b || !exactFields(d,['operation','target','body']) || d.operation!=='resource' ||
    typeof d.target!=='string' || !validUuid(d.target.trim()) || !exactFields(b,resourceDigestFields) ||
    !Object.values(b).every(v=>typeof v==='string' && !/[\uD800-\uDFFF]/u.test(v.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,''))) ||
    (b.entity_id as string).trim().toLowerCase()!==d.target.trim().toLowerCase())return null;
  try {
    const target=d.target.trim().toLowerCase();
    const r=resourceReview({operation:'resource',target,body:b as ResourceBody});
    const command=Object.freeze({operation:'resource' as const,target,body:r.draft.payload as ResourceBody});
    return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
  } catch {return null;}
}
export function resourcePath(_command:ResourceCommand):string {return '/api/v1/resources';}
export function resourceEvent(command:ResourceCommand):string {return 'EVT-LK-'+command.body.request_id;}
/** Mirrors the version-1 ordered, normalized UTF-8 JSON-array digest in the backend. */
export async function resourceDigest(command:ResourceCommand):Promise<string> {
  const bytes=new TextEncoder().encode(JSON.stringify(resourceDigestFields.map(k=>command.body[k])));
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
}
export type ResourceReceipt=Readonly<{operation:'resource';request_id:string;target:string;audit_event_no:string;
  result:Readonly<Record<string,string>>}>;
export function projectResourceReceipt(value:unknown,command:ResourceCommand):ResourceReceipt|null {
  const d=record(value),r=record(d?.result),b=command.body;
  if(!d || !r || d.operation!=='resource' || d.request_id!==b.request_id || d.target!==command.target ||
    d.audit_event_no!==resourceEvent(command) || r.id!==b.request_id ||
    typeof r.entity_ref!=='string' || !r.entity_ref.trim() || r.entity_ref.length>240 || /[\u0000-\u001f\u007f]/.test(r.entity_ref))return null;
  const result:Record<string,string>={id:b.request_id,entity_ref:r.entity_ref};
  for(const k of resourceDigestFields.filter(k=>k!=='request_id')) {
    if(r[k]!==b[k])return null;result[k]=b[k];
  }
  return Object.freeze({operation:'resource',request_id:b.request_id,target:command.target,
    audit_event_no:resourceEvent(command),result:Object.freeze(result)});
}
export type ResourceError = Exclude<FirstError, 'first_submission_disabled' | 'version_conflict'> |
  'resource_submission_disabled';
const denials: Readonly<Record<number, readonly ResourceError[]>> = {
  400:['invalid_request'], 401:['session_required'], 403:['cross_origin_request','read_only_mode','submission_forbidden'],
  409:['request_conflict','submission_conflict'], 413:['request_too_large'],
  415:['json_required'], 422:['invalid_request'], 503:['resource_submission_disabled'],
};
export type ResourceState = Readonly<{ phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:Review; command:ResourceCommand; error:ResourceError|null; receipt:ResourceReceipt|null }>;
/** Memory-only original bytes; audit recovery never repeats a write. */
export class ResourceSubmission {
  private current: ResourceState;
  private uncertain = false;
  private readonly body: string;
  constructor(review: Review) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command = parseResourceCommand({ operation:review.draft.operation, target:review.draft.payload.entity_id, body:review.draft.payload });
    if (!command) throw Error('invalid_review');
    const canonical = resourceReview(command);
    if (canonical.draft.path !== review.draft.path || canonical.draft.trace !== review.draft.trace ||
        canonical.draft.audit !== review.draft.audit || JSON.stringify(canonical.draft.payload) !== JSON.stringify(review.draft.payload)) throw Error('invalid_review');
    this.body = JSON.stringify(command);
    this.current = Object.freeze({ phase:'idle', review:canonical, command, error:null, receipt:null });
  }
  get state(): ResourceState { return this.current; }
  private update(phase:ResourceState['phase'], error:ResourceError|null, receipt:ResourceReceipt|null = null) {
    this.current = Object.freeze({ ...this.current, phase, error, receipt }); return this.current;
  }
  send(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ResourceState> { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean, fetcher:typeof fetch = fetch): Promise<ResourceState> { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover', enabled:boolean, fetcher:typeof fetch): Promise<ResourceState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain = true;
    if (enabled !== true) return this.update(this.uncertain ? 'unknown' : 'rejected','resource_submission_disabled');
    this.update(mode === 'submit' ? 'sending' : 'checking',null);
    try {
      const response = await fetcher(mode === 'submit' ? '/auth/resource-command' : '/auth/resource-command-receipt', {
        method:'POST', body:this.body, headers:{'Content-Type':'application/json',Accept:'application/json'},
        credentials:'same-origin', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(15000) });
      const value = await readCommandResponse(response);
      const receipt = response.status === 200 ? projectResourceReceipt(value,this.current.command) : null;
      if (receipt) { this.uncertain = false; return this.update('confirmed',null,receipt); }
      const error = record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as ResourceError))
        return this.update(this.uncertain ? 'unknown' : 'rejected',error as ResourceError);
    } catch { /* Lost responses and missing audit records do not prove absence. */ }
    this.uncertain = true; return this.update('unknown','outcome_unknown');
  }
}
