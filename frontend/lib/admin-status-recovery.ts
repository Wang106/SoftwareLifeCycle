import {record,exactFields,readCommandResponse} from './first-command-transport';
import {validUuid} from './command-draft';
import {preparePrincipalStatus,type PrincipalReview} from './principal-status-draft';
import {prepareGrantStatus,type GrantReview} from './grant-status-draft';
export type AdminStatusKind='PRINCIPAL'|'GLOBAL'|'PROJECT'|'SOFTWARE';
export type AdminStatusRecoveryCommand=Readonly<{kind:AdminStatusKind;id:string;event_no:string;expected_status:string;status:string;reason:string;principal_id?:string;role?:string}>;
export const adminStatusRecoveryTextLimit=32768;
const format='slc-admin-status-recovery';
const id=(x:unknown):x is string=>typeof x==='string'&&validUuid(x)&&x===x.toLowerCase();
function unicode(s:string):boolean{for(let i=0;i<s.length;i++){const n=s.charCodeAt(i);if(n>=0xd800&&n<=0xdbff){const m=s.charCodeAt(++i);if(!(m>=0xdc00&&m<=0xdfff))return false;}else if(n>=0xdc00&&n<=0xdfff)return false;}return true;}
const originValid=(origin:string)=>{try{const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&(u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}catch{return false;}};
export function parseAdminStatusRecoveryCommand(value:unknown):AdminStatusRecoveryCommand|null{
 const d=record(value);if(!d||!['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'].includes(d.kind as string)||!exactFields(d,['kind','id','event_no','expected_status','status','reason',...(d.kind==='PRINCIPAL'?[]:['principal_id','role'])])||!id(d.id)||typeof d.event_no!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$/.test(d.event_no)||typeof d.reason!=='string'||d.reason!==d.reason.trim()||Array.from(d.reason).length<5||Array.from(d.reason).length>500||/[\u0000-\u001f\u007f]/.test(d.reason)||!unicode(d.reason))return null;
 const states=d.kind==='PRINCIPAL'?['ACTIVE','DISABLED']:['ACTIVE','SUSPENDED'];
 if(!states.includes(d.expected_status as string)||!states.includes(d.status as string)||d.expected_status===d.status)return null;
 if(d.kind!=='PRINCIPAL'&&(!id(d.principal_id)||typeof d.role!=='string'||!d.role.trim()||d.role.length>100||!unicode(d.role)||/[\u0000-\u001f\u007f]/.test(d.role)))return null;
 return Object.freeze({kind:d.kind,id:d.id,event_no:d.event_no,expected_status:d.expected_status,status:d.status,reason:d.reason,...(d.kind==='PRINCIPAL'?{}:{principal_id:d.principal_id,role:d.role})}) as AdminStatusRecoveryCommand;
}
export function adminStatusRecoveryCommand(review:PrincipalReview|GrantReview):AdminStatusRecoveryCommand{
 if(review.confirmed!==true)throw Error('invalid_recovery');
 const principal='principalType' in review.target;
 const canonical=principal?preparePrincipalStatus((review as PrincipalReview).target,review.request.body.event_no,review.request.body.reason):prepareGrantStatus((review as GrantReview).target,review.request.body.event_no,review.request.body.reason);
 if(JSON.stringify(canonical.request)!==JSON.stringify(review.request))throw Error('invalid_recovery');
 const target=review.target as GrantReview['target'];
 const c=parseAdminStatusRecoveryCommand({kind:principal?'PRINCIPAL':target.scope,id:canonical.target.id,...canonical.request.body,...(principal?{}:{principal_id:target.principalId,role:target.role})});if(!c)throw Error('invalid_recovery');return c;
}
function envelope(command:AdminStatusRecoveryCommand,origin:string){return{format,version:1,origin,command};}
export function exportAdminStatusRecovery(review:PrincipalReview|GrantReview,origin:string):string{if(!originValid(origin))throw Error('invalid_recovery');const text=JSON.stringify(envelope(adminStatusRecoveryCommand(review),origin),null,2);if(new TextEncoder().encode(text).length>adminStatusRecoveryTextLimit)throw Error('invalid_recovery');return text;}
export function parseAdminStatusRecovery(text:string,origin:string):AdminStatusRecoveryCommand|null{if(!originValid(origin)||typeof text!=='string'||text.length>adminStatusRecoveryTextLimit||new TextEncoder().encode(text).length>adminStatusRecoveryTextLimit)return null;try{const d=record(JSON.parse(text));if(!d||!exactFields(d,['format','version','origin','command'])||d.format!==format||d.version!==1||d.origin!==origin)return null;const c=parseAdminStatusRecoveryCommand(d.command);if(!c)return null;const e=envelope(c,origin),trimmed=text.trim();return trimmed===JSON.stringify(e)||trimmed===JSON.stringify(e,null,2)?c:null;}catch{return null;}}
export type HistoricalAdminStatusReceipt=Readonly<{kind:AdminStatusKind;id:string;audit_event_no:string;expected_status:string;applied_status:string;revoked_browser_sessions?:number;principal_id?:string;role?:string;scope_id?:string}>;
export function projectHistoricalAdminStatusReceipt(value:unknown,c:AdminStatusRecoveryCommand):HistoricalAdminStatusReceipt|null{
 const d=record(value),principal=c.kind==='PRINCIPAL',membership=!principal&&c.kind!=='GLOBAL';
 if(!d||!exactFields(d,['kind','id','audit_event_no','expected_status','applied_status',...(principal?['revoked_browser_sessions']:['principal_id','role',...(membership?['scope_id']:[])])])||d.kind!==c.kind||d.id!==c.id||d.audit_event_no!==c.event_no||d.expected_status!==c.expected_status||d.applied_status!==c.status)return null;
 if(principal){if(!Number.isSafeInteger(d.revoked_browser_sessions)||(d.revoked_browser_sessions as number)<0||(c.status==='ACTIVE'&&d.revoked_browser_sessions!==0))return null;}
 else if(d.principal_id!==c.principal_id||d.role!==c.role||(membership&&!id(d.scope_id)))return null;
 return Object.freeze({...d}) as HistoricalAdminStatusReceipt;
}
export type AdminStatusRecoveryState=Readonly<{phase:'unknown'|'checking'|'confirmed';command:AdminStatusRecoveryCommand;error:string|null;historicalreceipt:HistoricalAdminStatusReceipt|null}>;
/** Zero network/storage on import; historical receipt never grants current permissions. */
export function importAdminStatusRecovery(text:string,origin:string){const command=parseAdminStatusRecovery(text,origin);if(!command)throw Error('invalid_recovery');const body=JSON.stringify(command);let state:AdminStatusRecoveryState=Object.freeze({phase:'unknown',command,error:'outcome_unknown',historicalreceipt:null});const update=(phase:AdminStatusRecoveryState['phase'],error:string|null,historicalreceipt:HistoricalAdminStatusReceipt|null=null)=>state=Object.freeze({phase,command,error,historicalreceipt});return Object.freeze({get state(){return state;},async recover(enabled:boolean,fetcher:typeof fetch=fetch):Promise<AdminStatusRecoveryState>{if(state.phase==='checking'||state.phase==='confirmed')return state;if(enabled!==true)return update('unknown','admin_status_recovery_disabled');update('checking',null);try{const r=await fetcher('/auth/admin-status-receipt',{method:'POST',body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});const value=await readCommandResponse(r),receipt=r.status===200?projectHistoricalAdminStatusReceipt(value,command):null;if(receipt)return update('confirmed',null,receipt);const error=record(value)?.error;if(typeof error==='string'&&['session_required','submission_forbidden','principal_submission_disabled','grant_submission_disabled','cross_origin_request','invalid_request','request_too_large','json_required'].includes(error))return update('unknown',error);}catch{}return update('unknown','outcome_unknown');}});}
export type ImportedAdminStatusRecovery=ReturnType<typeof importAdminStatusRecovery>;
