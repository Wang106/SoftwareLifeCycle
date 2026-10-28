import {validUuid} from './command-draft';
import {record,exactFields} from './first-command-transport';
export const evidenceResourceTypes=['PROJECT','RELEASE','SNAPSHOT','SCR','DVP_ITEM','TEST_RELEASE','DVP_EXECUTION','ISSUE'] as const;
export type EvidenceResourceType=typeof evidenceResourceTypes[number];
export type EvidencePageRequest=Readonly<{limit:number;offset:number}>;
export type PrivateEvidenceSelectionRequest=
 | Readonly<{operation:'approval';target:string}>
 | Readonly<{operation:'criteria'|'dvp';target:string}&EvidencePageRequest>
 | Readonly<{operation:'impact';target:string;release_id:string}&EvidencePageRequest>
 | Readonly<{operation:'resource';target:string;entity_type:EvidenceResourceType}>;
export type EvidencePage<T>=Readonly<{items:readonly T[];limit:number;offset:number;next_offset:number|null}>;
export type ChangeEvidenceContext=Readonly<{change_request_id:string;request_no:string;project_id:string}>;
export type ApprovalEvidenceSelection=Readonly<{context:Readonly<{approval_id:string;approval_no:string;project_id:string;target_type:'RELEASE'|'SCR';target_id:string;snapshot_id:string|null;status:string}>;step:Readonly<{step_id:string;step_order:number;role_name:string;status:'PENDING'|'WAITING'}>}>;
export type CriterionEvidenceItem=Readonly<{criterion_id:string;criterion_no:string;description:string}>;
export type DvpEvidenceItem=Readonly<{dvp_item_id:string;item_no:string;title:string;plan_id:string;plan_no:string}>;
export type SnapshotEvidenceItem=Readonly<{snapshot_id:string;snapshot_no:string;snapshot_number:number;status:'FROZEN'}>;
export type CriteriaEvidenceSelection=Readonly<{context:ChangeEvidenceContext}&EvidencePage<CriterionEvidenceItem>>;
export type DvpEvidenceSelection=Readonly<{context:ChangeEvidenceContext}&EvidencePage<DvpEvidenceItem>>;
export type ImpactEvidenceSelection=Readonly<{context:Readonly<{issue_id:string;issue_no:string;release_id:string;project_id:string}>}&EvidencePage<SnapshotEvidenceItem>>;
export type ResourceEvidenceSelection=Readonly<{context:Readonly<{entity_type:EvidenceResourceType;entity_id:string;entity_ref:string;project_ids:readonly string[]}>}>;
export type PrivateEvidenceSelectionResponse=ApprovalEvidenceSelection|CriteriaEvidenceSelection|DvpEvidenceSelection|ImpactEvidenceSelection|ResourceEvidenceSelection;
const id=(v:unknown):v is string=>typeof v==='string'&&validUuid(v)&&v===v.toLowerCase();
function unicode(s:string):boolean{for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const n=s.charCodeAt(++i);if(!(n>=0xdc00&&n<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
// Preserve stored evidence exactly; only input identifiers have trim/control restrictions.
const raw=(v:unknown,max:number):v is string=>typeof v==='string'&&Array.from(v).length<=max&&!v.includes('\0')&&unicode(v);
const identifier=(v:unknown,max:number):v is string=>raw(v,max)&&v.length>0&&v.trim()===v&&!/[\u0000-\u001f\u007f]/.test(v);
const integer=(v:unknown,min:number,max:number):v is number=>Number.isSafeInteger(v)&&(v as number)>=min&&(v as number)<=max;
export function parsePrivateEvidenceSelectionRequest(value:unknown):PrivateEvidenceSelectionRequest|null{
 const d=record(value);if(!d)return null;
 if(d.operation==='resource')return exactFields(d,['operation','target','entity_type'])&&id(d.target)&&evidenceResourceTypes.includes(d.entity_type as EvidenceResourceType)?Object.freeze({...d}) as PrivateEvidenceSelectionRequest:null;
 if(!identifier(d.target,50))return null;
 if(d.operation==='approval')return exactFields(d,['operation','target'])?Object.freeze({operation:'approval',target:d.target}):null;
 if(!['criteria','dvp','impact'].includes(d.operation as string)||!exactFields(d,['operation','target','limit','offset',...(d.operation==='impact'?['release_id']:[])])||!integer(d.limit,1,50)||!integer(d.offset,0,100000)||(d.operation==='impact'&&!id(d.release_id)))return null;
 return Object.freeze({...d}) as PrivateEvidenceSelectionRequest;
}
export function parsePrivateEvidenceSelectionResponse(value:unknown,request:PrivateEvidenceSelectionRequest):PrivateEvidenceSelectionResponse|null{
 if(!parsePrivateEvidenceSelectionRequest(request))return null;
 const d=record(value),c=record(d?.context);if(!d||!c)return null;
 if(request.operation==='resource'){
  if(!exactFields(d,['context'])||!exactFields(c,['entity_type','entity_id','entity_ref','project_ids'])||c.entity_type!==request.entity_type||c.entity_id!==request.target||!raw(c.entity_ref,512)||!Array.isArray(c.project_ids)||c.project_ids.length===0||c.project_ids.length>1000||!c.project_ids.every(id)||new Set(c.project_ids).size!==c.project_ids.length)return null;
  return Object.freeze({context:Object.freeze({...c,project_ids:Object.freeze([...c.project_ids])})}) as ResourceEvidenceSelection;
 }
 if(!id(c.project_id))return null;
 if(request.operation==='approval'){
  const s=record(d.step);if(!exactFields(d,['context','step'])||!exactFields(c,['approval_id','approval_no','project_id','target_type','target_id','snapshot_id','status'])||!id(c.approval_id)||c.approval_no!==request.target||!['RELEASE','SCR'].includes(c.target_type as string)||!id(c.target_id)||!(c.snapshot_id===null||id(c.snapshot_id))||!identifier(c.status,30)||!s||!exactFields(s,['step_id','step_order','role_name','status'])||!id(s.step_id)||!integer(s.step_order,0,2147483647)||!raw(s.role_name,120)||!['PENDING','WAITING'].includes(s.status as string))return null;
  return Object.freeze({context:Object.freeze({...c}),step:Object.freeze({...s})}) as ApprovalEvidenceSelection;
 }
 if(!exactFields(d,['context','items','limit','offset','next_offset'])||d.limit!==request.limit||d.offset!==request.offset||!Array.isArray(d.items)||d.items.length>request.limit||!(d.next_offset===null||integer(d.next_offset,0,100000)&&d.next_offset===request.offset+request.limit&&d.items.length===request.limit))return null;
 if(request.operation==='impact'){
  if(!exactFields(c,['issue_id','issue_no','release_id','project_id'])||!id(c.issue_id)||c.issue_no!==request.target||c.release_id!==request.release_id)return null;
 }else if(!exactFields(c,['change_request_id','request_no','project_id'])||!id(c.change_request_id)||c.request_no!==request.target)return null;
 const rows:Record<string,unknown>[]=[];const key=request.operation==='criteria'?'criterion_id':request.operation==='dvp'?'dvp_item_id':'snapshot_id';
 for(const item of d.items){const r=record(item);if(!r||!id(r[key]))return null;
  if(request.operation==='criteria'){if(!exactFields(r,['criterion_id','criterion_no','description'])||!raw(r.criterion_no,50)||!raw(r.description,131072))return null;}
  else if(request.operation==='dvp'){if(!exactFields(r,['dvp_item_id','item_no','title','plan_id','plan_no'])||!raw(r.item_no,50)||!raw(r.title,240)||!id(r.plan_id)||!raw(r.plan_no,50))return null;}
  else if(!exactFields(r,['snapshot_id','snapshot_no','snapshot_number','status'])||!raw(r.snapshot_no,80)||!integer(r.snapshot_number,1,2147483647)||r.status!=='FROZEN')return null;
  rows.push(Object.freeze({...r}));
 }
 if(new Set(rows.map(r=>r[key])).size!==rows.length)return null;
 return Object.freeze({context:Object.freeze({...c}),items:Object.freeze(rows),limit:request.limit,offset:request.offset,next_offset:d.next_offset}) as PrivateEvidenceSelectionResponse;
}
/** Fixed private GET paths only; no caller URL, search, identity or business payload. */
export function privateEvidenceSelectionPath(request:PrivateEvidenceSelectionRequest):string{
 const prefix='/api/v1/evidence-selection-context/';
 if(request.operation==='approval')return prefix+'approvals/'+encodeURIComponent(request.target)+'/current-step';
 if(request.operation==='resource')return prefix+'resources/'+request.entity_type+'/'+request.target;
 const query=new URLSearchParams({limit:String(request.limit),offset:String(request.offset)});
 return prefix+(request.operation==='impact'?'issues/'+encodeURIComponent(request.target)+'/releases/'+request.release_id+'/snapshots':'changes/'+encodeURIComponent(request.target)+(request.operation==='criteria'?'/criteria':'/dvp-items'))+'?'+query;
}
