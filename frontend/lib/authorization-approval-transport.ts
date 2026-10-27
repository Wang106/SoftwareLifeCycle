import {validUuid} from './command-draft';
import {record,exactFields,readCommandResponse} from './first-command-transport';
import {productionTime} from './production-command-transport';
export type AuthorizationApprovalTarget=Readonly<{authorization_no:string}>;
export type AuthorizationApprovalFacts=Readonly<{
 authorization_id:string;authorization_no:string;release_id:string;snapshot_id:string;release_decision_id:string;
 distribution_id:string;delivery_package_id:string;package_revision:number;customer_id:string;project_id:string;
 site_code:string;line_code:string;purpose:string;batch_limit:number|null;restriction_note:string|null;
 creation_event_id:string;creator_principal_id:string;
}>;
export type AuthorizationApprovalContext=Readonly<{version:1;context:AuthorizationApprovalFacts;context_digest:string}>;
export type AuthorizationApprovalBody=Readonly<{request_id:string;expected_context_digest:string;reason:string}>;
export type AuthorizationApprovalCommand=Readonly<{operation:'authorization-approval';target:AuthorizationApprovalTarget;context:AuthorizationApprovalContext;body:AuthorizationApprovalBody}>;
const id=(v:unknown):v is string=>typeof v==='string'&&validUuid(v)&&v===v.toLowerCase();
const digest=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
function unicode(s:string):boolean {for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const n=s.charCodeAt(++i);if(!(n>=0xdc00&&n<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length>0&&Array.from(v).length<=max&&v.trim()===v&&!/^\u0085|\u0085$/.test(v)&&!/[\u0000-\u001f\u007f]/.test(v)&&unicode(v);
const reasonText=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&Array.from(v).length<=2000&&v.trim()===v&&!/^\u0085|\u0085$/.test(v)&&!/[\u0000-\u0008\u000b-\u001f\u007f]/.test(v)&&unicode(v);
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&(v as number)>0&&(v as number)<=2147483647;
const ids=['authorization_id','release_id','snapshot_id','release_decision_id','distribution_id','delivery_package_id','customer_id','project_id','creation_event_id','creator_principal_id'];
const fields=['authorization_id','authorization_no','release_id','snapshot_id','release_decision_id','distribution_id','delivery_package_id','package_revision','customer_id','project_id','site_code','line_code','purpose','batch_limit','restriction_note','creation_event_id','creator_principal_id'];
export function parseAuthorizationApprovalTarget(value:unknown):AuthorizationApprovalTarget|null {
 const d=record(value);return d&&exactFields(d,['authorization_no'])&&text(d.authorization_no,50)?Object.freeze({authorization_no:d.authorization_no}):null;
}
/** Structural review evidence, never permission. The server verifies the digest and current authority. */
export function parseAuthorizationApprovalContext(value:unknown,target:AuthorizationApprovalTarget):AuthorizationApprovalContext|null {
 const d=record(value),c=record(d?.context);
 if(!parseAuthorizationApprovalTarget(target)||!d||!c||!exactFields(d,['version','context','context_digest'])||d.version!==1||!digest(d.context_digest)||!exactFields(c,fields)||c.authorization_no!==target.authorization_no||!ids.every(k=>id(c[k]))||!integer(c.package_revision)||!text(c.site_code,80)||!text(c.line_code,80)||!text(c.purpose,50)||(c.batch_limit!==null&&!integer(c.batch_limit))||(c.restriction_note!==null&&(typeof c.restriction_note!=='string'||new TextEncoder().encode(c.restriction_note).length>8192||c.restriction_note.includes('\0')||!unicode(c.restriction_note))))return null;
 const facts=Object.fromEntries(fields.map(k=>[k,c[k]])) as AuthorizationApprovalFacts;
 return Object.freeze({version:1,context:Object.freeze(facts),context_digest:d.context_digest});
}
export function parseAuthorizationApprovalCommand(value:unknown):AuthorizationApprovalCommand|null {
 const d=record(value),target=parseAuthorizationApprovalTarget(d?.target),b=record(d?.body);
 if(!d||!target||!b||!exactFields(d,['operation','target','context','body'])||d.operation!=='authorization-approval')return null;
 const context=parseAuthorizationApprovalContext(d.context,target);
 if(!context||!exactFields(b,['request_id','expected_context_digest','reason'])||!id(b.request_id)||b.expected_context_digest!==context.context_digest||!reasonText(b.reason))return null;
 const command=Object.freeze({operation:'authorization-approval' as const,target,context,body:Object.freeze({request_id:b.request_id,expected_context_digest:context.context_digest,reason:b.reason})});
 return new TextEncoder().encode(JSON.stringify(command)).length<=8192?command:null;
}
export type AuthorizationApprovalReview=Readonly<{command:AuthorizationApprovalCommand;confirmed:boolean}>;
export function confirmAuthorizationApproval(input:unknown,confirmed:boolean):AuthorizationApprovalReview {const command=parseAuthorizationApprovalCommand(input);if(!command)throw Error('invalid_review');return Object.freeze({command,confirmed:confirmed===true});}
export const authorizationApprovalPath=(c:AuthorizationApprovalCommand)=>'/api/v1/authorizations/'+encodeURIComponent(c.target.authorization_no)+'/approval';
export const authorizationApprovalContextPath=(t:AuthorizationApprovalTarget)=>'/api/v1/authorizations/'+encodeURIComponent(t.authorization_no)+'/approval-context';
export const authorizationApprovalEvent=(c:AuthorizationApprovalCommand)=>'EVT-PAA-'+c.body.request_id.replaceAll('-','');
export type AuthorizationApprovalReceipt=Readonly<{authorization_id:string;authorization_no:string;request_id:string;audit_event_no:string;applied_status:'APPROVED';approved_at:string;creator_principal_id:string;approver_principal_id:string;expected_context_digest:string;reason:string}>;
export function projectAuthorizationApprovalReceipt(value:unknown,c:AuthorizationApprovalCommand,principalId?:string):AuthorizationApprovalReceipt|null {
 const d=record(value),facts=c.context.context,b=c.body;
 if(!d||!exactFields(d,['authorization_id','authorization_no','request_id','audit_event_no','applied_status','approved_at','creator_principal_id','approver_principal_id','expected_context_digest','reason'])||d.authorization_id!==facts.authorization_id||d.authorization_no!==c.target.authorization_no||d.request_id!==b.request_id||d.audit_event_no!==authorizationApprovalEvent(c)||d.applied_status!=='APPROVED'||d.creator_principal_id!==facts.creator_principal_id||!id(d.approver_principal_id)||d.approver_principal_id===d.creator_principal_id||(principalId!==undefined&&d.approver_principal_id!==principalId)||d.expected_context_digest!==b.expected_context_digest||d.reason!==b.reason||typeof d.approved_at!=='string'||!productionTime(d.approved_at))return null;
 return Object.freeze({...d}) as AuthorizationApprovalReceipt;
}
export type AuthorizationApprovalError = 'authorization_approval_disabled'|'invalid_request'|'session_required'|'cross_origin_request'|'read_only_mode'|
  'submission_forbidden'|'request_conflict'|'submission_conflict'|'version_conflict'|'target_not_found'|'request_too_large'|'json_required'|'outcome_unknown';
const denials: Readonly<Record<number,readonly AuthorizationApprovalError[]>> = {
  400:['invalid_request'],401:['session_required'],403:['cross_origin_request','read_only_mode','submission_forbidden'],
  404:['target_not_found'],409:['request_conflict','submission_conflict','version_conflict'],413:['request_too_large'],
  415:['json_required'],422:['invalid_request'],503:['authorization_approval_disabled'],
};
export type AuthorizationApprovalState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';
  review:AuthorizationApprovalReview;command:AuthorizationApprovalCommand;error:AuthorizationApprovalError|null;receipt:AuthorizationApprovalReceipt|null}>;
/** Frozen original bytes; recovery reads the actor-bound original audit, never current history. */
export class AuthorizationApprovalSubmission {
  private current:AuthorizationApprovalState;
  private uncertain=false;
  private readonly body:string;
  constructor(review:AuthorizationApprovalReview) {
    if (review.confirmed !== true) throw Error('Confirm the exact request before sending.');
    const command=parseAuthorizationApprovalCommand(review.command);
    if (!command || JSON.stringify(command) !== JSON.stringify(review.command)) throw Error('invalid_review');
    this.body=JSON.stringify(command);
    this.current=Object.freeze({phase:'idle',review:confirmAuthorizationApproval(command,true),command,error:null,receipt:null});
  }
  get state():AuthorizationApprovalState { return this.current; }
  private update(phase:AuthorizationApprovalState['phase'],error:AuthorizationApprovalError|null,receipt:AuthorizationApprovalReceipt|null=null) {
    this.current=Object.freeze({...this.current,phase,error,receipt});return this.current;
  }
  send(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('submit',enabled,fetcher); }
  recover(enabled:boolean,fetcher:typeof fetch=fetch) { return this.run('recover',enabled,fetcher); }
  private async run(mode:'submit'|'recover',enabled:boolean,fetcher:typeof fetch):Promise<AuthorizationApprovalState> {
    if (['sending','checking','confirmed'].includes(this.current.phase)) return this.current;
    if (mode === 'recover') this.uncertain=true;
    if (enabled !== true) return this.update(this.uncertain?'unknown':'rejected','authorization_approval_disabled');
    this.update(mode === 'submit'?'sending':'checking',null);
    try {
      const response=await fetcher(mode === 'submit'?'/auth/authorization-approval':'/auth/authorization-approval-receipt',{
        method:'POST',body:this.body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',
        redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response);
      const receipt=response.status === 200?projectAuthorizationApprovalReceipt(value,this.current.command):null;
      if (receipt) { this.uncertain=false;return this.update('confirmed',null,receipt); }
      const error=record(value)?.error;
      if (typeof error === 'string' && denials[response.status]?.includes(error as AuthorizationApprovalError))
        return this.update(this.uncertain?'unknown':'rejected',error as AuthorizationApprovalError);
    } catch { /* Lost replies do not prove the correction was not committed. */ }
    this.uncertain=true;return this.update('unknown','outcome_unknown');
  }
}

/** Python json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':'))
 * for this fixed primitive-valued context. Never use a client digest as authority. */
export async function validateAuthorizationApprovalContextDigest(value:AuthorizationApprovalContext):Promise<boolean> {
 try {
  const parsed=parseAuthorizationApprovalContext(value,{authorization_no:value.context.authorization_no});if(!parsed)return false;
  const sorted=Object.fromEntries(Object.keys(parsed.context).sort().map(k=>[k,parsed.context[k as keyof AuthorizationApprovalFacts]]));
  const canonical=JSON.stringify({context:sorted,version:1});
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical));
  return Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('')===parsed.context_digest;
 }catch{return false;}
}
