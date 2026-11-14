import { validUuid } from './command-draft';
import { record, exactFields } from './first-command-transport';
export type Target=Readonly<{release_id:string;component_definition_id:string;base_component_id:string|null}>;
export type Context=Readonly<Target & {project_id:string;project_code:string;project_name:string;customer_id:string;customer_code:string;customer_name:string;software_id:string;software_code:string;software_name:string;standard_base_release_id:string;standard_base_version:string;standard_base_status:string;release_version:string;release_status:'DRAFT';component_code:string;component_name:string;base_component_version:string|null}>;
export type ContextEnvelope=Readonly<{version:1;context:Context;context_digest:string}>;
export type Body=Readonly<Target & {request_id:string;version:string;delta_type:'ADDED'|'UNCHANGED'|'MODIFIED';reason:string;expected_context_digest:string}>;
export type Command=Readonly<{context:ContextEnvelope;body:Body}>;
export type Receipt=Readonly<Body & {component_id:string;project_id:string;customer_id:string;software_id:string;standard_base_release_id:string;standard_base_version:string;standard_base_status:string;applied_status:'DRAFT';audit_event_no:string;actor_principal_id:string;created_at:string}>;
const id=(v:unknown):v is string=>typeof v==='string'&&validUuid(v)&&v!=='00000000-0000-0000-0000-000000000000'&&v===v.toLowerCase();
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length<=max&&!/[\p{Cs}\p{Cc}]/u.test(v.replace(/[\n\t]/g,''));
const canonical=(v:unknown,max:number):v is string=>text(v,max)&&!!v.trim()&&v.trim()===v;
const digest=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const targetKeys=['release_id','component_definition_id','base_component_id'];
const derivedKeys=['project_id','customer_id','software_id','standard_base_release_id','standard_base_version','standard_base_status'];
const contextKeys=[...targetKeys,...derivedKeys,'project_code','project_name','customer_code','customer_name','software_code','software_name','release_version','release_status','component_code','component_name','base_component_version'];
const bodyKeys=[...targetKeys,'request_id','version','delta_type','reason','expected_context_digest'];
export function parseTarget(value:unknown):Target|null{const d=record(value);return d&&exactFields(d,targetKeys)&&id(d.release_id)&&id(d.component_definition_id)&&(d.base_component_id===null||id(d.base_component_id))?Object.freeze({...d}) as Target:null;}
export function parseContext(value:unknown,target:Target):ContextEnvelope|null{
 const e=record(value),c=record(e?.context);if(!parseTarget(target)||!e||!exactFields(e,['version','context','context_digest'])||e.version!==1||!digest(e.context_digest)||!c||!exactFields(c,contextKeys)||!targetKeys.every(k=>c[k]===target[k as keyof Target])||!['project_id','customer_id','software_id','standard_base_release_id'].every(k=>id(c[k]))||c.release_status!=='DRAFT'||!canonical(c.standard_base_status,30)||c.standard_base_status==='REVOKED'||!['project_code','project_name','customer_code','customer_name','software_code','software_name','standard_base_version','release_version','component_code','component_name'].every(k=>canonical(c[k],1000))||(target.base_component_id===null?c.base_component_version!==null:(c.base_component_version!==null&&!canonical(c.base_component_version,100))))return null;
 return Object.freeze({version:1,context:Object.freeze({...c}) as Context,context_digest:e.context_digest});
}
export function parseCommand(value:unknown):Command|null{
 const d=record(value),b=record(d?.body);if(!d||!exactFields(d,['context','body'])||!b||!exactFields(b,bodyKeys))return null;
 const target=parseTarget({release_id:b.release_id,component_definition_id:b.component_definition_id,base_component_id:b.base_component_id});if(!target)return null;const context=parseContext(d.context,target);
 if(!context||!id(b.request_id)||!canonical(b.version,100)||/[\p{Cs}\p{Cc}]/u.test(b.version)||!canonical(b.reason,4000)||b.expected_context_digest!==context.context_digest||(target.base_component_id===null?b.delta_type!=='ADDED':!['UNCHANGED','MODIFIED'].includes(b.delta_type as string)))return null;
 const result=Object.freeze({context,body:Object.freeze({...b}) as Body});return new TextEncoder().encode(JSON.stringify(result)).length<=32768?result:null;
}
export function parseReceipt(value:unknown,command:Command,actor?:string):Receipt|null{
 const d=record(value),c=parseCommand(command);if(!d||!c||!exactFields(d,[...bodyKeys,...derivedKeys,'component_id','applied_status','audit_event_no','actor_principal_id','created_at']))return null;
 if(!bodyKeys.every(k=>d[k]===c.body[k as keyof Body])||d.component_id!==c.body.request_id||!id(d.actor_principal_id)||(actor!==undefined&&d.actor_principal_id!==actor)||d.applied_status!=='DRAFT'||!derivedKeys.every(k=>d[k]===c.context.context[k as keyof Context])||d.audit_event_no!=='EVT-ASRC-'+c.body.request_id.replaceAll('-','')||typeof d.created_at!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(d.created_at)||!Number.isFinite(Date.parse(d.created_at)))return null;
 return Object.freeze({...d}) as Receipt;
}
/** Bounded streamed JSON; reject malformed UTF-8 and non-JSON responses. */
export async function readCreationResponse(response:Response):Promise<unknown>{
 if(response.headers.get('content-type')?.split(';')[0].trim().toLowerCase()!=='application/json'||Number(response.headers.get('content-length')||0)>32768){await response.body?.cancel();throw Error('invalid_response');}
 const reader=response.body?.getReader();if(!reader)throw Error('invalid_response');let size=0;const chunks:Uint8Array[]=[];
 try{for(;;){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>32768){await reader.cancel();throw Error('invalid_response');}chunks.push(part.value);}}finally{reader.releaseLock();}
 const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
