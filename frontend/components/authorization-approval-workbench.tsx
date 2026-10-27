'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {Localized} from './localized';
import {exportAuthorizationApprovalRecovery,importAuthorizationApprovalRecovery,authorizationApprovalRecoveryTextLimit,type ImportedAuthorizationApprovalRecovery} from '../lib/authorization-approval-recovery';
import {readCommandResponse} from '../lib/first-command-transport';
import {parseAuthorizationApprovalTarget,parseAuthorizationApprovalContext,parseAuthorizationApprovalCommand,confirmAuthorizationApproval,
  AuthorizationApprovalSubmission,type AuthorizationApprovalContext,type AuthorizationApprovalReview,type AuthorizationApprovalState} from '../lib/authorization-approval-transport';

type Fields={reason:string};
const blank:Fields={reason:''};
const fromContext=(_context:AuthorizationApprovalContext):Fields=>({...blank});

export function AuthorizationApprovalResult({state}:{state:AuthorizationApprovalState}){
  const receipt=state.receipt;
  const labels:Record<string,string>={authorization_id:'Authorization UUID',authorization_no:'Authorization number',request_id:'Request ID',audit_event_no:'Audit event number',applied_status:'Original applied status',approved_at:'Approved at',creator_principal_id:'Creator principal UUID',approver_principal_id:'Approver principal UUID',expected_context_digest:'Expected context digest',reason:'Reason'};
  return <Localized><section className="panel" aria-live="polite">
    <h3><Localized>{'Authorization approval result'}</Localized></h3>
    <p><Localized>{'Operation phase'}</Localized>: <Localized>{state.phase}</Localized></p>
    {state.phase==='unknown'&&<p className="notice"><Localized>{'The original outcome is unknown. Keep this request and query its original audit; do not prepare a replacement.'}</Localized></p>}
    {state.phase==='rejected'&&<p><Localized>{'This attempt was rejected before a confirmed result. Reload private approval context before preparing another request.'}</Localized></p>}
    {state.error&&<p><Localized>{'Result code'}</Localized>: <code>{state.error}</code></p>}
    {receipt&&<><p><Localized>{'This receipt proves only the original APPROVED decision. It does not prove current eligibility, deployment, physical production or formal release.'}</Localized></p>
      <dl className="kv">{Object.entries(receipt).map(([key,value])=><div key={key}><dt><Localized>{labels[key]??key}</Localized></dt><dd style={{overflowWrap:'anywhere'}}>{value===null?<Localized>{'Not recorded'}</Localized>:String(value)}</dd></div>)}</dl>
      <Link href={'/activity/'+encodeURIComponent(receipt.audit_event_no)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open original approval audit'}</Localized></Link>
    </>}
  </section></Localized>;
}

export default function AuthorizationApprovalWorkbench({authorizationNo,contextEnabled=false,submissionEnabled=false,recoveryEnabled=false}:{
  authorizationNo:string;contextEnabled?:boolean;submissionEnabled?:boolean;recoveryEnabled?:boolean;
}){
  const [context,setContext]=useState<AuthorizationApprovalContext|null>(null),[fields,setFields]=useState<Fields>(blank);
  const [review,setReview]=useState<AuthorizationApprovalReview|null>(null),[result,setResult]=useState<AuthorizationApprovalState|null>(null);
  const [message,setMessage]=useState(''),[loading,setLoading]=useState(false);
  const [copying,setCopying]=useState(false),[importText,setImportText]=useState('');
  const imported=useRef(false),copyPending=useRef(false),importSource=useRef('');
  const controller=useRef<AuthorizationApprovalSubmission|ImportedAuthorizationApprovalRecovery|null>(null),loadPending=useRef(false);
  const capability=useRef({context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled});
  capability.current={context:contextEnabled,submit:submissionEnabled,recover:recoveryEnabled};
  const key=JSON.stringify([authorizationNo]),currentKey=useRef(key),previousKey=useRef(key);currentKey.current=key;
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
    const target=parseAuthorizationApprovalTarget({authorization_no:authorizationNo});
    if(!target){setMessage('The private approval target is invalid. Nothing was sent.');return;}
    loadPending.current=true;setLoading(true);active.current=null;setReview(null);setContext(null);setMessage('');
    try{
      const response=await fetch('/auth/authorization-approval-context',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},
        body:JSON.stringify(target),credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
      const value=await readCommandResponse(response),next=response.status===200?parseAuthorizationApprovalContext(value,target):null;
      if(currentKey.current!==key||controller.current)return;
      if(!next||!capability.current.context){setMessage('Private approval context could not be loaded. Nothing was sent.');return;}
      currentContext.current=next;setContext(next);setFields(fromContext(next));
    }catch{if(currentKey.current===key&&!controller.current)setMessage('Private approval context could not be loaded. Nothing was sent.');}
    finally{loadPending.current=false;setLoading(false);}
  }
  function edit(name:keyof Fields,value:string){
    if(copyPending.current||controller.current||loadPending.current||currentKey.current!==key)return;
    active.current=null;draftFields.current={...fields,[name]:value};setFields(draftFields.current);setReview(null);setMessage('');
  }
  function prepare(){
    if(active.current||copyPending.current||!context||context!==currentContext.current||draftFields.current!==fields||controller.current||loadPending.current||currentKey.current!==key)return;
    const command=parseAuthorizationApprovalCommand({operation:'authorization-approval',target:{authorization_no:context.context.authorization_no},context,
      body:{request_id:crypto.randomUUID(),expected_context_digest:context.context_digest,reason:fields.reason}});
    if(!command){setMessage('The approval values are invalid. Nothing was sent.');return;}
    const next=confirmAuthorizationApproval(command,false);active.current=next;setReview(next);setMessage('Review the exact scope, creator, digest and reason before confirming.');
  }
  function confirm(checked:boolean){
    if(copyPending.current||!checked||!current||!matches()||controller.current||loadPending.current)return;
    try{const next=confirmAuthorizationApproval(current.command,true);controller.current=new AuthorizationApprovalSubmission(next);
      active.current=controller.current.state.review;setReview(next);setResult(controller.current.state);setMessage('');
    }catch{setMessage('The approval values are invalid. Nothing was sent.');}
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
    controller.current=null;imported.current=false;importSource.current='';setImportText('');active.current=null;currentContext.current=null;setContext(null);setFields(blank);setReview(null);setResult(null);setMessage('Reload private approval context before preparing another request.');
  }
  async function copyRecovery(){
    if(!current?.confirmed||!matches()||copyPending.current||loadPending.current||['sending','checking'].includes(controller.current?.state.phase??''))return;
    copyPending.current=true;setCopying(true);
    try{await navigator.clipboard.writeText(exportAuthorizationApprovalRecovery(current,window.location.origin));
      if(matches())setMessage('Recovery text copied. It contains business data, not proof of execution. Store it securely.');
    }catch{if(matches())setMessage('Clipboard unavailable. Select and copy the recovery text below.');}
    finally{copyPending.current=false;setCopying(false);}
  }
  function stageRecovery(){
    if(copyPending.current||loadPending.current||controller.current||active.current||currentKey.current!==key||importSource.current!==importText)return;
    try{
      const restored=importAuthorizationApprovalRecovery(importText,window.location.origin),target=restored.state.command.target;
      if(target.authorization_no!==authorizationNo)throw Error('wrong_target');
      controller.current=restored;imported.current=true;active.current=restored.state.review;currentContext.current=null;
      setContext(null);setFields(blank);setReview(restored.state.review);setResult(restored.state);setImportText('');importSource.current='';setMessage('');
    }catch{setMessage('Recovery text is invalid or does not match this site and authorization. Nothing was sent.');}
  }
  let recoveryText='';
  try{if(current?.confirmed&&typeof window!=='undefined'&&window.location?.origin)recoveryText=exportAuthorizationApprovalRecovery(current,window.location.origin);}
  catch{ /* Invalid manual exports never break preparation. */ }
  const shown=current?.command.context??context;
  const contextLabels:Record<string,string>={authorization_id:'Authorization UUID',authorization_no:'Authorization number',release_id:'Release ID',snapshot_id:'Snapshot ID',release_decision_id:'Release decision UUID',distribution_id:'Distribution UUID',delivery_package_id:'Delivery package UUID',package_revision:'Package revision',customer_id:'Customer UUID',project_id:'Project UUID',site_code:'Site code',line_code:'Line code',purpose:'Purpose',batch_limit:'Batch limit',restriction_note:'Restriction note',creation_event_id:'Creation audit UUID',creator_principal_id:'Creator principal UUID'};
  return <Localized><section className="panel">
    <h2><Localized>{'Review production authorization approval'}</Localized></h2>
    <p><Localized>{'A different currently authorized project authority must approve this exact scope. Creator self-approval is not allowed; a digest is not permission.'}</Localized></p>
    <p>{current?.command.target.authorization_no??authorizationNo}</p>
    {!submissionEnabled&&<p className="notice"><Localized>{'Authorization approval submission is disabled or unavailable for this session.'}</Localized></p>}
    <p><Localized>{'Public authorization details are not permission. Explicitly load private approval context.'}</Localized></p>
    {!controller.current&&<button type="button" onClick={loadContext} disabled={!contextEnabled||busy}><Localized>{'Load private approval context'}</Localized></button>}
    {shown&&<section><h3><Localized>{imported.current?'Imported approval context — unverified evidence':'Private approval context'}</Localized></h3>
      <dl className="kv">{Object.entries(shown.context).map(([name,value])=><div key={name}><dt><Localized>{contextLabels[name]??name}</Localized></dt><dd style={{overflowWrap:'anywhere'}}>{value===null?<Localized>{'Not recorded'}</Localized>:String(value)}</dd></div>)}</dl>
      <p><Localized>{'Context version'}</Localized>: {shown.version}</p><p><Localized>{'Expected context digest'}</Localized>: <code>{shown.context_digest}</code></p>
    </section>}
    {context&&<form className="commandform" onSubmit={e=>{e.preventDefault();prepare();}}><fieldset className="commandfields" disabled={busy||controller.current!==null}>
      <label><Localized>{'Approval reason'}</Localized><textarea name="reason" required maxLength={2000} value={fields.reason} onChange={e=>edit('reason',e.target.value)}/></label>
      <button type="submit" disabled={current!==null}><Localized>{'Prepare authorization approval'}</Localized></button>
    </fieldset></form>}
    {current&&<section><h3><Localized>{'Review exact authorization approval'}</Localized></h3>
      <p><Localized>{'Request ID'}</Localized>: <code>{current.command.body.request_id}</code></p>
      <p><Localized>{'Expected context digest'}</Localized>: <code>{current.command.body.expected_context_digest}</code></p>
      <p><Localized>{'The confirmed request ID, scope, digest and reason remain frozen. Unknown outcomes cannot be replaced by refreshed context.'}</Localized></p>
      <pre><code>{JSON.stringify(current.command,null,2)}</code></pre>
      {!controller.current&&<label><input type="checkbox" checked={false} disabled={busy} onChange={e=>confirm(e.target.checked)}/><Localized>{'I confirm this exact authorization, scope, creator, digest, reason and request ID.'}</Localized></label>}
      {!imported.current&&result?.phase==='idle'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Send confirmed authorization approval'}</Localized></button>}
      {!imported.current&&result?.phase==='unknown'&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Retry original authorization approval'}</Localized></button>}
      {result&&['unknown','rejected'].includes(result.phase)&&<button type="button" disabled={!recoveryEnabled||busy} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>}
      {(!result||['idle','rejected','confirmed'].includes(result.phase))&&<button type="button" disabled={busy} onClick={reset}><Localized>{'Reload context for a new approval'}</Localized></button>}
      <p className="muted"><Localized>{'Approval recovery text contains business scope, creator UUID and reason. Keep it locally and privately; it is not credentials, permission or execution proof.'}</Localized></p>
      <button type="button" disabled={!current.confirmed||busy} onClick={copyRecovery}><Localized>{'Copy authorization approval recovery text'}</Localized></button>
      {recoveryText&&<pre><code>{recoveryText}</code></pre>}
      {imported.current&&<p className="notice"><Localized>{'Imported approval recovery is audit-only. Nothing was sent; explicitly query your original audit after signing in.'}</Localized></p>}
    </section>}
    {!current&&!result&&<section><h3><Localized>{'Restore an original approval audit query'}</Localized></h3>
      <p><Localized>{'Paste approval recovery text for this exact site and authorization. Import never submits, retries or queries automatically.'}</Localized></p>
      <label><Localized>{'Approval recovery text'}</Localized><textarea name="importText" maxLength={authorizationApprovalRecoveryTextLimit} value={importText} onChange={e=>{
        if(copyPending.current||loadPending.current||controller.current||currentKey.current!==key)return;
        importSource.current=e.target.value;setImportText(e.target.value);setMessage('');
      }}/></label>
      <button type="button" disabled={busy||!importText} onClick={stageRecovery}><Localized>{'Import approval recovery without sending'}</Localized></button>
    </section>}
    {message&&<p role="status"><Localized>{message}</Localized></p>}
    {result&&<AuthorizationApprovalResult state={result}/>}
    <p><Localized>{'Request state is kept only in this page. Manually save recovery text before leaving an unknown outcome; nothing is stored automatically.'}</Localized></p>
  </section></Localized>;
}
