'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import type {Fields} from '../lib/command-draft';
import {readCommandResponse} from '../lib/first-command-transport';
import {parsePrivateEvidenceSelectionRequest,parsePrivateEvidenceSelectionResponse,
 type PrivateEvidenceSelectionResponse,type CriteriaEvidenceSelection,type DvpEvidenceSelection,
 type ApprovalEvidenceSelection,type ImpactEvidenceSelection,type ResourceEvidenceSelection} from '../lib/private-evidence-selection';
type Operation='approval'|'acceptance'|'impact'|'resource';
type Data={primary:PrivateEvidenceSelectionResponse;dvp:DvpEvidenceSelection|null};
export default function PrivateEvidenceSelector({operation,fields,contextKey,enabled=false,locked=false,onApply}:{operation:Operation;fields:Fields;contextKey:string;enabled?:boolean;locked?:boolean;onApply:(patch:Partial<Fields>,key:string)=>boolean}){
 const [data,setData]=useState<Data|null>(null),[choice,setChoice]=useState(''),[dvp,setDvp]=useState(''),[message,setMessage]=useState(''),[loading,setLoading]=useState(false);
 const current=useRef({contextKey,enabled,locked,onApply});current.current={contextKey,enabled,locked,onApply};
 const pending=useRef(false),previous=useRef(contextKey),dataRef=useRef(data),choiceRef=useRef(choice),dvpRef=useRef(dvp);dataRef.current=data;choiceRef.current=choice;dvpRef.current=dvp;
 function clear(){dataRef.current=null;choiceRef.current='';dvpRef.current='';setData(null);setChoice('');setDvp('');}
 useEffect(()=>{if(previous.current!==contextKey){previous.current=contextKey;clear();setMessage('');}},[contextKey]);
 const valid=()=>current.current.contextKey===contextKey&&current.current.enabled&&!current.current.locked;
 const unavailable=()=>{clear();setMessage('Private evidence context unavailable or changed. Reload the exact target; no fields were applied.');};
 const supported=operation!=='resource'||!['SUPPLIER','CUSTOMER'].includes(fields.entityType);
 async function load(next:'primary'|'dvp'|null=null){
  if(!valid()||pending.current||!supported)return;
  const old=dataRef.current,page=next==='dvp'?old?.dvp:old?.primary;
  if(next&&(!page||!('next_offset'in page)||page.next_offset===null))return;
  const request=parsePrivateEvidenceSelectionRequest({operation:operation==='acceptance'?(next==='dvp'?'dvp':'criteria'):operation,target:fields.target,
   ...(operation==='resource'?{entity_type:fields.entityType}:operation==='approval'?{}:{limit:5,offset:next&&page&&'next_offset'in page?page.next_offset:0,...(operation==='impact'?{release_id:fields.release}:{})})});
  if(!request){setMessage('Enter the exact target and required evidence context before loading. Nothing was sent.');return;}
  pending.current=true;setLoading(true);setMessage('');if(!next)clear();
  const read=async(input:unknown)=>{const req=parsePrivateEvidenceSelectionRequest(input);if(!req)return null;
   const res=await fetch('/auth/evidence-selection',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(req),credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
   const value=await readCommandResponse(res);return res.status===200?parsePrivateEvidenceSelectionResponse(value,req):null;};
  try{
   const result=await read(request);if(!valid())return;
   if(!result||next&&JSON.stringify(result.context)!==JSON.stringify(old?.primary.context)){unavailable();return;}
   let second=old?.dvp??null;
   if(operation==='acceptance'&&!next){const value=await read({operation:'dvp',target:fields.target,limit:5,offset:0});if(!valid())return;
    if(!value||JSON.stringify(value.context)!==JSON.stringify(result.context)){unavailable();return;}second=value as DvpEvidenceSelection;}
   const fresh=next==='dvp'?{primary:old!.primary,dvp:result as DvpEvidenceSelection}:{primary:result,dvp:second};dataRef.current=fresh;setData(fresh);
  }catch{if(valid())unavailable();}finally{pending.current=false;setLoading(false);}
 }
 function choose(value:string,kind:'primary'|'dvp'){
  if(!valid()||pending.current||dataRef.current!==data||!data)return;
  const page=kind==='dvp'?data.dvp:data.primary;if(!page||!('items'in page))return;
  const key=kind==='dvp'?'dvp_item_id':operation==='acceptance'?'criterion_id':'snapshot_id';
  if(value&&!page.items.some(row=>(row as unknown as Record<string,unknown>)[key]===value))return;
  if(kind==='dvp'){dvpRef.current=value;setDvp(value);}else{choiceRef.current=value;setChoice(value);}
 }
 function apply(){
  if(!valid()||pending.current||!data||dataRef.current!==data)return;
  let patch:Partial<Fields>;
  if(operation==='approval')patch={step:(data.primary as ApprovalEvidenceSelection).step.step_id};
  else if(operation==='acceptance'){if(!choiceRef.current||!dvpRef.current)return;patch={criterion:choiceRef.current,dvp:dvpRef.current};}
  else if(operation==='impact'){if(!choiceRef.current)return;patch={snapshot:choiceRef.current};}
  else{const c=(data.primary as ResourceEvidenceSelection).context;patch={target:c.entity_id,entityType:c.entity_type};}
  if(current.current.onApply(patch,contextKey))setMessage('Selected values applied to preparation only. No request was sent.');
 }
 const shown=previous.current===contextKey?data:null;
 const labels:Record<string,string>={approval_id:'Approval UUID',approval_no:'Approval number',project_id:'Project UUID',target_type:'Target type',target_id:'Target UUID',snapshot_id:'Snapshot ID',status:'Status',change_request_id:'SCR UUID',request_no:'SCR number',issue_id:'Issue UUID',issue_no:'Issue number',release_id:'Release ID',entity_type:'Resource object type',entity_id:'Resource object UUID',entity_ref:'Resource object reference',project_ids:'Project UUIDs'};
 const page=(kind:'primary'|'dvp')=>kind==='dvp'?shown?.dvp:shown?.primary;
 const nextButton=(kind:'primary'|'dvp')=>{const p=page(kind);return p&&'next_offset'in p&&p.next_offset!==null?<button type="button" disabled={!enabled||locked||loading} onClick={()=>load(kind)}><Localized>{kind==='dvp'?'Load next DVP choices page':'Load next evidence choices page'}</Localized></button>:null;};
 return <Localized><section className="panel"><h3><Localized>{'Private evidence selection'}</Localized></h3>
  <p><Localized>{'Read only the explicitly named target. These are current observations, not permission, approval, test results or a guarantee that later submission will succeed.'}</Localized></p>
  {!enabled&&<p><Localized>{'Private selection is disabled or unavailable for this session. Manual preparation remains available.'}</Localized></p>}
  {!supported&&<p><Localized>{'This object has no supported project scope for private selection. Existing manual preparation remains available.'}</Localized></p>}
  <button type="button" disabled={!enabled||locked||loading||!supported} onClick={()=>load()}><Localized>{'Load private evidence context'}</Localized></button>
  {shown&&<><dl className="kv">{Object.entries(shown.primary.context).map(([key,value])=><div key={key}><dt><Localized>{labels[key]??key}</Localized></dt><dd style={{overflowWrap:'anywhere'}}>{value===null?<Localized>{'Not recorded'}</Localized>:['status','target_type','entity_type'].includes(key)?<Localized>{String(value)}</Localized>:Array.isArray(value)?value.join(', '):String(value)}</dd></div>)}</dl>
   {operation==='approval'&&<p><Localized>{'Current approval step'}</Localized>: <code>{(shown.primary as ApprovalEvidenceSelection).step.step_id}</code> · {(shown.primary as ApprovalEvidenceSelection).step.step_order} · <span>{(shown.primary as ApprovalEvidenceSelection).step.role_name}</span> · <Localized>{(shown.primary as ApprovalEvidenceSelection).step.status}</Localized></p>}
   {operation==='acceptance'&&<>
    <label><Localized>{'Select an acceptance criterion from this SCR'}</Localized><select name="selectedCriterion" value={choice} disabled={!enabled||locked||loading} onChange={e=>choose(e.target.value,'primary')}><option value=""><Localized>{'Choose explicitly'}</Localized></option>{(shown.primary as CriteriaEvidenceSelection).items.map(row=><option key={row.criterion_id} value={row.criterion_id}>{row.criterion_no} · {row.description} · {row.criterion_id}</option>)}</select></label>
    {choice&&<p><Localized>{'Selected criterion UUID'}</Localized>: <code>{choice}</code></p>}{nextButton('primary')}
    <label><Localized>{'Select a DVP item from this same SCR'}</Localized><select name="selectedDvp" value={dvp} disabled={!enabled||locked||loading} onChange={e=>choose(e.target.value,'dvp')}><option value=""><Localized>{'Choose explicitly'}</Localized></option>{shown.dvp?.items.map(row=><option key={row.dvp_item_id} value={row.dvp_item_id}>{row.plan_no} / {row.item_no} · {row.title} · {row.dvp_item_id}</option>)}</select></label>
    {dvp&&<p><Localized>{'Selected DVP UUID'}</Localized>: <code>{dvp}</code></p>}{nextButton('dvp')}
   </>}
   {operation==='impact'&&<><label><Localized>{'Select this release’s exact frozen snapshot'}</Localized><select name="selectedSnapshot" value={choice} disabled={!enabled||locked||loading} onChange={e=>choose(e.target.value,'primary')}><option value=""><Localized>{'Choose explicitly'}</Localized></option>{(shown.primary as ImpactEvidenceSelection).items.map(row=><option key={row.snapshot_id} value={row.snapshot_id}>{row.snapshot_no} · {row.snapshot_number} · {row.snapshot_id}</option>)}</select></label>{choice&&<p><Localized>{'Selected snapshot UUID'}</Localized>: <code>{choice}</code></p>}{nextButton('primary')}</>}
   {'items'in shown.primary&&!shown.primary.items.length&&<p><Localized>{'No eligible choices returned on this page.'}</Localized></p>}
   {operation==='acceptance'&&shown.dvp&&!shown.dvp.items.length&&<p><Localized>{'No DVP choices returned on this page.'}</Localized></p>}
   <button type="button" disabled={!enabled||locked||loading||operation==='acceptance'&&(!choice||!dvp)||operation==='impact'&&!choice} onClick={apply}><Localized>{'Apply selected values to preparation'}</Localized></button>
  </>}
  {message&&<p role="status"><Localized>{message}</Localized></p>}
 </section></Localized>;
}
