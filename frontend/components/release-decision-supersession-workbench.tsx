'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import {exportReleaseDecisionSupersessionRecovery,importReleaseDecisionSupersessionRecovery,type ImportedReleaseDecisionSupersessionRecovery} from '../lib/release-decision-supersession-recovery';
import ReleaseDecisionSupersessionResult from './release-decision-supersession-result';
import {parseReleaseDecisionSupersessionCommand,confirmReleaseDecisionSupersession,ReleaseDecisionSupersessionSubmission,
 type ReleaseDecisionSupersessionReview,type ReleaseDecisionSupersessionState} from '../lib/release-decision-supersession-transport';
type Fields={target:string;predecessor:string;release:string;snapshot:string;previousNo:string;previousDecision:string;
 previousReadiness:string;decisionNo:string;actor:string;readiness:string;decision:string;notes:string;correctionReason:string};
const blank:Fields={target:'',predecessor:'',release:'',snapshot:'',previousNo:'',previousDecision:'',previousReadiness:'',
 decisionNo:'',actor:'',readiness:'',decision:'',notes:'',correctionReason:''};
export default function ReleaseDecisionSupersessionWorkbench({initialContext={},submissionEnabled=false,recoveryEnabled=false}:
 {initialContext?:Partial<Fields>;submissionEnabled?:boolean;recoveryEnabled?:boolean}){
 const [fields,setFields]=useState<Fields>({...blank,...initialContext}),[review,setReview]=useState<ReleaseDecisionSupersessionReview|null>(null),
  [result,setResult]=useState<ReleaseDecisionSupersessionState|null>(null),[message,setMessage]=useState('');
 const [importText,setImportText]=useState(''),[copying,setCopying]=useState(false),[revealed,setRevealed]=useState(false);
 const controller=useRef<ReleaseDecisionSupersessionSubmission|ImportedReleaseDecisionSupersessionRecovery|null>(null),imported=useRef(false),copyPending=useRef(false),importSource=useRef('');
 const key=JSON.stringify(initialContext),currentKey=useRef(key),previousKey=useRef(key);currentKey.current=key;
 const current=result?.review??(previousKey.current===key?review:null),active=useRef(current),draft=useRef(fields);active.current=current;draft.current=fields;
 const capability=useRef({send:submissionEnabled,recover:recoveryEnabled});capability.current={send:submissionEnabled,recover:recoveryEnabled};
 const busy=copying||result?.phase==='sending'||result?.phase==='checking';
 const matches=()=>active.current===current&&(controller.current?controller.current.state.review===current:currentKey.current===key);
 useEffect(()=>{if(previousKey.current===key)return;previousKey.current=key;if(!controller.current){active.current=null;setReview(null);setFields({...blank,...initialContext});setMessage('');setImportText('');importSource.current='';setRevealed(false);}},[key]);
 useEffect(()=>{if(!result||!['sending','checking','unknown'].includes(result.phase))return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[result?.phase]);
 const edit=(name:keyof Fields,value:string)=>{if(controller.current||copyPending.current||currentKey.current!==key)return;active.current=null;draft.current={...fields,[name]:value};setFields(draft.current);setReview(null);setMessage('');setRevealed(false);};
 async function run(mode:'send'|'recover'){
  if(!current?.confirmed||!matches()||copyPending.current||busy||(mode==='send'&&imported.current)||!(mode==='send'?capability.current.send:capability.current.recover))return;
  if(!controller.current)controller.current=new ReleaseDecisionSupersessionSubmission(current);
  if(mode==='send'&&!('send'in controller.current))return;
  const pending=mode==='send'&&'send'in controller.current?controller.current.send(capability.current.send):controller.current.recover(capability.current.recover);setResult(controller.current.state);setResult(await pending);
 }
 function reset(){if(copyPending.current||!matches()||(controller.current&&!['confirmed','rejected'].includes(controller.current.state.phase)))return;controller.current=null;imported.current=false;active.current=null;setResult(null);setReview(null);setMessage('');setFields({...blank,...initialContext});setImportText('');importSource.current='';setRevealed(false);}
 async function copy(recovery=false){
  if(!current?.confirmed||!matches()||copyPending.current||busy)return;copyPending.current=true;setCopying(true);
  try{await navigator.clipboard.writeText(recovery?exportReleaseDecisionSupersessionRecovery(current,window.location.origin):JSON.stringify(current.command));if(matches())setMessage(recovery?'Recovery text copied. It contains business data, not proof of execution. Store it securely.':'Original replacement request copied. Copying does not send an operation.');}
  catch{if(matches())setMessage('Clipboard unavailable. Select and copy the confirmed request below.');}finally{copyPending.current=false;setCopying(false);}
 }
 function stageRecovery(){
  if(copyPending.current||controller.current||active.current||currentKey.current!==key||importSource.current!==importText)return;
  try{const restored=importReleaseDecisionSupersessionRecovery(importText,window.location.origin);
   if(initialContext.target&&restored.state.command.target!==initialContext.target)throw Error('wrong_target');
   controller.current=restored;imported.current=true;active.current=restored.state.review;setReview(restored.state.review);setResult(restored.state);setImportText('');importSource.current='';setMessage('');setRevealed(false);
  }catch{setMessage('Replacement recovery text is invalid or belongs to another site or approval. Nothing was sent.');}
 }
 let recoveryText='';try{if(revealed&&current?.confirmed&&typeof window!=='undefined')recoveryText=exportReleaseDecisionSupersessionRecovery(current,window.location.origin);}catch{/* Invalid export never breaks the workbench. */}
 const input=(name:keyof Fields,label:string,max:number)=><label><Localized>{label}</Localized><input name={name} required maxLength={max} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label>;
 return <Localized><section className="panel"><h2><Localized>{'Replace a release decision'}</Localized></h2>
  <p className="notice"><Localized>{'Replacement appends a new formal decision for a new approved request and the same frozen snapshot. It never edits the predecessor.'}</Localized></p>
  <Localized>{!submissionEnabled&&<p><Localized>{'Release decision replacement submission is disabled in this environment.'}</Localized></p>}</Localized>
  <form className="commandform" hidden={imported.current} onSubmit={e=>{e.preventDefault();if(controller.current||active.current||copyPending.current||currentKey.current!==key||draft.current!==fields)return;
   const command=parseReleaseDecisionSupersessionCommand({operation:'release-decision-supersession',target:fields.target,
    body:{request_id:crypto.randomUUID(),decision_no:fields.decisionNo,decided_by:fields.actor,readiness_status:fields.readiness,
      decision:fields.decision,notes:fields.notes.trim()||null,supersedes_id:fields.predecessor,correction_reason:fields.correctionReason},
    predecessor:{id:fields.predecessor,release_id:fields.release,snapshot_id:fields.snapshot,decision_no:fields.previousNo,
      decision:fields.previousDecision,readiness_status:fields.previousReadiness}});
   if(!command){setMessage('The release decision replacement context or request is invalid.');return;}
   const next=confirmReleaseDecisionSupersession(command,false);active.current=next;setReview(next);setRevealed(false);setMessage('Review the exact predecessor, new approval and replacement request before confirming.');}}>
   <fieldset className="commandfields" disabled={copying||!!review||!!result}>{input('target','New approved request number',50)}
    {input('predecessor','Predecessor decision UUID',36)}{input('release','Release UUID',36)}{input('snapshot','Frozen snapshot UUID',36)}
    {input('previousNo','Predecessor decision number',50)}{input('previousDecision','Predecessor decision',30)}
    {input('previousReadiness','Predecessor readiness declaration',30)}{input('decisionNo','New decision number',50)}
    {input('actor','Declared authority — retained text, not authenticated identity',120)}
    {input('readiness','New readiness declaration',30)}{input('decision','New decision',30)}
    <label><Localized>{'New decision notes'}</Localized><textarea name="notes" maxLength={4000} value={fields.notes} onChange={e=>edit('notes',e.target.value)}/></label>
    <label><Localized>{'Correction reason'}</Localized><textarea name="correctionReason" required maxLength={4000} value={fields.correctionReason} onChange={e=>edit('correctionReason',e.target.value)}/></label>
    <button type="submit"><Localized>{'Prepare replacement request'}</Localized></button></fieldset></form>
  {current&&<section><h3><Localized>{imported.current?'Imported replacement request — unverified preparation metadata':'Review exact release decision replacement'}</Localized></h3>
   <p><Localized>{'New approved request number'}</Localized>: {current.command.target}</p>
   <p><Localized>{'Predecessor decision UUID'}</Localized>: <code>{current.command.predecessor.id}</code></p>
   <p><Localized>{'Predecessor decision number'}</Localized>: {current.command.predecessor.decision_no}</p>
   <p><Localized>{'Release UUID'}</Localized>: <code>{current.command.predecessor.release_id}</code></p>
   <p><Localized>{'Frozen snapshot UUID'}</Localized>: <code>{current.command.predecessor.snapshot_id}</code></p>
   <p><Localized>{'New decision number'}</Localized>: {current.command.body.decision_no}</p>
   <p><Localized>{'New decision'}</Localized>: {current.command.body.decision}</p>
   <p><Localized>{'Correction reason'}</Localized>: {current.command.body.correction_reason}</p>
   {!result&&<label><input type="checkbox" checked={current.confirmed} disabled={copying} onChange={e=>{if(copyPending.current||controller.current||!matches())return;const next=confirmReleaseDecisionSupersession(current.command,e.target.checked);active.current=next;setReview(next);setRevealed(false);}}/>
    <Localized>{'I confirm the exact predecessor, new approval and replacement request.'}</Localized></label>}
   <div className="actions">{!imported.current&&<button type="button" disabled={!current.confirmed||busy||!submissionEnabled} onClick={()=>run('send')}><Localized>{'Send confirmed replacement request'}</Localized></button>}
    <button type="button" disabled={!current.confirmed||busy||!recoveryEnabled} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>
    <button type="button" disabled={!current.confirmed||busy} onClick={()=>copy()}><Localized>{'Copy confirmed request'}</Localized></button></div>
   <p className="notice"><Localized>{'Replacement recovery contains approval and release identifiers, declared authority, reasons and notes. Store it securely on your device; do not share or upload it. It contains no session credentials and is not proof of execution.'}</Localized></p>
   <p><Localized>{'Predecessor number, decision and readiness are unverified preparation metadata, including after audit confirmation. The original audit verifies the original request and predecessor UUID, not those descriptive labels or the current effective decision.'}</Localized></p>
   {current.confirmed&&<><button type="button" disabled={busy} onClick={()=>{if(copyPending.current||!matches()||busy)return;setRevealed(true);}}><Localized>{'Reveal replacement recovery text'}</Localized></button>
    <button type="button" disabled={busy} onClick={()=>copy(true)}><Localized>{'Copy replacement recovery text'}</Localized></button>
    {recoveryText&&<textarea name="replacementRecoveryExport" aria-label="Replacement recovery text" readOnly value={recoveryText}/>}</>}

   <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(current.command,null,2)}</pre></section>}
  {!controller.current&&!current&&<section><h3><Localized>{'Recover a saved replacement request'}</Localized></h3>
   <p><Localized>{'Import is audit-only and makes no request. A fresh valid session for the original authority may query its original audit; imported data cannot submit, retry or grant permission.'}</Localized></p>
   <label><Localized>{'Replacement recovery text'}</Localized><textarea name="replacementRecoveryImport" maxLength={32768} disabled={copying} value={importText} onChange={e=>{if(copyPending.current||controller.current||active.current||currentKey.current!==key)return;importSource.current=e.target.value;setImportText(e.target.value);}}/></label>
   <button type="button" disabled={copying||!importText} onClick={stageRecovery}><Localized>{'Import replacement request for audit query only'}</Localized></button></section>}
  {message&&<p className="muted"><Localized>{message}</Localized></p>}{result&&<ReleaseDecisionSupersessionResult state={result}/>}
  {(result?.phase==='confirmed'||result?.phase==='rejected')&&<button type="button" onClick={reset}><Localized>{'Start a new request'}</Localized></button>}
 </section></Localized>;
}
