'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import AcceptanceCorrectionResult from './acceptance-correction-result';
import {parseAcceptanceCorrectionCommand,confirmAcceptanceCorrection,AcceptanceCorrectionSubmission,
  type AcceptanceCorrectionReview,type AcceptanceCorrectionState} from '../lib/acceptance-correction-transport';

export type CorrectionFields={target:string;criterion:string;predecessor:string;previousDvp:string;previousAction:string;action:string;dvp:string;actor:string;reason:string};
const blank:CorrectionFields={target:'',criterion:'',predecessor:'',previousDvp:'',previousAction:'ASSIGN',action:'SUPERSEDE',dvp:'',actor:'',reason:''};
export default function AcceptanceCorrectionWorkbench({initialContext={},submissionEnabled=false,recoveryEnabled=false}:{
  initialContext?:Partial<CorrectionFields>;submissionEnabled?:boolean;recoveryEnabled?:boolean;
}) {
  const [fields,setFields]=useState<CorrectionFields>({...blank,...initialContext});
  const [review,setReview]=useState<AcceptanceCorrectionReview|null>(null);
  const [result,setResult]=useState<AcceptanceCorrectionState|null>(null);
  const [message,setMessage]=useState('');
  const [copying,setCopying]=useState(false);
  const controller=useRef<AcceptanceCorrectionSubmission|null>(null),copyPending=useRef(false);
  const capability=useRef({submit:submissionEnabled,recover:recoveryEnabled});
  capability.current={submit:submissionEnabled,recover:recoveryEnabled};
  const key=JSON.stringify(initialContext),currentKey=useRef(key),previousKey=useRef(key);currentKey.current=key;
  const current=result?.review??(previousKey.current===key?review:null);
  const active=useRef(current);active.current=current;
  const preparation=useRef(fields);preparation.current=fields;
  const busy=copying||result?.phase==='sending'||result?.phase==='checking';
  useEffect(()=>{
    if(previousKey.current===key)return;
    previousKey.current=key;
    if(!controller.current){setFields({...blank,...initialContext});setReview(null);setMessage('');}
  },[key]);
  useEffect(()=>{
    if(!result||!['sending','checking','unknown'].includes(result.phase))return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[result?.phase]);
  function matches(){return active.current===current && (controller.current?controller.current.state.review===current:currentKey.current===key);}
  function edit(name:keyof CorrectionFields,value:string){
    if(controller.current||copyPending.current||currentKey.current!==key)return;
    active.current=null;preparation.current={...fields,[name]:value};setFields(preparation.current);setReview(null);setMessage('');
  }
  async function run(mode:'send'|'recover'){
    if(!current?.confirmed||!matches()||copyPending.current||!(mode==='send'?capability.current.submit:capability.current.recover))return;
    if(!controller.current){if(mode==='recover')return;controller.current=new AcceptanceCorrectionSubmission(current);}
    const pending=mode==='send'?controller.current.send(capability.current.submit):controller.current.recover(capability.current.recover);
    active.current=controller.current.state.review;setResult(controller.current.state);setMessage('');setResult(await pending);
  }
  async function copy(){
    if(!current?.confirmed||!matches()||copyPending.current||['sending','checking'].includes(controller.current?.state.phase??''))return;
    copyPending.current=true;setCopying(true);
    try{await navigator.clipboard.writeText(JSON.stringify(current.command));
      if(controller.current||currentKey.current===key)setMessage('Original correction request copied. Copying does not send an operation.');
    }catch{if(controller.current||currentKey.current===key)setMessage('Clipboard unavailable. Select and copy the confirmed request below.');}
    finally{copyPending.current=false;setCopying(false);}
  }
  function reset(){
    if(!matches()||copyPending.current||(controller.current&&!['confirmed','rejected'].includes(controller.current.state.phase)))return;
    controller.current=null;active.current=null;setResult(null);setReview(null);setMessage('');setFields({...blank,...initialContext});
  }
  const input=(name:keyof CorrectionFields,label:string,maxLength:number)=><label><Localized>{label}</Localized><input name={name} required maxLength={maxLength} value={fields[name]} onChange={e=>edit(name,e.target.value)}/></label>;
  return <Localized><section className="panel">
    <h2><Localized>{'Correct an acceptance-to-DVP relationship'}</Localized></h2>
    <p className="notice"><Localized>{'Replacement and withdrawal append history. Review the exact predecessor; the API checks its current effectiveness and permission. Ordinary assignment uses its separate form.'}</Localized></p>
    {!submissionEnabled&&<p><Localized>{'Acceptance correction submission is disabled in this environment.'}</Localized></p>}
    <form className="commandform" onSubmit={e=>{
      e.preventDefault();if(controller.current||copyPending.current||currentKey.current!==key||active.current||preparation.current!==fields)return;
      const command=parseAcceptanceCorrectionCommand({operation:'acceptance-correction',target:fields.target,
        body:{request_id:crypto.randomUUID(),actor_name:fields.actor,reason:fields.reason,criterion_id:fields.criterion,
          dvp_item_id:fields.action==='WITHDRAW'?fields.previousDvp:fields.dvp,action:fields.action,supersedes_id:fields.predecessor},
        predecessor:{id:fields.predecessor,criterion_id:fields.criterion,dvp_item_id:fields.previousDvp,action:fields.previousAction}});
      if(!command){setMessage('The acceptance correction context or request is invalid.');return;}
      const next=confirmAcceptanceCorrection(command,false);active.current=next;setReview(next);setMessage('Review the target and request before copying.');
    }}>
      <fieldset className="commandfields" disabled={copying||result!==null}>
        {input('target','SCR number',50)}{input('criterion','Acceptance criterion UUID',36)}
        {input('predecessor','Predecessor assignment UUID',36)}{input('previousDvp','Predecessor DVP UUID',36)}
        <label><Localized>{'Predecessor action'}</Localized><select name="previousAction" value={fields.previousAction} onChange={e=>edit('previousAction',e.target.value)}>
          {['ASSIGN','SUPERSEDE'].map(v=><option key={v} value={v}><Localized>{v}</Localized></option>)}
        </select></label>
        <label><Localized>{'Correction action'}</Localized><select name="action" value={fields.action} onChange={e=>edit('action',e.target.value)}>
          {['SUPERSEDE','WITHDRAW'].map(v=><option key={v} value={v}><Localized>{v}</Localized></option>)}
        </select></label>
        {fields.action==='SUPERSEDE'?input('dvp','Replacement DVP UUID',36):<p><Localized>{'Withdrawal retains the predecessor DVP item in the original record.'}</Localized></p>}
        {input('actor','Declared operator — retained text, not authenticated identity',120)}
        <label><Localized>{'Reason'}</Localized><textarea name="reason" required maxLength={4000} value={fields.reason} onChange={e=>edit('reason',e.target.value)}/></label>
        <button type="submit" disabled={current!==null}><Localized>{'Prepare correction request'}</Localized></button>
      </fieldset>
    </form>
    {current&&<section>
      <h3><Localized>{'Review exact correction context'}</Localized></h3>
      <p><Localized>{'Correction action'}</Localized>: <Localized>{current.command.body.action}</Localized></p>
      <p><Localized>{'SCR number'}</Localized>: {current.command.target}</p>
      <p><Localized>{'Request ID'}</Localized>: <code>{current.command.body.request_id}</code></p>
      <p><Localized>{'Predecessor assignment UUID'}</Localized>: <code>{current.command.predecessor.id}</code></p>
      <p><Localized>{'Acceptance criterion UUID'}</Localized>: <code>{current.command.body.criterion_id}</code></p>
      <p><Localized>{'Predecessor action'}</Localized>: <Localized>{current.command.predecessor.action}</Localized></p>
      <p><Localized>{'Predecessor DVP UUID'}</Localized>: <code>{current.command.predecessor.dvp_item_id}</code></p>
      <p><Localized>{'DVP UUID in this correction'}</Localized>: <code>{current.command.body.dvp_item_id}</code></p>
      <p><Localized>{'Declared reviewer'}</Localized>: {current.command.body.actor_name}</p>
      <p><Localized>{'Reason'}</Localized>: {current.command.body.reason}</p>
      <pre><code>{JSON.stringify(current.command,null,2)}</code></pre>
      {!result&&<label><input type="checkbox" checked={current.confirmed} disabled={copying} onChange={e=>{
        if(controller.current||copyPending.current||!matches())return;
        const next=confirmAcceptanceCorrection(current.command,e.target.checked);active.current=next;setReview(next);
      }}/><Localized>{'I confirm this exact predecessor, action, DVP item, reason and request ID.'}</Localized></label>}
      <p><button type="button" disabled={!current.confirmed||busy} onClick={copy}><Localized>{'Copy confirmed correction request'}</Localized></button>
        {!result&&submissionEnabled&&<button type="button" disabled={!current.confirmed||busy} onClick={()=>run('send')}><Localized>{'Send confirmed correction request'}</Localized></button>}
        {result&&['unknown','rejected'].includes(result.phase)&&<button type="button" disabled={!submissionEnabled||busy} onClick={()=>run('send')}><Localized>{'Retry original correction request'}</Localized></button>}
        {result&&result.phase!=='confirmed'&&<button type="button" disabled={!recoveryEnabled||busy} onClick={()=>run('recover')}><Localized>{'Query original audit without resubmitting'}</Localized></button>}
        {(!result||['confirmed','rejected'].includes(result.phase))&&<button type="button" disabled={busy} onClick={reset}><Localized>{'Start a new request'}</Localized></button>}
      </p>
    </section>}
    {message&&<p role="status"><Localized>{message}</Localized></p>}
    {result&&<AcceptanceCorrectionResult state={result}/>}
  </section></Localized>;
}