export type CreationState=Readonly<{phase:'idle'|'sending'|'checking'|'unknown'|'rejected'|'confirmed';receipt:Receipt|null;error?:string}>;
/** Original immutable request, one POST attempt only. Recovery is read-only original-audit lookup. */
export class CreationSubmission{
 readonly command:Command;private attempted=false;private current:CreationState=Object.freeze({phase:'idle',receipt:null});
 constructor(command:unknown,confirmed:boolean,recoveryOnly=false){const c=parseCommand(command);if(!c||confirmed!==true)throw Error('invalid_review');this.command=c;this.attempted=recoveryOnly;if(recoveryOnly)this.current=Object.freeze({phase:'unknown',receipt:null});}
 get state(){return this.current;}
 send(enabled:boolean,fetcher:typeof fetch=fetch){return this.run(false,enabled,fetcher);}
 recover(enabled:boolean,fetcher:typeof fetch=fetch){return this.run(true,enabled,fetcher);}
 private async run(recover:boolean,enabled:boolean,fetcher:typeof fetch):Promise<CreationState>{
  if(recover)this.attempted=true;
  if(['sending','checking','confirmed'].includes(this.current.phase)||(!recover&&this.attempted))return this.current;
  if(!enabled)return this.current=Object.freeze({phase:this.attempted?'unknown':'rejected',receipt:null});
  if(!recover)this.attempted=true;this.current=Object.freeze({phase:recover?'checking':'sending',receipt:null});
  try{const response=await fetcher('/auth/application-component-'+(recover?'receipt':'create'),{method:'POST',body:JSON.stringify(this.command),headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});const value=await readCreationResponse(response);const receipt=[200,201].includes(response.status)?parseReceipt(value,this.command):null;if(receipt)return this.current=Object.freeze({phase:'confirmed',receipt});const error=record(value)?.error;const known:Record<number,string[]>={400:['invalid_request'],401:['session_required'],403:['submission_forbidden','cross_origin_request','read_only_mode'],404:['target_not_found'],409:['context_conflict','request_conflict','base_component_conflict'],413:['request_too_large'],415:['json_required'],422:['invalid_request'],503:['application_component_declaration_disabled']};if(typeof error==='string'&&known[response.status]?.includes(error))return this.current=Object.freeze({phase:recover?'unknown':'rejected',receipt:null,error});}catch{/* A lost reply never establishes failure. */}
  return this.current=Object.freeze({phase:'unknown',receipt:null});
 }
}

/** Digest consistency is not authentication; the fixed authenticated API remains authoritative. */
export async function verifyContextDigest(envelope:ContextEnvelope):Promise<boolean>{
 const context=Object.fromEntries(Object.entries(envelope.context).sort(([a],[b])=>a<b?-1:a>b?1:0));
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify({context,version:1})));
 return Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('')===envelope.context_digest;
}
export function exportCreationRecovery(command:Command,origin:string):string{
 return JSON.stringify({version:1,app_origin:origin,command});
}
export function importCreationRecovery(raw:string,origin:string):Command|null{
 if(new TextEncoder().encode(raw).length>32768)return null;
 try{const value=record(JSON.parse(raw));if(!value||!exactFields(value,['version','app_origin','command'])||value.version!==1||value.app_origin!==origin)return null;return parseCommand(value.command);}catch{return null;}
}
