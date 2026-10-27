'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import type {Fields} from '../lib/command-draft';
import {readCommandResponse} from '../lib/first-command-transport';
import {parsePrivateDistributionSelectionRequest,parsePrivateDistributionSelectionResponse,
 type PrivateDistributionSelectionResponse,type DeliverySelection,type DistributionSelection,type AuthorizationSelection,
 type DeliverySelectionItem,type AuthorizationSelectionItem} from '../lib/private-distribution-selection';
type Operation='delivery'|'distribution'|'authorization';
export default function PrivateDistributionSelector({operation,fields,contextKey,enabled=false,locked=false,onApply}:{
 operation:Operation;fields:Fields;contextKey:string;enabled?:boolean;locked?:boolean;onApply:(patch:Partial<Fields>,contextKey:string)=>boolean;
}){
 const [response,setResponse]=useState<PrivateDistributionSelectionResponse|null>(null),[message,setMessage]=useState(''),[loading,setLoading]=useState(false);
 const [selected,setSelected]=useState<readonly DeliverySelectionItem[]>([]),[line,setLine]=useState<AuthorizationSelectionItem|null>(null);
 const pending=useRef(false),current=useRef({contextKey,enabled,locked,onApply});current.current={contextKey,enabled,locked,onApply};
 const previousKey=useRef(contextKey),selection=useRef(selected),chosenLine=useRef(line);selection.current=selected;chosenLine.current=line;
 const responseRef=useRef(response);responseRef.current=response;
 useEffect(()=>{if(previousKey.current!==contextKey){previousKey.current=contextKey;responseRef.current=null;selection.current=[];chosenLine.current=null;setResponse(null);setSelected([]);setLine(null);setMessage('');}},[contextKey]);
 const valid=()=>current.current.contextKey===contextKey&&current.current.enabled&&!current.current.locked;
 async function load(next=false){
  if(!valid()||pending.current)return;
  const old=responseRef.current,page=old&&'next_offset' in old?old:null;
  if(next&&(!page||page.next_offset===null))return;
  const request=parsePrivateDistributionSelectionRequest({operation,target_id:fields.target,...(operation==='distribution'?{}:{limit:5,offset:next?page!.next_offset:0,
   expected_snapshot_id:next?old!.context.snapshot_id:null,expected_decision_id:next?old!.context.release_decision_id:null,
   ...(operation==='delivery'?{recipient_type:fields.recipientType,recipient_code:fields.recipientCode,purpose:fields.purpose}:{})})});
  if(!request){setMessage('Enter the exact target and required recipient/purpose before loading. Nothing was sent.');return;}
  pending.current=true;setLoading(true);setMessage('');
  if(!next){responseRef.current=null;selection.current=[];chosenLine.current=null;setResponse(null);setSelected([]);setLine(null);}
  try{
   const res=await fetch('/auth/distribution-selection',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(request),credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
   const value=await readCommandResponse(res),parsed=res.status===200?parsePrivateDistributionSelectionResponse(value,request):null;
   if(!valid())return;
   if(!parsed||(next&&JSON.stringify(parsed.context)!==JSON.stringify(old?.context))){responseRef.current=null;selection.current=[];chosenLine.current=null;setResponse(null);setSelected([]);setLine(null);setMessage('Private selection unavailable or changed. Reload the exact context; no fields were applied.');return;}
   if(next&&operation==='authorization'){chosenLine.current=null;setLine(null);}
   responseRef.current=parsed;setResponse(parsed);
  }catch{if(valid()){responseRef.current=null;selection.current=[];chosenLine.current=null;setResponse(null);setSelected([]);setLine(null);setMessage('Private selection unavailable or changed. Reload the exact context; no fields were applied.');}}
  finally{pending.current=false;setLoading(false);}
 }
 function chooseArtifact(row:DeliverySelectionItem,checked:boolean){
  if(!valid()||pending.current||responseRef.current!==response)return;
  const next=selection.current.filter(item=>item.snapshot_artifact_id!==row.snapshot_artifact_id);
  if(checked){if(next.length>=200){setMessage('Select at most 200 artifacts.');return;}next.push(row);}
  selection.current=next;setSelected(next);setMessage('');
 }
 function chooseLine(id:string){
  if(!valid()||pending.current||responseRef.current!==response)return;
  const row=(response as AuthorizationSelection|null)?.items.find(item=>item.line_id===id)??null;chosenLine.current=row;setLine(row);
 }
 function apply(){
  if(!valid()||pending.current||!response||responseRef.current!==response)return;
  let patch:Partial<Fields>;
  if(operation==='delivery'){
   if(!selection.current.length)return;const c=(response as DeliverySelection).context;
   patch={artifacts:selection.current.map(row=>row.snapshot_artifact_id).join('\n'),recipientType:c.recipient_type,recipientCode:c.recipient_code,purpose:c.purpose};
  }else if(operation==='distribution'){const c=(response as DistributionSelection).context;patch={recipientType:c.recipient_type,recipientCode:c.recipient_code};}
  else{const c=(response as AuthorizationSelection).context,row=chosenLine.current;if(!row)return;patch={release:c.release_id,customer:c.customer_id,project:c.project_id,purpose:c.purpose,site:row.site_code,line:row.line_code};}
  if(current.current.onApply(patch,contextKey))setMessage('Selected values applied to preparation only. No request was sent.');
 }
 const labels:Record<string,string>={release_id:'Release ID',snapshot_id:'Snapshot ID',release_decision_id:'Release decision UUID',project_id:'Project UUID',recipient_type:'Recipient type',recipient_code:'Recipient code',purpose:'Purpose',delivery_package_id:'Delivery package UUID',package_no:'Package number',revision:'Package revision',status:'Status',distribution_id:'Distribution UUID',distribution_no:'Distribution number',customer_id:'Customer UUID'};
 const shown=previousKey.current===contextKey?response:null;
 return <Localized><section className="panel"><h3><Localized>{'Private distribution selection'}</Localized></h3>
  <p><Localized>{'Load only the exact private target. Selection is not permission, approval or a pinned write decision; submission revalidates current state and may reject changes.'}</Localized></p>
  {!enabled&&<p><Localized>{'Private selection is disabled or unavailable for this session. Manual preparation remains available.'}</Localized></p>}
  <button type="button" disabled={!enabled||locked||loading} onClick={()=>load()}><Localized>{'Load private selection context'}</Localized></button>
  {shown&&<><dl className="kv">{Object.entries(shown.context).map(([key,value])=><div key={key}><dt><Localized>{labels[key]??key}</Localized></dt><dd style={{overflowWrap:'anywhere'}}>{value===null?<Localized>{'Not recorded'}</Localized>:String(value)}</dd></div>)}</dl>
   {operation==='delivery'&&<><p><Localized>{'Choose eligible frozen artifacts explicitly. File names and hashes are original evidence.'}</Localized></p>
    {(shown as DeliverySelection).items.map(row=><label key={row.snapshot_artifact_id} style={{overflowWrap:'anywhere'}}><input type="checkbox" name="selectedArtifact" value={row.snapshot_artifact_id} checked={selected.some(item=>item.snapshot_artifact_id===row.snapshot_artifact_id)} disabled={locked||loading||!enabled} onChange={e=>chooseArtifact(row,e.target.checked)}/>{row.filename} · {row.artifact_type} · {row.component_code} · {row.component_version??'—'} · <code>{row.snapshot_artifact_id}</code> · <code>{row.sha256}</code> · <Localized>{row.policy_decision}</Localized></label>)}
    <p><Localized>{'Selected artifacts'}</Localized>: {selected.length}</p><ul>{selected.map(row=><li key={row.snapshot_artifact_id}>{row.filename} · <code>{row.snapshot_artifact_id}</code></li>)}</ul></>}
   {operation==='authorization'&&<label><Localized>{'Select an active site and line in this exact project'}</Localized><select name="selectedLine" value={line?.line_id??''} disabled={locked||loading||!enabled} onChange={e=>chooseLine(e.target.value)}><option value=""><Localized>{'Select a site and line'}</Localized></option>{(shown as AuthorizationSelection).items.map(row=><option key={row.line_id} value={row.line_id}>{row.site_name} · {row.site_code} / {row.line_name} · {row.line_code} / {row.line_id}</option>)}</select></label>}
   {'items' in shown&&!shown.items.length&&<p><Localized>{'No eligible choices returned on this page.'}</Localized></p>}
   {'next_offset' in shown&&shown.next_offset!==null&&<button type="button" disabled={!enabled||locked||loading} onClick={()=>load(true)}><Localized>{'Load next private choices page'}</Localized></button>}
   <button type="button" disabled={!enabled||locked||loading||operation==='delivery'&&!selected.length||operation==='authorization'&&!line} onClick={apply}><Localized>{'Apply selected values to preparation'}</Localized></button>
  </>}
  {message&&<p role="status"><Localized>{message}</Localized></p>}
 </section></Localized>;
}
