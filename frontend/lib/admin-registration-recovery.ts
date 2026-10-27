import {record,exactFields,readCommandResponse} from './first-command-transport';
import {prepareRegistration,confirmRegistration,type RegistrationInput,type RegistrationReview,type RegistrationKind} from './admin-registration-draft';
import {registrationInput,registrationDenials} from './admin-registration-transport';
export const registrationRecoveryTextLimit=32768;
const format='slc-admin-registration-recovery';
function validOrigin(origin:string):boolean {try {const u=new URL(origin);return u.origin===origin&&!u.username&&!u.password&&(u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}catch{return false;}}
// Python's strict UTF-8 digest cannot encode lone UTF-16 surrogates. Preserve valid
// opaque subject/name code points exactly; never trim or normalize them here.
function validUnicode(value:string):boolean {for(let i=0;i<value.length;i++){const c=value.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const next=value.charCodeAt(++i);if(!(next>=0xdc00&&next<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
function canonical(input:unknown):RegistrationReview|null {try {const d=record(input);if(!d||Object.values(d).some(v=>typeof v!=='string'||!validUnicode(v)))return null;const review=confirmRegistration(prepareRegistration(d as RegistrationInput),true);return JSON.stringify(registrationInput(review))===JSON.stringify(d)?review:null;}catch{return null;}}
function envelope(review:RegistrationReview,origin:string){return {format,version:1,origin,input:registrationInput(review)};}
export function exportRegistrationRecovery(review:RegistrationReview,origin:string):string {
 if(review.confirmed!==true||!validOrigin(origin))throw Error('invalid_recovery');
 const verified=canonical(registrationInput(review));
 if(!verified||JSON.stringify(verified)!==JSON.stringify(review))throw Error('invalid_recovery');
 const text=JSON.stringify(envelope(verified,origin),null,2);
 if(new TextEncoder().encode(text).length>registrationRecoveryTextLimit)throw Error('invalid_recovery');return text;
}
export function parseRegistrationRecovery(text:string,origin:string):RegistrationReview|null {
 if(!validOrigin(origin)||typeof text!=='string'||text.length>registrationRecoveryTextLimit||new TextEncoder().encode(text).length>registrationRecoveryTextLimit)return null;
 try {const d=record(JSON.parse(text));if(!d||!exactFields(d,['format','version','origin','input'])||d.format!==format||d.version!==1||d.origin!==origin)return null;
 const review=canonical(d.input);if(!review)return null;const expected=envelope(review,origin),trimmed=text.trim();return trimmed===JSON.stringify(expected)||trimmed===JSON.stringify(expected,null,2)?review:null;}catch{return null;}
}
export type HistoricalRegistrationReceipt=Readonly<{kind:RegistrationKind;id:string;audit_event_no:string;applied_status:'DISABLED'|'SUSPENDED';principal_id?:string;role?:string;scope_id?:string}>;
/** Historical application only: no assertion about current activation or replay. */
export function projectHistoricalRegistrationReceipt(value:unknown,review:RegistrationReview):HistoricalRegistrationReceipt|null {
 const d=record(value),b=review.request.body,kind=review.kind,id=kind==='PRINCIPAL'?b.principal_id:kind==='GLOBAL'?b.grant_id:b.membership_id;
 const fields=['kind','id','audit_event_no','applied_status',...(kind==='PRINCIPAL'?[]:kind==='GLOBAL'?['principal_id','role']:['principal_id','role','scope_id'])];
 if(!d||!exactFields(d,fields)||d.kind!==kind||d.id!==id||d.audit_event_no!==b.event_no||d.applied_status!==review.initialStatus)return null;
 const common={kind,id,audit_event_no:b.event_no,applied_status:review.initialStatus};if(kind==='PRINCIPAL')return Object.freeze(common);
 if(d.principal_id!==b.principal_id||d.role!==b.role||(kind!=='GLOBAL'&&d.scope_id!==b.scope_id))return null;
 return Object.freeze({...common,principal_id:b.principal_id,role:b.role,...(kind==='GLOBAL'?{}:{scope_id:b.scope_id})});
}
export type RegistrationRecoveryState=Readonly<{phase:'unknown'|'checking'|'confirmed';review:RegistrationReview;error:string|null;historicalreceipt:HistoricalRegistrationReceipt|null}>;
/** Zero-network import. This frozen facade has no business send or retry method. */
export function importRegistrationRecovery(text:string,origin:string){
 const review=parseRegistrationRecovery(text,origin);if(!review)throw Error('invalid_recovery');
 const body=JSON.stringify(registrationInput(review));let state:RegistrationRecoveryState=Object.freeze({phase:'unknown',review,error:'outcome_unknown',historicalreceipt:null});
 const update=(phase:RegistrationRecoveryState['phase'],error:string|null,historicalreceipt:HistoricalRegistrationReceipt|null=null)=>state=Object.freeze({phase,review,error,historicalreceipt});
 return Object.freeze({get state(){return state;},async recover(enabled:boolean,fetcher:typeof fetch=fetch):Promise<RegistrationRecoveryState>{
  if(state.phase==='checking'||state.phase==='confirmed')return state;
  if(enabled!==true)return update('unknown','registration_submission_disabled');update('checking',null);
  try {const response=await fetcher('/auth/admin-registration-receipt',{method:'POST',body,headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
   const value=await readCommandResponse(response),receipt=response.status===200?projectHistoricalRegistrationReceipt(value,review):null;
   if(receipt)return update('confirmed',null,receipt);const error=record(value)?.error;
   if(typeof error==='string'&&registrationDenials[response.status]?.includes(error))return update('unknown',error);
  }catch{/* Missing or malformed historical evidence never proves failure or success. */}
  return update('unknown','outcome_unknown');
 }});
}
export type ImportedRegistrationRecovery=ReturnType<typeof importRegistrationRecovery>;
