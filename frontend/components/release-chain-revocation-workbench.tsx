'use client';
import {useRef,useState} from 'react';
import {Localized} from './localized';
import ReleaseChainRevocationResult from './release-chain-revocation-result';
import {exportReleaseChainRevocationRecovery,importReleaseChainRevocationRecovery,releaseChainRevocationRecoveryTextLimit,
  type ImportedReleaseChainRevocationRecovery} from '../lib/release-chain-revocation-recovery';
import {parseReleaseChainRevocationCommand,confirmReleaseChainRevocation,ReleaseChainRevocationSubmission,
  type ReleaseChainRevocationReview,type ReleaseChainRevocationState,type ReleaseChainTargetKind} from '../lib/release-chain-revocation-transport';

type Fields={kind:ReleaseChainTargetKind;targetId:string;reason:string;releaseId:string;snapshotId:string;decisionId:string;
 deliveryId:string;distributionId:string;authorizationId:string};
const blank:Fields={kind:'RELEASE',targetId:'',reason:'',releaseId:'',snapshotId:'',decisionId:'',deliveryId:'',distributionId:'',authorizationId:''};
const kinds:ReleaseChainTargetKind[]=['RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION'];
export default function ReleaseChainRevocationWorkbench({initialContext={},submissionEnabled=false,recoveryEnabled=false}:
 {initialContext?:Partial<Fields>;submissionEnabled?:boolean;recoveryEnabled?:boolean}){
 const [fields,setFields]=useState<Fields>({...blank,...initialContext}),[review,setReview]=useState<ReleaseChainRevocationReview|null>(null),
  [result,setResult]=useState<ReleaseChainRevocationState|null>(null),[message,setMessage]=useState(''),[copying,setCopying]=useState(false),[importText,setImportText]=useState('');
 const controller=useRef<ReleaseChainRevocationSubmission|ImportedReleaseChainRevocationRecovery|null>(null),imported=useRef(false),source=useRef(''),
  locked=copying||result?.phase==='sending'||result?.phase==='checking';const current=result?.review??review;
 const edit=(name:keyof Fields,value:string)=>{if(controller.current||copying)return;setFields({...fields,[name]:value});setReview(null);setMessage('');};
 function command(){
  const depth=kinds.indexOf(fields.kind);
  return parseReleaseChainRevocationCommand({operation:'release-chain-revocation',target_kind:fields.kind,target_id:fields.targetId.trim(),
   body:{request_id:crypto.randomUUID(),reason:fields.reason.trim(),expected_context:{version:1,release_id:fields.releaseId.trim(),
    snapshot_id:fields.snapshotId.trim(),release_decision_id:fields.decisionId.trim(),
    delivery_package_id:depth>=1?fields.deliveryId.trim():null,distribution_id:depth>=2?fields.distributionId.trim():null,
    authorization_id:depth>=3?fields.authorizationId.trim():null}}});
 }
 async function run(mode:'send'|'recover'){if(!current?.confirmed||locked||(mode==='send'&&imported.current))return;
  if(!controller.current){if(mode==='recover')return;controller.current=new ReleaseChainRevocationSubmission(current);}
  const pending=mode==='send'&&'send'in controller.current?controller.current.send(submissionEnabled):controller.current.recover(recoveryEnabled);
  setResult(controller.current.state);setMessage('');setResult(await pending);}
 async function copy(recovery=false){if(!current?.confirmed||locked)return;setCopying(true);
  try{await navigator.clipboard.writeText(recovery?exportReleaseChainRevocationRecovery(current,window.location.origin):JSON.stringify(current.command));
   setMessage(recovery?'Revocation recovery text copied. It contains business data, not proof of execution. Store it securely.':'Original revocation request copied. Copying does not send an operation.');}
  catch{setMessage('Clipboard unavailable. Select and copy the confirmed revocation below.');}finally{setCopying(false);}}
 function reset(){if(locked||controller.current&&!['confirmed','rejected'].includes(controller.current.state.phase))return;
  controller.current=null;imported.current=false;source.current='';setImportText('');setResult(null);setReview(null);setMessage('');setFields({...blank,...initialContext});}
 function stage(){if(controller.current||review||source.current!==importText)return;
  try{const restored=importReleaseChainRevocationRecovery(importText,window.location.origin);controller.current=restored;imported.current=true;
   setReview(restored.state.review);setResult(restored.state);setImportText('');source.current='';setMessage('');}
  catch{setMessage('Revocation recovery text is invalid, noncanonical or belongs to another site. Nothing was sent.');}}
 let recoveryText='';try{if(current?.confirmed&&typeof window!=='undefined')recoveryText=exportReleaseChainRevocationRecovery(current,window.location.origin);}catch{}
 const input=(name:keyof Fields,label:string,max:number)=><label><Localized>{label}</Localized><input name={name} required maxLength={max} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label>;
 return <Localized><section className="panel"><h2><Localized>{'Permanently revoke a release-chain node'}</Localized></h2>
  <p className="notice"><Localized>{'Revocation permanently ends future authority for the exact target. It never edits recorded status and never recalls existing delivery or production facts.'}</Localized></p>
  {!submissionEnabled&&<p><Localized>{'Release-chain revocation submission is disabled in this environment.'}</Localized></p>}
  <form className="commandform" hidden={imported.current} onSubmit={e=>{e.preventDefault();if(controller.current||review)return;
   const c=command();if(!c){setMessage('The release-chain revocation context or request is invalid.');return;}
   setReview(confirmReleaseChainRevocation(c,false));setMessage('Review the exact target, reviewed context and reason before confirming.');}}>
   <fieldset className="commandfields" disabled={copying||result!==null}>
    <label><Localized>{'Target kind'}</Localized><select name="kind" value={fields.kind} onChange={e=>edit('kind',e.target.value as ReleaseChainTargetKind)}>{kinds.map(k=><option key={k} value={k}><Localized>{k}</Localized></option>)}</select></label>
    {input('targetId','Exact target UUID',36)}
    <label><Localized>{'Revocation reason'}</Localized><textarea name="reason" required maxLength={4000} value={fields.reason} onChange={e=>edit('reason',e.target.value)}/></label>
    {input('releaseId','Release UUID',36)}{input('snapshotId','Frozen snapshot UUID',36)}{input('decisionId','Reviewed release decision UUID',36)}
    {kinds.indexOf(fields.kind)>=1&&input('deliveryId','Delivery package UUID',36)}
    {kinds.indexOf(fields.kind)>=2&&input('distributionId','Distribution UUID',36)}
    {kinds.indexOf(fields.kind)>=3&&input('authorizationId','Authorization UUID',36)}
    <button type="submit"><Localized>{'Prepare revocation request'}</Localized></button>
   </fieldset></form>
  {current&&<section><h3><Localized>{'Review exact release-chain revocation'}</Localized></h3>
   <p><Localized>{'Target kind'}</Localized>: <Localized>{current.command.target_kind}</Localized></p>
   <p><Localized>{'Exact target UUID'}</Localized>: <code>{current.command.target_id}</code></p>
   <p><Localized>{'Request ID'}</Localized>: <code>{current.command.body.request_id}</code></p>
   <p><Localized>{'Release UUID'}</Localized>: <code>{current.command.body.expected_context.release_id}</code></p>
   <p><Localized>{'Frozen snapshot UUID'}</Localized>: <code>{current.command.body.expected_context.snapshot_id}</code></p>
   <p><Localized>{'Reviewed release decision UUID'}</Localized>: <code>{current.command.body.expected_context.release_decision_id}</code></p>
   {current.command.body.expected_context.delivery_package_id!==null&&<p><Localized>{'Delivery package UUID'}</Localized>: <code>{current.command.body.expected_context.delivery_package_id}</code></p>}
   {current.command.body.expected_context.distribution_id!==null&&<p><Localized>{'Distribution UUID'}</Localized>: <code>{current.command.body.expected_context.distribution_id}</code></p>}
   {current.command.body.expected_context.authorization_id!==null&&<p><Localized>{'Authorization UUID'}</Localized>: <code>{current.command.body.expected_context.authorization_id}</code></p>}
   <p><Localized>{'Revocation reason'}</Localized>: <span style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{current.command.body.reason}</span></p>
   {!result&&<label><input type="checkbox" checked={current.confirmed} onChange={e=>setReview(confirmReleaseChainRevocation(current.command,e.target.checked))}/>
    <Localized>{'I confirm this exact target, reviewed context, reason and request ID.'}</Localized></label>}
   <div className="actions">
    {!imported.current&&!result&&submissionEnabled&&<button type="button" disabled={!current.confirmed||locked} onClick={()=>run('send')}><Localized>{'Send confirmed revocation request'}</Localized></button>}
    {result&&result.phase!=='confirmed'&&<button type="button" disabled={!recoveryEnabled||locked} onClick={()=>run('recover')}><Localized>{'Query original revocation audit without resubmitting'}</Localized></button>}
    {(!result||['confirmed','rejected'].includes(result.phase))&&<button type="button" disabled={locked} onClick={reset}><Localized>{'Start a new request'}</Localized></button>}
    <button type="button" disabled={!current.confirmed||locked} onClick={()=>copy()}><Localized>{'Copy confirmed revocation request'}</Localized></button>
    <button type="button" disabled={!current.confirmed||locked} onClick={()=>copy(true)}><Localized>{'Copy revocation recovery text'}</Localized></button>
   </div>
   {recoveryText&&<><p className="muted"><Localized>{'Recovery text contains the original revocation and reviewed context, not proof of execution. Store it securely.'}</Localized></p><pre><code>{recoveryText}</code></pre></>}
   {imported.current&&<p className="notice"><Localized>{'Imported revocation recovery is read-only. Nothing was sent; explicitly query your original audit after signing in.'}</Localized></p>}
  </section>}
  {!current&&!result&&<section><h3><Localized>{'Restore an original revocation audit query'}</Localized></h3>
   <p className="muted"><Localized>{'Paste revocation recovery text exported from this exact site. Import does not send, retry or query automatically.'}</Localized></p>
   <label><Localized>{'Revocation recovery text'}</Localized><textarea name="importText" maxLength={releaseChainRevocationRecoveryTextLimit} value={importText} onChange={e=>{if(!controller.current){source.current=e.target.value;setImportText(e.target.value);setMessage('');}}}/></label>
   <button type="button" disabled={!importText||copying} onClick={stage}><Localized>{'Import revocation recovery without sending'}</Localized></button></section>}
  {message&&<p role="status"><Localized>{message}</Localized></p>}{result&&<ReleaseChainRevocationResult state={result}/>}</section></Localized>;
}
