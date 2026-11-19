import {record, exactFields} from './first-command-transport';
import {parseContext as parseComponentContext, verifyContextDigest} from './application-component-declaration';
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
export const uploadId = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v) && v !== '00000000-0000-0000-0000-000000000000';
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const size = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= MAX_UPLOAD_BYTES;
const text = (v: unknown,max: number): v is string => typeof v === 'string' && !!v.trim() && v.trim() === v && [...v].length <= max && !/[\p{Cs}\p{Cc}]/u.test(v.replace(/[\n\t]/g,''));
const date = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
export type Reservation = Readonly<{version:1;request_id:string;component_id:string;object_id:string;storage_scope_id:string;expected_bytes:number;sha256:string;actor_principal_id:string;state:'RESERVED';created_at:string}>;
export type Stored = Omit<Reservation,'state'> & Readonly<{state:'STORED_PRIVATE';revision:4;stored_at:string}>;
export type Status = Readonly<{version:1;state:string;revision:number;reservation:Reservation;stored_receipt:Stored|null}>;
export type Reserve = Readonly<{request_id:string;component_id:string;expected_bytes:number;sha256:string;expected_context_digest:string;reason:string}>;
export function parseReserve(v:unknown):Reserve|null {
 const d=record(v);return d && exactFields(d,['request_id','component_id','expected_bytes','sha256','expected_context_digest','reason']) && uploadId(d.request_id) && uploadId(d.component_id) && size(d.expected_bytes) && hash(d.sha256) && hash(d.expected_context_digest) && text(d.reason,4000) ? Object.freeze({...d}) as Reserve : null;
}
export async function parseUploadContext(v:unknown,component:string) {
 const e=record(v),c=record(e?.context);if(!e||!c||!uploadId(component))return null;
 const extra=['component_id','component_version','delta_type','storage_scope_id','admission_max_bytes'];
 const base=Object.fromEntries(Object.entries(c).filter(([k])=>!extra.includes(k)));
 const target={release_id:base.release_id,component_definition_id:base.component_definition_id,base_component_id:base.base_component_id};
 // Reuse the exact ASRC context validator without claiming its smaller digest binds the upload context.
 const parsed=parseComponentContext({...e,context:base},target as Parameters<typeof parseComponentContext>[1]);
 if(!parsed||!extra.every(k=>Object.prototype.hasOwnProperty.call(c,k))||c.component_id!==component||!text(c.component_version,100)||!uploadId(c.storage_scope_id)||typeof c.admission_max_bytes!=='number'||!Number.isSafeInteger(c.admission_max_bytes)||c.admission_max_bytes<0||
 (c.base_component_id===null?c.delta_type!=='ADDED':!['UNCHANGED','MODIFIED'].includes(c.delta_type as string)))return null;
 if(!await verifyContextDigest({...parsed,context:c as typeof parsed.context}))return null;
 return Object.freeze({version:1 as const,context:Object.freeze({...c,component_id:component,storage_scope_id:c.storage_scope_id,admission_max_bytes:c.admission_max_bytes}),context_digest:parsed.context_digest});
}
const reservationKeys=['version','request_id','component_id','object_id','storage_scope_id','expected_bytes','sha256','actor_principal_id','state','created_at'];
export function parseReservation(v:unknown,request:string,actor:string):Reservation|null {
 const d=record(v);if(!d||!exactFields(d,reservationKeys)||d.version!==1||d.state!=='RESERVED'||d.request_id!==request||d.actor_principal_id!==actor||!['request_id','component_id','object_id','storage_scope_id','actor_principal_id'].every(k=>uploadId(d[k]))||!size(d.expected_bytes)||!hash(d.sha256)||!date(d.created_at))return null;
 return Object.freeze({...d}) as Reservation;
}
export function parseStored(v:unknown,r:Reservation):Stored|null {
 const d=record(v);if(!d||!exactFields(d,[...reservationKeys,'revision','stored_at'])||!reservationKeys.filter(k=>k!=='state').every(k=>d[k]===r[k as keyof Reservation])||d.state!=='STORED_PRIVATE'||d.revision!==4||!date(d.stored_at)||Date.parse(d.stored_at)<Date.parse(r.created_at))return null;
 return Object.freeze({...d}) as Stored;
}
export function parseStatus(v:unknown,request:string,actor:string):Status|null {
 const d=record(v);if(!d||!exactFields(d,['version','state','revision','reservation','stored_receipt'])||d.version!==1)return null;
 const r=parseReservation(d.reservation,request,actor);if(!r)return null;
 const stages:Record<string,number>={RESERVED:0,RECEIVING:1,STAGED:2,PUBLISHING:3,STORED_PRIVATE:4};
 if(typeof d.state!=='string'||typeof d.revision!=='number'||!Number.isInteger(d.revision)||(d.state==='RECONCILIATION_REQUIRED'?![2,3,4].includes(d.revision):!Object.prototype.hasOwnProperty.call(stages,d.state)||stages[d.state]!==d.revision))return null;
 const stored=d.state==='STORED_PRIVATE'?parseStored(d.stored_receipt,r):null;
 if(d.state==='STORED_PRIVATE'?!stored:d.stored_receipt!==null)return null;
 return Object.freeze({version:1,state:d.state,revision:d.revision,reservation:r,stored_receipt:stored});
}
export async function uploadHash(bytes:Uint8Array):Promise<string> {return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes as BufferSource)),v=>v.toString(16).padStart(2,'0')).join('');}
