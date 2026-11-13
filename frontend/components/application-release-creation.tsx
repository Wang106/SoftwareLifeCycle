'use client';
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {usePathname,useSearchParams} from 'next/navigation';
import {Localized} from './localized';
import {CreationSubmission,parseTarget,parseContext,parseCommand,readCreationResponse,verifyContextDigest,exportCreationRecovery,importCreationRecovery,type Command,type CreationState} from '../lib/application-release-creation';
export default function ApplicationReleaseCreation({enabled=false}:{enabled?:boolean}){
 const pathname=usePathname(),query=useSearchParams();
 const [fields,setFields]=useState({project_id:'',standard_base_release_id:'',version:'',release_notes:'',reason:''});
 const [review,setReview]=useState<Command|null>(null),[confirmed,setConfirmed]=useState(false),[state,setState]=useState<CreationState|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[recovery,setRecovery]=useState('');
 const generation=useRef(0),active=useRef(false),submission=useRef<CreationSubmission|null>(null),heading=useRef<HTMLHeadingElement>(null);
 const locked=!!submission.current;
 useEffect(()=>{generation.current++;setReview(null);setConfirmed(false);heading.current?.focus();},[pathname,query]);
 useEffect(()=>{return()=>{generation.current++;};},[]);
 useEffect(()=>{const prevent=(event:BeforeUnloadEvent)=>{if(submission.current&&submission.current.state.phase!=='confirmed'){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',prevent);return()=>window.removeEventListener('beforeunload',prevent);},[]);
 function change(name:keyof typeof fields,value:string){if(locked)return;generation.current++;setFields({...fields,[name]:value});setReview(null);setConfirmed(false);setMessage('');}
 async function prepare(){if(active.current||locked)return;setReview(null);setConfirmed(false);const target=parseTarget({project_id:fields.project_id.trim().toLowerCase(),standard_base_release_id:fields.standard_base_release_id.trim().toLowerCase()});
  if(!target||!fields.version.trim()||fields.version.trim().length>100||!fields.reason.trim()||fields.reason.trim().length>4000||fields.release_notes.length>4000){setMessage('Enter exact UUIDs, a version and a reason within the stated limits.');return;}
  if(!enabled){setMessage('Currently cannot save online. The public sample is read-only; real identity is not configured.');return;}
  const token=++generation.current;active.current=true;setBusy(true);
  try{const response=await fetch('/auth/application-release-context',{method:'POST',body:JSON.stringify(target),headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});const value=await readCreationResponse(response);if(token!==generation.current)return;const context=response.status===200?parseContext(value,target):null;if(!context||!await verifyContextDigest(context))throw Error('context');if(token!==generation.current)return;
   const command=parseCommand({context,body:{...target,request_id:crypto.randomUUID(),version:fields.version.trim(),release_notes:fields.release_notes===''?null:fields.release_notes,reason:fields.reason.trim(),expected_context_digest:context.context_digest}});if(!command)throw Error('input');setReview(command);setMessage('Review the exact project, derived customer and software, and standard release status.');
  }catch{if(token===generation.current)setMessage('Context unavailable or changed. Check identity, permissions and exact UUIDs.');}finally{active.current=false;setBusy(false);}
 }
 async function send(recover=false){if(active.current||!enabled)return;let controller=submission.current;if(!controller){if(!review||!confirmed||recover)return;controller=new CreationSubmission(review,true);submission.current=controller;}active.current=true;setBusy(true);const pending=recover?controller.recover(enabled):controller.send(enabled);setState(controller.state);try{setState(await pending);}finally{active.current=false;setBusy(false);}}
 return <section><h1 tabIndex={-1} ref={heading}><Localized>{'Create application release draft'}</Localized></h1>
 <p><Localized>{'Draft association does not establish approval or delivery permission, including when the SSR record says RELEASED.'}</Localized></p>
 <p><Localized>{'Create an empty DRAFT only. No snapshot, approval, files, components or upload.'}</Localized></p>
 <Localized>{!enabled&&<p role="status"><Localized>{'Currently cannot save online. The public sample is read-only; real identity is not configured.'}</Localized></p>}</Localized>
 <form onSubmit={event=>{event.preventDefault();void prepare();}}>
 <fieldset disabled={locked}><legend><Localized>{'Exact creation inputs'}</Localized></legend>
 <Localized>{([['project_id','Project UUID',36],['standard_base_release_id','Standard release UUID',36],['version','Version (maximum 100 characters)',100],['release_notes','Release notes (optional, maximum 4000 characters)',4000],['reason','Reason (maximum 4000 characters)',4000]] as const).map(([name,label,max])=><p key={name}><label htmlFor={'asr-'+name}><Localized>{label}</Localized></label><br/>{name==='reason'||name==='release_notes'?<textarea id={'asr-'+name} value={fields[name]} maxLength={max} required={name==='reason'} onChange={e=>change(name,e.target.value)}/>:<input id={'asr-'+name} value={fields[name]} maxLength={max} required onChange={e=>change(name,e.target.value)}/>}</p>)}</Localized>
 <button type="submit" disabled={busy}><Localized>{'Prepare immutable preview'}</Localized></button></fieldset></form>
 <p role="status" aria-live="polite"><Localized>{message}</Localized></p>
 <Localized>{review&&<section aria-label="Creation review"><h2><Localized>{'Immutable creation preview'}</Localized></h2><dl>{Object.entries(review.context.context).map(([key,value])=><div key={key}><dt><Localized>{key}</Localized></dt><dd>{value}</dd></div>)}</dl>
 <p><Localized>{'SSR record status'}</Localized>: <strong>{review.context.context.standard_base_status}</strong></p>
 {review.context.context.standard_base_status!=='RELEASED'&&<p role="alert"><Localized>{'Warning: this SSR record is not marked RELEASED. A draft association is still allowed.'}</Localized></p>}
 <p><Localized>{'Version'}</Localized>: {review.body.version}</p><p><Localized>{'Release notes'}</Localized>: {review.body.release_notes??'—'}</p><p><Localized>{'Reason'}</Localized>: {review.body.reason}</p><p><Localized>{'Request UUID'}</Localized>: {review.body.request_id}</p>
 <label><input type="checkbox" checked={confirmed} disabled={locked} onChange={e=>setConfirmed(e.target.checked)}/><Localized>{'I confirm this exact empty DRAFT request and its standard release status.'}</Localized></label>
 <p><button type="button" disabled={!enabled||!confirmed||busy||locked} onClick={()=>void send()}><Localized>{'Submit empty DRAFT'}</Localized></button> <button type="button" disabled={busy||locked} onClick={()=>{generation.current++;setReview(null);setConfirmed(false);}}><Localized>{'Cancel preview'}</Localized></button></p></section>}</Localized>
 <Localized>{locked&&<p><label htmlFor="asr-recovery-export"><Localized>{'Save this private recovery text before leaving. It contains the original request, not credentials; keep it private.'}</Localized></label><textarea id="asr-recovery-export" readOnly value={exportCreationRecovery(submission.current!.command,window.location.origin)}/></p>}</Localized>
 <Localized>{!locked&&<section><h2><Localized>{'Recover an earlier request'}</Localized></h2><p><Localized>{'Pasting recovery text only restores the original request locally. Checking its audit receipt never resubmits it.'}</Localized></p><textarea aria-label="Original recovery request" maxLength={32768} value={recovery} onChange={e=>setRecovery(e.target.value)}/><button type="button" disabled={busy} onClick={()=>{try{const c=importCreationRecovery(recovery,window.location.origin);if(!c)throw Error();submission.current=new CreationSubmission(c,true);setReview(c);setConfirmed(false);setState({phase:'unknown',receipt:null});setRecovery('');}catch{setMessage('Invalid recovery request. No network request was sent.');}}}><Localized>{'Restore for receipt lookup only'}</Localized></button></section>}</Localized>
 <Localized>{state&&<div role="status" aria-live="polite"><Localized>{state.phase==='confirmed'?'Original audit receipt verified. Empty DRAFT created.':state.phase==='rejected'?'Request rejected. Review the reported reason; the original request will not be automatically retried.':state.phase==='unknown'?'Outcome unknown. Do not submit again. Keep this page open and check the original audit receipt.':state.phase==='sending'?'Submitting the exact request.':'Checking the original receipt.'}</Localized>
 {state.error&&<p><Localized>{state.error}</Localized></p>}
 {['unknown','rejected'].includes(state.phase)&&<button type="button" disabled={busy||!enabled} onClick={()=>void send(true)}><Localized>{'Check original audit receipt'}</Localized></button>}
 {state.receipt&&<p><Link prefetch={false} href={'/releases/application/'+state.receipt.release_id}><Localized>{'Open newly created application release'}</Localized></Link> · {state.receipt.release_id} · {state.receipt.audit_event_no}</p>}</div>}</Localized>
 </section>;
}
