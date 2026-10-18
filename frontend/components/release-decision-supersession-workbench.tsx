'use client';
import {useRef,useState} from 'react';
import {Localized} from './localized';
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
 const controller=useRef<ReleaseDecisionSupersessionSubmission|null>(null),busy=result?.phase==='sending'||result?.phase==='checking',current=result?.review??review;
 const edit=(name:keyof Fields,value:string)=>{if(controller.current)return;setFields({...fields,[name]:value});setReview(null);setMessage('');};
 async function run(mode:'send'|'recover'){if(!current?.confirmed||busy)return;if(!controller.current)controller.current=new ReleaseDecisionSupersessionSubmission(current);
  const pending=mode==='send'?controller.current.send(submissionEnabled):controller.current.recover(recoveryEnabled);setResult(controller.current.state);setResult(await pending);}
 function reset(){if(busy||result?.phase==='unknown')return;controller.current=null;setResult(null);setReview(null);setMessage('');setFields({...blank,...initialContext});}
 const input=(name:keyof Fields,label:string,max:number)=><label><Localized>{label}</Localized><input name={name} required maxLength={max} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label>;
 return <Localized><section className="panel"><h2><Localized>{'Replace a release decision'}</Localized></h2>
  <p className="notice"><Localized>{'Replacement appends a new formal decision for a new approved request and the same frozen snapshot. It never edits the predecessor.'}</Localized></p>
  <Localized>{!submissionEnabled&&<p><Localized>{'Release decision replacement submission is disabled in this environment.'}</Localized></p>}</Localized>
  <form className="commandform" onSubmit={e=>{e.preventDefault();if(controller.current||review)return;
   const command=parseReleaseDecisionSupersessionCommand({operation:'release-decision-supersession',target:fields.target,
    body:{request_id:crypto.randomUUID(),decision_no:fields.decisionNo,decided_by:fields.actor,readiness_status:fields.readiness,
      decision:fields.decision,notes:fields.notes.trim()||null,supersedes_id:fields.predecessor,correction_reason:fields.correctionReason},
    predecessor:{id:fields.predecessor,release_id:fields.release,snapshot_id:fields.snapshot,decision_no:fields.previousNo,
      decision:fields.previousDecision,readiness_status:fields.previousReadiness}});
   if(!command){setMessage('The release decision replacement context or request is invalid.');return;}
   setReview(confirmReleaseDecisionSupersession(command,false));setMessage('Review the exact predecessor, new approval and replacement request before confirming.');}}>
   <fieldset className="commandfields" disabled={!!review||!!result}>{input('target','New approved request number',50)}
    {input('predecessor','Predecessor decision UUID',36)}{input('release','Release UUID',36)}{input('snapshot','Frozen snapshot UUID',36)}
    {input('previousNo','Predecessor decision number',50)}{input('previousDecision','Predecessor decision',30)}
    {input('previousReadiness','Predecessor readiness declaration',30)}{input('decisionNo','New decision number',50)}
    {input('actor','Declared authority — retained text, not authenticated identity',120)}
    {input('readiness','New readiness declaration',30)}{input('decision','New decision',30)}
    <label><Localized>{'New decision notes'}</Localized><textarea name="notes" maxLength={4000} value={fields.notes} onChange={e=>edit('notes',e.target.value)}/></label>
    <label><Localized>{'Correction reason'}</Localized><textarea name="correctionReason" required maxLength={4000} value={fields.correctionReason} onChange={e=>edit('correctionReason',e.target.value)}/></label>
    <button type="submit"><Localized>{'Prepare replacement request'}</Localized></button></fieldset></form>
  {current&&<section><h3><Localized>{'Review exact release decision replacement'}</Localized></h3>
   <p><Localized>{'New approved request number'}</Localized>: {current.command.target}</p>
   <p><Localized>{'Predecessor decision UUID'}</Localized>: <code>{current.command.predecessor.id}</code></p>
   <p><Localized>{'Predecessor decision number'}</Localized>: {current.command.predecessor.decision_no}</p>
   <p><Localized>{'Release UUID'}</Localized>: <code>{current.command.predecessor.release_id}</code></p>
   <p><Localized>{'Frozen snapshot UUID'}</Localized>: <code>{current.command.predecessor.snapshot_id}</code></p>
   <p><Localized>{'New decision number'}</Localized>: {current.command.body.decision_no}</p>
   <p><Localized>{'New decision'}</Localized>: {current.command.body.decision}</p>
   <p><Localized>{'Correction reason'}</Localized>: {current.command.body.correction_reason}</p>
   {!result&&<label><input type="checkbox" checked={current.confirmed} onChange={e=>setReview(confirmReleaseDecisionSupersession(current.command,e.target.checked))}/>
    <Localized>{'I confirm the exact predecessor, new approval and replacement request.'}</Localized></label>}
   <div className="actions"><button type="button" disabled={!current.confirmed||busy||!submissionEnabled} onClick={()=>run('send')}><Localized>{'Send confirmed replacement request'}</Localized></button>
    <button type="button" disabled={!current.confirmed||busy||!recoveryEnabled} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>
    <button type="button" disabled={!current.confirmed||busy} onClick={async()=>{try{await navigator.clipboard.writeText(JSON.stringify(current.command));setMessage('Original replacement request copied. Copying does not send an operation.');}catch{setMessage('Clipboard unavailable. Select and copy the confirmed request below.');}}}><Localized>{'Copy confirmed request'}</Localized></button></div>
   <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(current.command,null,2)}</pre></section>}
  {message&&<p className="muted"><Localized>{message}</Localized></p>}{result&&<ReleaseDecisionSupersessionResult state={result}/>}
  {(result?.phase==='confirmed'||result?.phase==='rejected')&&<button type="button" onClick={reset}><Localized>{'Start a new request'}</Localized></button>}
 </section></Localized>;
}
