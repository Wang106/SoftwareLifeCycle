'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {Localized} from './localized';
import {exportBatchCorrectionRecovery,importBatchCorrectionRecovery,batchCorrectionRecoveryTextLimit,type ImportedBatchCorrectionRecovery} from '../lib/batch-correction-recovery';
import {readCommandResponse} from '../lib/first-command-transport';
import {parseBatchCorrectionTarget,parseBatchCorrectionContext,parseBatchCorrectionCommand,confirmBatchCorrection,
  BatchCorrectionSubmission,type BatchCorrectionContext,type BatchCorrectionReview,type BatchCorrectionState} from '../lib/batch-correction-transport';

type Fields={started_at:string;ended_at:string;changeover_id:string;note:string;correction_reason:string};
const blank:Fields={started_at:'',ended_at:'',changeover_id:'',note:'',correction_reason:''};
const fromContext=(context:BatchCorrectionContext):Fields=>({started_at:context.started_at??'',ended_at:context.ended_at??'',changeover_id:context.changeover_id??'',note:context.note??'',correction_reason:''});

export function BatchCorrectionResult({state}:{state:BatchCorrectionState}){
  const receipt=state.receipt;
  const labels:Record<string,string>={batch_id:'Batch ID',batch_no:'Batch number',release_id:'Release ID',snapshot_id:'Snapshot ID',started_at:'Started',ended_at:'Ended',changeover_id:'Changeover ID',note:'Note',correction_reason:'Correction reason',revision:'Revision',predecessor_id:'Predecessor correction ID'};
  return <Localized><section className="panel" aria-live="polite">
    <h3><Localized>{'Batch correction result'}</Localized></h3>
    <p><Localized>{'Operation phase'}</Localized>: <Localized>{state.phase}</Localized></p>
    {state.phase==='unknown'&&<p className="notice"><Localized>{'The original outcome is unknown. Keep this request and query its original audit; do not prepare a replacement.'}</Localized></p>}
    {state.phase==='rejected'&&<p><Localized>{'This attempt was rejected before a confirmed result. Reload private context before preparing another request.'}</Localized></p>}
    {state.error&&<p><Localized>{'Result code'}</Localized>: <code>{state.error}</code></p>}
    {receipt&&<><p><Localized>{'This receipt confirms the original recorded correction only, not current facts, permission or physical software changes.'}</Localized></p>
      <dl className="kv">{Object.entries(receipt.result).map(([key,value])=><div key={key}><dt><Localized>{labels[key]??key}</Localized></dt><dd style={{overflowWrap:'anywhere'}}>{value===null?<Localized>{'Not recorded'}</Localized>:String(value)}</dd></div>)}</dl>
      <Link href={'/activity/'+encodeURIComponent(receipt.audit_event_no)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open original correction audit'}</Localized></Link>
    </>}
  </section></Localized>;
}

export default function BatchCorrectionWorkbench({deploymentNo,batchNo,contextEnabled=false,submissionEnabled=false,recoveryEnabled=false}:{
  deploymentNo:string;batchNo:string;contextEnabled?:boolean;submissionEnabled?:boolean;recoveryEnabled?:boolean;
}){
  const [context,setContext]=useState<BatchCorrectionContext|null>(null),[fields,setFields]=useState<Fields>(blank);
  const [review,setReview]=useState<BatchCorrectionReview|null>(null),[result,setResult]=useState<BatchCorrectionState|null>(null);
  const [message,setMessage]=useState(''),[loading,setLoading]=useState(false);
  const [copying,setCopying]=useState(false),[importText,setImportText]=useState('');
  const imported=useRef(false),copyPending=useRef(false),importSource=useRef('');
  const controller=useRef<BatchCorrectionSubmission|ImportedBatchCorrectionRecovery|null>(null),loadPending=useRef(false);
  const capability=useRef({context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled});
  capability.current={context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled};
  const key=JSON.stringify([deploymentNo,batchNo]),currentKey=useRef(key),previousKey=useRef(key);currentKey.current=key;
  const current=result?.review??(previousKey.current===key?review:null),active=useRef(current);active.current=current;
  const currentContext=useRef(context),draftFields=useRef(fields);currentContext.current=context;draftFields.current=fields;
  const busy=copying||loading||result?.phase==='sending'||result?.phase==='checking';
  useEffect(()=>{if(previousKey.current===key)return;previousKey.current=key;
    if(!controller.current){setContext(null);setFields(blank);setReview(null);setMessage('');importSource.current='';setImportText('');}
  },[key]);
  useEffect(()=>{if(!result||!['sending','checking','unknown'].includes(result.phase))return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[result?.phase]);
  function matches(){return active.current===current&&(controller.current?controller.current.state.review===current:currentKey.current===key);}
  async function loadContext(){
    if(copyPending.current||!capability.current.context||loadPending.current||controller.current||currentKey.current!==key)return;
    const target=parseBatchCorrectionTarget({deployment_no:deploymentNo,batch_no:batchNo});
    if(!target){setMessage('The private correction target is invalid. Nothing was sent.');return;}
    loadPending.current=true;setLoading(true);active.current=null;setReview(null);setContext(null);setMessage('');
    try{
      const response=await fetch('/auth/batch-correction-context',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},
        body:JSON.stringify(target),credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response),next=response.status===200?parseBatchCorrectionContext(value,target):null;
      if(currentKey.current!==key||controller.current)return;
      if(!next||!capability.current.context){setMessage('Private correction context could not be loaded. Nothing was sent.');return;}
      currentContext.current=next;setContext(next);setFields(fromContext(next));
    }catch{if(currentKey.current===key&&!controller.current)setMessage('Private correction context could not be loaded. Nothing was sent.');}
    finally{loadPending.current=false;setLoading(false);}
  }
  function edit(name:keyof Fields,value:string){
    if(copyPending.current||controller.current||loadPending.current||currentKey.current!==key)return;
    active.current=null;draftFields.current={...fields,[name]:value};setFields(draftFields.current);setReview(null);setMessage('');
  }
  function prepare(){
    if(copyPending.current||!context||context!==currentContext.current||draftFields.current!==fields||controller.current||loadPending.current||currentKey.current!==key)return;
    const command=parseBatchCorrectionCommand({operation:'batch-correction',target:{deployment_no:context.deployment_no,batch_no:context.batch_no},context,
      body:{request_id:crypto.randomUUID(),expected_revision:context.expected_revision,predecessor_id:context.predecessor_id,
        started_at:fields.started_at||null,ended_at:fields.ended_at||null,changeover_id:fields.changeover_id||null,note:fields.note||null,correction_reason:fields.correction_reason}});
    if(!command){setMessage('The batch correction values are invalid. Nothing was sent.');return;}
    const next=confirmBatchCorrection(command,false);active.current=next;setReview(next);setMessage('Review the exact context and replacement values before confirming.');
  }
  function confirm(checked:boolean){
    if(copyPending.current||!checked||!current||!matches()||controller.current||loadPending.current)return;
    try{const next=confirmBatchCorrection(current.command,true);controller.current=new BatchCorrectionSubmission(next);
      active.current=controller.current.state.review;setReview(next);setResult(controller.current.state);setMessage('');
    }catch{setMessage('The batch correction values are invalid. Nothing was sent.');}
  }
  async function run(mode:'send'|'recover'){
    if(mode==='send'&&imported.current)return;
    if(copyPending.current||!current?.confirmed||!matches()||!controller.current||loadPending.current||!(mode==='send'?capability.current.submit:capability.current.recover))return;
    if(mode==='send'&&!('send' in controller.current))return;
    const pending=mode==='send'&&'send' in controller.current?controller.current.send(capability.current.submit):controller.current.recover(capability.current.recover);
    setResult(controller.current.state);setMessage('');setResult(await pending);
  }
  function reset(){
    if(copyPending.current||loadPending.current||!matches()||(controller.current&&!['idle','rejected','confirmed'].includes(controller.current.state.phase)))return;
    controller.current=null;imported.current=false;importSource.current='';setImportText('');active.current=null;currentContext.current=null;setContext(null);setFields(blank);setReview(null);setResult(null);setMessage('Reload private context before preparing another request.');
  }
  async function copyRecovery(){
    if(!current?.confirmed||!matches()||copyPending.current||loadPending.current||['sending','checking'].includes(controller.current?.state.phase??''))return;
    copyPending.current=true;setCopying(true);
    try{await navigator.clipboard.writeText(exportBatchCorrectionRecovery(current,window.location.origin));
      if(matches())setMessage('Recovery text copied. It contains business data, not proof of execution. Store it securely.');
    }catch{if(matches())setMessage('Clipboard unavailable. Select and copy the recovery text below.');}
    finally{copyPending.current=false;setCopying(false);}
  }
  function stageRecovery(){
    if(copyPending.current||loadPending.current||controller.current||active.current||currentKey.current!==key||importSource.current!==importText)return;
    try{
      const restored=importBatchCorrectionRecovery(importText,window.location.origin),target=restored.state.command.target;
      if(target.deployment_no!==deploymentNo||target.batch_no!==batchNo)throw Error('wrong_target');
      controller.current=restored;imported.current=true;active.current=restored.state.review;currentContext.current=null;
      setContext(null);setFields(blank);setReview(restored.state.review);setResult(restored.state);setImportText('');importSource.current='';setMessage('');
    }catch{setMessage('Recovery text is invalid or does not match this site and batch. Nothing was sent.');}
  }
  let recoveryText='';
  try{if(current?.confirmed&&typeof window!=='undefined'&&window.location?.origin)recoveryText=exportBatchCorrectionRecovery(current,window.location.origin);}
  catch{ /* Invalid manual exports never break preparation. */ }
  const shown=current?.command.context??context;
  const input=(name:keyof Fields,label:string,maxLength:number)=><Localized><label><Localized>{label}</Localized><input name={name} maxLength={maxLength} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label></Localized>;
  return <Localized><section className="panel">
    <h2><Localized>{'Correct recorded batch facts'}</Localized></h2>
    <p><Localized>{'This appends a correction to recorded batch facts. It does not change software attribution or perform physical production actions.'}</Localized></p>
    <p>{current?.command.target.deployment_no??deploymentNo} · {current?.command.target.batch_no??batchNo}</p>
    {!submissionEnabled&&<p className="notice"><Localized>{'Batch correction submission is disabled or unavailable for this session.'}</Localized></p>}
    <p><Localized>{'Public history is not permission. Load private authenticated context before preparing a correction.'}</Localized></p>
    {!controller.current&&<button type="button" onClick={loadContext} disabled={!contextEnabled||busy}><Localized>{'Load private correction context'}</Localized></button>}
    {shown&&<section><h3><Localized>{imported.current?'Imported batch context — unverified evidence':'Private correction context'}</Localized></h3>
      <p><Localized>{'Batch ID'}</Localized>: <code>{shown.batch_id}</code></p>
      <p><Localized>{'Immutable release and snapshot'}</Localized>: <code>{shown.release_id}</code> · <code>{shown.snapshot_id}</code></p>
      <p><Localized>{'Current revision'}</Localized>: {shown.expected_revision} · <Localized>{'Predecessor correction ID'}</Localized>: <code>{shown.predecessor_id??'—'}</code></p>
      <p><Localized>{'History state'}</Localized>: <Localized>{shown.history_state}</Localized></p>
    </section>}
    {context&&<form className="commandform" onSubmit={e=>{e.preventDefault();prepare();}}><fieldset className="commandfields" disabled={busy||controller.current!==null}>
      {input('started_at','Corrected start time (explicit zone)',40)}{input('ended_at','Corrected end time (explicit zone)',40)}
      <p><Localized>{'Blank start or end time preserves the current recorded time; it does not clear it.'}</Localized></p>
      {input('changeover_id','Corrected changeover UUID (blank clears link)',36)}
      <label><Localized>{'Corrected note (blank clears note)'}</Localized><textarea name="note" maxLength={8192} value={fields.note} onChange={e=>edit('note',e.target.value)}/></label>
      <p><Localized>{'The complete context and request must fit the transport limit. Long existing notes are never silently truncated.'}</Localized></p>
      <label><Localized>{'Correction reason'}</Localized><textarea name="correction_reason" required maxLength={2000} value={fields.correction_reason} onChange={e=>edit('correction_reason',e.target.value)}/></label>
      <button type="submit" disabled={current!==null}><Localized>{'Prepare batch correction'}</Localized></button>
    </fieldset></form>}
    {current&&<section><h3><Localized>{'Review exact batch correction'}</Localized></h3>
      <p><Localized>{'Request ID'}</Localized>: <code>{current.command.body.request_id}</code></p>
      <p><Localized>{'Expected revision'}</Localized>: {current.command.body.expected_revision}</p>
      <p><Localized>{'The confirmed request ID, predecessor and body remain frozen. Unknown outcomes cannot be replaced by refreshed context.'}</Localized></p>
      <pre><code>{JSON.stringify(current.command,null,2)}</code></pre>
      {!controller.current&&<label><input type="checkbox" checked={false} disabled={busy} onChange={e=>confirm(e.target.checked)}/><Localized>{'I confirm this exact batch, revision, predecessor, replacement values, reason and request ID.'}</Localized></label>}
      {!imported.current&&result?.phase==='idle'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Send confirmed batch correction'}</Localized></button>}
      {!imported.current&&result?.phase==='unknown'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Retry original batch correction'}</Localized></button>}
      {result&&['unknown','rejected'].includes(result.phase)&&<button type="button" disabled={!recoveryEnabled||busy} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>}
      {(!result||['idle','rejected','confirmed'].includes(result.phase))&&<button type="button" disabled={busy} onClick={reset}><Localized>{'Reload context for a new correction'}</Localized></button>}
      <button type="button" disabled={!current.confirmed||busy} onClick={copyRecovery}><Localized>{'Copy batch correction recovery text'}</Localized></button>
      {recoveryText&&<><p className="muted"><Localized>{'Batch recovery text contains business metadata, the original context and request, not proof of execution or permission. Store it securely.'}</Localized></p><pre><code>{recoveryText}</code></pre></>}
      {imported.current&&<p className="notice"><Localized>{'Imported correction recovery is read-only. Nothing was sent; explicitly query your original audit after signing in.'}</Localized></p>}
    </section>}
    {!current&&!result&&<section><h3><Localized>{'Restore an original correction audit query'}</Localized></h3>
      <p><Localized>{'Paste recovery text for this exact site and batch. Import never submits, retries or queries automatically.'}</Localized></p>
      <label><Localized>{'Correction recovery text'}</Localized><textarea name="importText" maxLength={batchCorrectionRecoveryTextLimit} value={importText} onChange={e=>{
        if(copyPending.current||loadPending.current||controller.current||currentKey.current!==key)return;
        importSource.current=e.target.value;setImportText(e.target.value);setMessage('');
      }}/></label>
      <button type="button" disabled={busy||!importText} onClick={stageRecovery}><Localized>{'Import correction recovery without sending'}</Localized></button>
    </section>}
    {message&&<p role="status"><Localized>{message}</Localized></p>}
    {result&&<BatchCorrectionResult state={result}/>}
    <p><Localized>{'Request state is kept only in this page. Manually save recovery text before leaving an unknown outcome; nothing is stored automatically.'}</Localized></p>
  </section></Localized>;
}
