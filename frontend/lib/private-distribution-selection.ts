import {validUuid} from './command-draft';
import {record,exactFields} from './first-command-transport';
export type SelectionPageRequest=Readonly<{limit:number;offset:number;expected_snapshot_id:string|null;expected_decision_id:string|null}>;
export type PrivateDistributionSelectionRequest=
 | Readonly<{operation:'delivery';target_id:string;recipient_type:string;recipient_code:string;purpose:string}&SelectionPageRequest>
 | Readonly<{operation:'distribution';target_id:string}>
 | Readonly<{operation:'authorization';target_id:string}&SelectionPageRequest>;
export type SelectionBaseContext=Readonly<{release_id:string;snapshot_id:string;release_decision_id:string|null;project_id:string}>;
export type DeliverySelectionContext=Readonly<SelectionBaseContext&{release_decision_id:string;recipient_type:string;recipient_code:string;purpose:string}>;
export type DistributionSelectionContext=Readonly<SelectionBaseContext&{release_decision_id:null;delivery_package_id:string;package_no:string;revision:number;recipient_type:string;recipient_code:string;purpose:string;status:string}>;
export type AuthorizationSelectionContext=Readonly<SelectionBaseContext&{release_decision_id:string;distribution_id:string;distribution_no:string;delivery_package_id:string;package_no:string;revision:number;customer_id:string;purpose:string;recipient_type:string;recipient_code:string}>;
export type DeliverySelectionItem=Readonly<{snapshot_artifact_id:string;filename:string;artifact_type:string;component_code:string;component_version:string|null;sha256:string;policy_decision:'ALLOW'|'APPROVAL_REQUIRED'}>;
export type AuthorizationSelectionItem=Readonly<{site_id:string;site_code:string;site_name:string;line_id:string;line_code:string;line_name:string}>;
export type SelectionPage<T>=Readonly<{items:readonly T[];limit:number;offset:number;next_offset:number|null}>;
export type DeliverySelection=Readonly<{context:DeliverySelectionContext}&SelectionPage<DeliverySelectionItem>>;
export type DistributionSelection=Readonly<{context:DistributionSelectionContext}>;
export type AuthorizationSelection=Readonly<{context:AuthorizationSelectionContext}&SelectionPage<AuthorizationSelectionItem>>;
export type PrivateDistributionSelectionResponse=DeliverySelection|DistributionSelection|AuthorizationSelection;
const id=(v:unknown):v is string=>typeof v==='string'&&validUuid(v)&&v===v.toLowerCase();
function unicode(s:string):boolean{for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const n=s.charCodeAt(++i);if(!(n>=0xdc00&&n<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length>0&&Array.from(v).length<=max&&v.trim()===v&&!/[\u0000-\u001f\u007f]/.test(v)&&unicode(v);
const integer=(v:unknown,min:number,max:number):v is number=>Number.isSafeInteger(v)&&(v as number)>=min&&(v as number)<=max;
const pageFields=['limit','offset','expected_snapshot_id','expected_decision_id'];
export function parsePrivateDistributionSelectionRequest(value:unknown):PrivateDistributionSelectionRequest|null{
 const d=record(value);if(!d||!id(d.target_id))return null;
 if(d.operation==='distribution')return exactFields(d,['operation','target_id'])?Object.freeze({operation:'distribution',target_id:d.target_id}):null;
 if(!['delivery','authorization'].includes(d.operation as string)||!exactFields(d,['operation','target_id',...pageFields,...(d.operation==='delivery'?['recipient_type','recipient_code','purpose']:[])])||!integer(d.limit,1,50)||!integer(d.offset,0,100000))return null;
 const unpinned=d.expected_snapshot_id===null&&d.expected_decision_id===null;
 if(!(unpinned&&d.offset===0)&&!(id(d.expected_snapshot_id)&&id(d.expected_decision_id)))return null;
 const page={limit:d.limit,offset:d.offset,expected_snapshot_id:d.expected_snapshot_id as string|null,expected_decision_id:d.expected_decision_id as string|null};
 if(d.operation==='authorization')return Object.freeze({operation:'authorization',target_id:d.target_id,...page});
 if(!text(d.recipient_type,50)||!text(d.recipient_code,80)||!text(d.purpose,50))return null;
 return Object.freeze({operation:'delivery',target_id:d.target_id,recipient_type:d.recipient_type,recipient_code:d.recipient_code,purpose:d.purpose,...page});
}
const baseFields=['release_id','snapshot_id','release_decision_id','project_id'];
export function parsePrivateDistributionSelectionResponse(value:unknown,request:PrivateDistributionSelectionRequest):PrivateDistributionSelectionResponse|null{
 if(!parsePrivateDistributionSelectionRequest(request))return null;
 const d=record(value),c=record(d?.context);if(!d||!c||!baseFields.filter(k=>k!=='release_decision_id').every(k=>id(c[k]))||(request.operation==='distribution'?c.release_decision_id!==null:!id(c.release_decision_id)))return null;
 const paginated=request.operation!=='distribution';
 if(!exactFields(d,paginated?['context','items','limit','offset','next_offset']:['context']))return null;
 if(!text(c.recipient_type,50)||!text(c.recipient_code,80)||!text(c.purpose,50))return null;
 if(request.operation==='distribution'){
  if(!exactFields(c,[...baseFields,'delivery_package_id','package_no','revision','recipient_type','recipient_code','purpose','status'])||c.delivery_package_id!==request.target_id||!text(c.package_no,50)||!integer(c.revision,1,2147483647)||!['READY','APPROVED'].includes(c.status as string))return null;
  return Object.freeze({context:Object.freeze({...c}) as DistributionSelectionContext});
 }
 if(d.limit!==request.limit||d.offset!==request.offset||!Array.isArray(d.items)||d.items.length>request.limit||!(d.next_offset===null||integer(d.next_offset,0,100000)&&d.next_offset===request.offset+request.limit&&d.items.length===request.limit))return null;
 if(request.expected_snapshot_id!==null&&(c.snapshot_id!==request.expected_snapshot_id||c.release_decision_id!==request.expected_decision_id))return null;
 const items:Record<string,unknown>[]=[];
 if(request.operation==='delivery'){
  if(!exactFields(c,[...baseFields,'recipient_type','recipient_code','purpose'])||c.release_id!==request.target_id||c.recipient_type!==request.recipient_type||c.recipient_code!==request.recipient_code||c.purpose!==request.purpose)return null;
  for(const value of d.items){const row=record(value);if(!row||!exactFields(row,['snapshot_artifact_id','filename','artifact_type','component_code','component_version','sha256','policy_decision'])||!id(row.snapshot_artifact_id)||!text(row.filename,255)||!text(row.artifact_type,80)||!text(row.component_code,80)||!(row.component_version===null||text(row.component_version,100))||typeof row.sha256!=='string'||!/^[0-9a-f]{64}$/.test(row.sha256)||!['ALLOW','APPROVAL_REQUIRED'].includes(row.policy_decision as string))return null;items.push(Object.freeze({...row}));}
  if(new Set(items.map(row=>row.snapshot_artifact_id)).size!==items.length)return null;
  return Object.freeze({context:Object.freeze({...c}) as DeliverySelectionContext,items:Object.freeze(items) as readonly DeliverySelectionItem[],limit:request.limit,offset:request.offset,next_offset:d.next_offset as number|null});
 }
 if(!exactFields(c,[...baseFields,'distribution_id','distribution_no','delivery_package_id','package_no','revision','customer_id','purpose','recipient_type','recipient_code'])||c.distribution_id!==request.target_id||!id(c.delivery_package_id)||!id(c.customer_id)||!text(c.distribution_no,50)||!text(c.package_no,50)||!integer(c.revision,1,2147483647))return null;
 for(const value of d.items){const row=record(value);if(!row||!exactFields(row,['site_id','site_code','site_name','line_id','line_code','line_name'])||!id(row.site_id)||!id(row.line_id)||!text(row.site_code,80)||!text(row.line_code,80)||!text(row.site_name,200)||!text(row.line_name,200))return null;items.push(Object.freeze({...row}));}
 if(new Set(items.map(row=>row.line_id)).size!==items.length)return null;
 return Object.freeze({context:Object.freeze({...c}) as AuthorizationSelectionContext,items:Object.freeze(items) as readonly AuthorizationSelectionItem[],limit:request.limit,offset:request.offset,next_offset:d.next_offset as number|null});
}

/** Fixed authenticated GET paths. No caller-controlled URLs, sorts or unrelated filters. */
export function privateDistributionSelectionPath(request:PrivateDistributionSelectionRequest):string {
 if(request.operation==='distribution')return '/api/v1/selection-context/deliveries/'+request.target_id;
 const query=new URLSearchParams();
 if(request.operation==='delivery'){query.set('recipient_type',request.recipient_type);query.set('recipient_code',request.recipient_code);query.set('purpose',request.purpose);}
 query.set('limit',String(request.limit));query.set('offset',String(request.offset));
 if(request.expected_snapshot_id!==null){query.set('expected_snapshot_id',request.expected_snapshot_id);query.set('expected_decision_id',request.expected_decision_id!);}
 return '/api/v1/selection-context/'+(request.operation==='delivery'?'releases/':'distributions/')+request.target_id+(request.operation==='delivery'?'/delivery-artifacts':'/authorization-scope')+'?'+query;
}
