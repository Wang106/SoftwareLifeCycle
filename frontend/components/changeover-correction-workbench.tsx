'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {Localized} from './localized';
import {readCommandResponse} from '../lib/first-command-transport';
import {parseChangeoverCorrectionTarget,parseChangeoverCorrectionContext,parseChangeoverCorrectionCommand,confirmChangeoverCorrection,
  ChangeoverCorrectionSubmission,type ChangeoverCorrectionContext,type ChangeoverCorrectionReview,type ChangeoverCorrectionState} from '../lib/changeover-correction-transport';

type Fields={from_release_id:string;changed_at:string;note:string;correction_reason:string};
const blank:Fields={from_release_id:'',changed_at:'',note:'',correction_reason:''};
const fromContext=(context:ChangeoverCorrectionContext):Fields=>({from_release_id:context.from_release_id??'',changed_at:context.changed_at??'',note:context.note??'',correction_reason:''});

export function ChangeoverCorrectionResult({state}:{state:ChangeoverCorrectionState}){
  const receipt=state.receipt;
  const labels:Record<string,string>={changeover_id:'Changeover ID',changeover_no:'Changeover number',from_release_id:'From release ID',to_release_id:'To release ID',changed_at:'Changed at',note:'Note',correction_reason:'Correction reason',revision:'Revision',predecessor_id:'Predecessor correction ID'};
  return <Localized><section className="panel" aria-live="polite">
    <h3><Localized>{'Changeover correction result'}</Localized></h3>
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

export default function ChangeoverCorrectionWorkbench({deploymentNo,changeoverNo,contextEnabled=false,submissionEnabled=false,recoveryEnabled=false}:{
  deploymentNo:string;changeoverNo:string;contextEnabled?:boolean;submissionEnabled?:boolean;recoveryEnabled?:boolean;
}){
  const [context,setContext]=useState<ChangeoverCorrectionContext|null>(null),[fields,setFields]=useState<Fields>(blank);
  const [review,setReview]=useState<ChangeoverCorrectionReview|null>(null),[result,setResult]=useState<ChangeoverCorrectionState|null>(null);
  const [message,setMessage]=useState(''),[loading,setLoading]=useState(false);
  const controller=useRef<ChangeoverCorrectionSubmission|null>(null),loadPending=useRef(false);
  const capability=useRef({context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled});
  capability.current={context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled};
  const key=JSON.stringify([deploymentNo,changeoverNo]),currentKey=useRef(key),previousKey=useRef(key);currentKey.current=key;
  const current=result?.review??(previousKey.current===key?review:null),active=useRef(current);active.current=current;
  const currentContext=useRef(context),draftFields=useRef(fields);currentContext.current=context;draftFields.current=fields;
  const busy=loading||result?.phase==='sending'||result?.phase==='checking';
  useEffect(()=>{if(previousKey.current===key)return;previousKey.current=key;
    if(!controller.current){setContext(null);setFields(blank);setReview(null);setMessage('');}
  },[key]);
  useEffect(()=>{if(!result||!['sending','checking','unknown'].includes(result.phase))return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[result?.phase]);
  function matches(){return active.current===current&&(controller.current?controller.current.state.review===current:currentKey.current===key);}
  async function loadContext(){
    if(!capability.current.context||loadPending.current||controller.current||currentKey.current!==key)return;
    const target=parseChangeoverCorrectionTarget({deployment_no:deploymentNo,changeover_no:changeoverNo});
    if(!target){setMessage('The private correction target is invalid. Nothing was sent.');return;}
    loadPending.current=true;setLoading(true);active.current=null;setReview(null);setContext(null);setMessage('');
    try{
      const response=await fetch('/auth/changeover-correction-context',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},
        body:JSON.stringify(target),credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response),next=response.status===200?parseChangeoverCorrectionContext(value,target):null;
      if(currentKey.current!==key||controller.current)return;
      if(!next||!capability.current.context){setMessage('Private correction context could not be loaded. Nothing was sent.');return;}
      currentContext.current=next;setContext(next);setFields(fromContext(next));
    }catch{if(currentKey.current===key&&!controller.current)setMessage('Private correction context could not be loaded. Nothing was sent.');}
    finally{loadPending.current=false;setLoading(false);}
  }
  function edit(name:keyof Fields,value:string){
    if(controller.current||loadPending.current||currentKey.current!==key)return;
    active.current=null;draftFields.current={...fields,[name]:value};setFields(draftFields.current);setReview(null);setMessage('');
  }
  function prepare(){
    if(!context||context!==currentContext.current||draftFields.current!==fields||controller.current||loadPending.current||currentKey.current!==key)return;
    if(!fields.changed_at.trim()){setMessage('An explicit changeover time with a timezone is required. Nothing was sent.');return;}
    const command=parseChangeoverCorrectionCommand({operation:'changeover-correction',target:{deployment_no:context.deployment_no,changeover_no:context.changeover_no},context,
      body:{request_id:crypto.randomUUID(),expected_revision:context.expected_revision,predecessor_id:context.predecessor_id,
        from_release_id:fields.from_release_id,changed_at:fields.changed_at,note:fields.note||null,correction_reason:fields.correction_reason}});
    if(!command){setMessage('The changeover correction values are invalid. Nothing was sent.');return;}
    const next=confirmChangeoverCorrection(command,false);active.current=next;setReview(next);setMessage('Review the exact context and replacement values before confirming.');
  }
  function confirm(checked:boolean){
    if(!checked||!current||!matches()||controller.current||loadPending.current)return;
    try{const next=confirmChangeoverCorrection(current.command,true);controller.current=new ChangeoverCorrectionSubmission(next);
      active.current=controller.current.state.review;setReview(next);setResult(controller.current.state);setMessage('');
    }catch{setMessage('The changeover correction values are invalid. Nothing was sent.');}
  }
  async function run(mode:'send'|'recover'){
    if(!current?.confirmed||!matches()||!controller.current||loadPending.current||!(mode==='send'?capability.current.submit:capability.current.recover))return;
    const pending=mode==='send'?controller.current.send(capability.current.submit):controller.current.recover(capability.current.recover);
    setResult(controller.current.state);setMessage('');setResult(await pending);
  }
  function reset(){
    if(loadPending.current||!matches()||(controller.current&&!['idle','rejected','confirmed'].includes(controller.current.state.phase)))return;
    controller.current=null;active.current=null;currentContext.current=null;setContext(null);setFields(blank);setReview(null);setResult(null);setMessage('Reload private context before preparing another request.');
  }
  const shown=current?.command.context??context;
  const input=(name:keyof Fields,label:string,maxLength:number)=><Localized><label><Localized>{label}</Localized><input name={name} required maxLength={maxLength} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label></Localized>;
  return <Localized><section className="panel">
    <h2><Localized>{'Correct recorded changeover facts'}</Localized></h2>
    <p><Localized>{'This appends a correction to recorded changeover facts. The target release remains immutable; no physical production action is performed.'}</Localized></p>
    <p>{current?.command.target.deployment_no??deploymentNo} · {current?.command.target.changeover_no??changeoverNo}</p>
    {!submissionEnabled&&<p className="notice"><Localized>{'Changeover correction submission is disabled or unavailable for this session.'}</Localized></p>}
    <p><Localized>{'Public history is not permission. Load private authenticated context before preparing a correction.'}</Localized></p>
    {!controller.current&&<button type="button" onClick={loadContext} disabled={!contextEnabled||busy}><Localized>{'Load private correction context'}</Localized></button>}
    {shown&&<section><h3><Localized>{'Private correction context'}</Localized></h3>
      <p><Localized>{'Changeover ID'}</Localized>: <code>{shown.changeover_id}</code></p>
      <p><Localized>{'Immutable target release'}</Localized>: <code>{shown.to_release_id}</code></p>
      <p><Localized>{'Current revision'}</Localized>: {shown.expected_revision} · <Localized>{'Predecessor correction ID'}</Localized>: <code>{shown.predecessor_id??'—'}</code></p>
      <p><Localized>{'History state'}</Localized>: <Localized>{shown.history_state}</Localized></p>
    </section>}
    {context&&<form className="commandform" onSubmit={e=>{e.preventDefault();prepare();}}><fieldset className="commandfields" disabled={busy||controller.current!==null}>
      {input('from_release_id','Corrected source release UUID (required)',36)}
      <label><Localized>{'Corrected changeover time (explicit timezone required)'}</Localized><input name="changed_at" required maxLength={40} value={fields.changed_at} onChange={e=>edit('changed_at',e.target.value)}/></label>
      <p><Localized>{'Enter an explicit timestamp with a timezone. Blank time is not allowed and never means now.'}</Localized></p>
      <label><Localized>{'Corrected note (blank clears note)'}</Localized><textarea name="note" maxLength={8192} value={fields.note} onChange={e=>edit('note',e.target.value)}/></label>
      <p><Localized>{'The complete context and request must fit the transport limit. Long existing notes are never silently truncated.'}</Localized></p>
      <label><Localized>{'Correction reason'}</Localized><textarea name="correction_reason" required maxLength={2000} value={fields.correction_reason} onChange={e=>edit('correction_reason',e.target.value)}/></label>
      <button type="submit" disabled={current!==null}><Localized>{'Prepare changeover correction'}</Localized></button>
    </fieldset></form>}
    {current&&<section><h3><Localized>{'Review exact changeover correction'}</Localized></h3>
      <p><Localized>{'Request ID'}</Localized>: <code>{current.command.body.request_id}</code></p>
      <p><Localized>{'Expected revision'}</Localized>: {current.command.body.expected_revision}</p>
      <p><Localized>{'The confirmed request ID, predecessor and body remain frozen. Unknown outcomes cannot be replaced by refreshed context.'}</Localized></p>
      <pre><code>{JSON.stringify(current.command,null,2)}</code></pre>
      {!controller.current&&<label><input type="checkbox" checked={false} disabled={busy} onChange={e=>confirm(e.target.checked)}/><Localized>{'I confirm this exact changeover, revision, predecessor, replacement values, reason and request ID.'}</Localized></label>}
      {result?.phase==='idle'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Send confirmed changeover correction'}</Localized></button>}
      {result?.phase==='unknown'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Retry original changeover correction'}</Localized></button>}
      {result&&['unknown','rejected'].includes(result.phase)&&<button type="button" disabled={!recoveryEnabled||busy} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>}
      {(!result||['idle','rejected','confirmed'].includes(result.phase))&&<button type="button" disabled={busy} onClick={reset}><Localized>{'Reload context for a new correction'}</Localized></button>}
    </section>}
    {message&&<p role="status"><Localized>{message}</Localized></p>}
    {result&&<ChangeoverCorrectionResult state={result}/>}
    <p><Localized>{'Request state is kept only in this page. Do not leave while the original outcome is unknown; no cross-session recovery import is provided here.'}</Localized></p>
  </section></Localized>;
}
