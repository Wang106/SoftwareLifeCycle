'use client';
import { useEffect, useRef, useState } from 'react';
import {exportRegistrationRecovery,importRegistrationRecovery,registrationRecoveryTextLimit,type ImportedRegistrationRecovery,type RegistrationRecoveryState} from '../lib/admin-registration-recovery';
import AdminRegistrationRecoveryResult from './admin-registration-recovery-result';
import AdminRegistrationResult from './admin-registration-result';
import { RegistrationSubmission, type RegistrationSubmissionState } from '../lib/admin-registration-transport';
import { Localized } from './localized';
import { prepareRegistration, confirmRegistration, exportRegistration, registrationRoles,
  type RegistrationKind, type RegistrationInput, type RegistrationReview } from '../lib/admin-registration-draft';

export default function AdminRegistrationPreparation({ submissionEnabled = false, recoveryEnabled = false }: { submissionEnabled?: boolean; recoveryEnabled?: boolean }) {
  const [kind,setKind] = useState<RegistrationKind>('PRINCIPAL');
  const [newId,setNewId] = useState('');
  const [principalId,setPrincipalId] = useState('');
  const [scopeId,setScopeId] = useState('');
  const [principalType,setPrincipalType] = useState<'USER' | 'SERVICE'>('USER');
  const [subject,setSubject] = useState('');
  const [displayName,setDisplayName] = useState('');
  const [role,setRole] = useState('AUDITOR');
  const [eventNo,setEventNo] = useState('');
  const [reason,setReason] = useState('');
  const [review,setReview] = useState<RegistrationReview | null>(null);
  const [message,setMessage] = useState('');
  const [copying,setCopying] = useState(false);
  const submission = useRef<RegistrationSubmission | null>(null);
  const [result,setResult] = useState<RegistrationSubmissionState | null>(null);
  const recovery=useRef<ImportedRegistrationRecovery|null>(null),imported=useRef(false),copyPending=useRef(false);
  const [recovered,setRecovered]=useState<RegistrationRecoveryState|null>(null),[recoveryText,setRecoveryText]=useState(''),[importText,setImportText]=useState('');
  const active=useRef(review),importSource=useRef(''),capability=useRef({submit:submissionEnabled,recover:recoveryEnabled});active.current=review;capability.current={submit:submissionEnabled,recover:recoveryEnabled};
  const locked = result !== null || recovered !== null;
  const busy=copying||result?.phase==='sending'||recovered?.phase==='checking';
  useEffect(() => {
    if (!['sending','unknown'].includes(result?.phase??'') && !['checking','unknown'].includes(recovered?.phase??'')) return;
    if(recovered?.phase==='confirmed')return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload',warn);
    return () => window.removeEventListener('beforeunload',warn);
  },[result?.phase,recovered?.phase]);
  function running(){return submission.current?.state.phase==='sending'||recovery.current?.state.phase==='checking';}
  function edit(change: () => void) { if (copyPending.current || submission.current || recovery.current) return; active.current=null;change();setRecoveryText('');setReview(null); setMessage(''); }
  async function send() {
    if (!review?.confirmed || active.current!==review || !capability.current.submit || copyPending.current || imported.current || recovery.current?.state.phase==='checking' || recovery.current?.state.phase==='confirmed') return;
    if (!submission.current) submission.current = new RegistrationSubmission(review);
    const controller = submission.current, pending = controller.send(capability.current.submit);
    setResult(controller.state); setMessage('');
    const completed=await pending;setResult(completed);
    if(completed.phase==='confirmed'){recovery.current=null;setRecovered(null);}
  }
  function newRequest() {
    if(copyPending.current||recovery.current?.state.phase==='checking'||(recovery.current?.state.phase!=='confirmed'&&(!submission.current||!['confirmed','rejected'].includes(submission.current.state.phase))))return;
    submission.current = null;recovery.current=null;imported.current=false;active.current=null;importSource.current='';setImportText('');setRecovered(null);setRecoveryText('');setResult(null);setReview(null);
    setNewId(crypto.randomUUID()); setEventNo('ADM-'+crypto.randomUUID());
    setSubject(''); setDisplayName(''); setPrincipalId(''); setScopeId(''); setReason('');
    setMessage('New registration UUID and audit number generated. Review all fields before another operation.');
  }
  function preview() {
    if (copyPending.current || submission.current || recovery.current) return;
    active.current=null;setRecoveryText('');
    const common = {kind,newId,eventNo,reason};
    const input: RegistrationInput = kind === 'PRINCIPAL' ?
      {...common,kind,principalType,subject,displayName} : kind === 'GLOBAL' ?
      {...common,kind,principalId,role} : {...common,kind,principalId,scopeId,role};
    try { const next=prepareRegistration(input);active.current=next;setRecoveryText('');setReview(next); setMessage('Review every exact identity, target, role and audit field.'); }
    catch(error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
  }
  async function copy() {
    if (!review?.confirmed || active.current!==review || copyPending.current || running()) return;
    copyPending.current=true;setCopying(true);
    try { await navigator.clipboard.writeText(exportRegistration(review)); setMessage(submission.current ? 'Original registration request copied. Copying does not send another operation.' : 'Registration request copied. No identity or grant was created.'); }
    catch { setMessage('Clipboard unavailable. Select and copy the confirmed request below.'); }
    finally { copyPending.current=false;setCopying(false); }
  }
  function revealRecovery(){
    if(!review?.confirmed||active.current!==review||copyPending.current||running())return;
    try{setRecoveryText(exportRegistrationRecovery(review,window.location.origin));setMessage('');}catch{setMessage('Registration recovery text could not be prepared. Nothing was sent.');}
  }
  async function copyRecovery(){
    if(!recoveryText||!review?.confirmed||active.current!==review||copyPending.current||running())return;
    copyPending.current=true;setCopying(true);
    try{await navigator.clipboard.writeText(recoveryText);setMessage('Sensitive registration recovery text copied. Keep it locally and securely; copying is not execution proof.');}
    catch{setMessage('Clipboard unavailable. Select and copy the recovery text below.');}
    finally{copyPending.current=false;setCopying(false);}
  }
  function stageRecovery(){
    if(copyPending.current||submission.current||recovery.current||active.current||importSource.current!==importText)return;
    try{const controller=importRegistrationRecovery(importText,window.location.origin);recovery.current=controller;imported.current=true;active.current=controller.state.review;setReview(controller.state.review);setRecovered(controller.state);setRecoveryText('');setImportText('');importSource.current='';setMessage('');}
    catch{setMessage('Registration recovery text is invalid or belongs to another site. Nothing was sent.');}
  }
  async function recover(){
    if(!review?.confirmed||active.current!==review||copyPending.current||submission.current?.state.phase==='sending'||!capability.current.recover)return;
    if(!recovery.current){try{recovery.current=importRegistrationRecovery(exportRegistrationRecovery(review,window.location.origin),window.location.origin);}catch{return;}}
    const controller=recovery.current,pending=controller.recover(capability.current.recover);setRecovered(controller.state);setMessage('');setRecovered(await pending);
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare identity or grant registration'}</Localized></h2>
    <p className="notice"><Localized>{locked && !submissionEnabled ? 'Registration submission is disabled in this environment.' :
      submissionEnabled ? 'Controlled registration is available. Review and confirm the exact request before sending.' :
      'Preparation only. No identity or grant is created by this form.'}</Localized></p>
    <p className="muted"><Localized>{'Use only approved provider identifiers. Keep passwords, tokens and other secrets out of every field and reason.'}</Localized></p>
    <form hidden={imported.current} className="commandform" onSubmit={event=>{event.preventDefault();preview();}}>
      <fieldset disabled={busy || locked} className="commandfields">
        <label><Localized>{'Registration operation'}</Localized><select name="operation" value={kind} onChange={event=>edit(()=>{
          const next=event.target.value as RegistrationKind;
          if (!['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'].includes(next)) return;
          setKind(next);
          if (next!=='PRINCIPAL') setRole(registrationRoles[next][0]);
        })}>
          <option value="PRINCIPAL"><Localized>{'Local identity'}</Localized></option>
          <option value="GLOBAL"><Localized>{'GLOBAL'}</Localized></option>
          <option value="PROJECT"><Localized>{'PROJECT'}</Localized></option>
          <option value="SOFTWARE"><Localized>{'SOFTWARE'}</Localized></option>
        </select></label>
        <label><Localized>{kind==='PRINCIPAL'?'New principal UUID':'New grant UUID'}</Localized>
          <input required name="new_id" value={newId} onChange={event=>edit(()=>setNewId(event.target.value))} /></label>
        <button className="btn" type="button" onClick={()=>edit(()=>setNewId(crypto.randomUUID()))}>
          <Localized>{'Generate registration UUID'}</Localized>
        </button>
        <Localized>{kind==='PRINCIPAL' ? <>
          <label><Localized>{'Principal type'}</Localized><select name="principal_type" value={principalType}
            onChange={event=>edit(()=>setPrincipalType(event.target.value as 'USER' | 'SERVICE'))}>
            <option value="USER"><Localized>{'USER'}</Localized></option>
            <option value="SERVICE"><Localized>{'SERVICE'}</Localized></option>
          </select></label>
          <label><Localized>{'Exact provider subject'}</Localized><textarea required name="subject" value={subject}
            onChange={event=>edit(()=>setSubject(event.target.value))} /></label>
          <label><Localized>{'Display name'}</Localized><input required name="display_name" value={displayName}
            onChange={event=>edit(()=>setDisplayName(event.target.value))} /></label>
          <p className="muted"><Localized>{'The server supplies the configured issuer. Registration creates a disabled local identity without roles and does not create a provider account.'}</Localized></p>
        </> : <>
          <label><Localized>{'Existing principal UUID'}</Localized><input required name="principal_id" value={principalId}
            onChange={event=>edit(()=>setPrincipalId(event.target.value))} /></label>
          <Localized>{kind!=='GLOBAL' && <label><Localized>{kind==='PROJECT'?'Exact project UUID':'Exact software UUID'}</Localized>
            <input required name="scope_id" value={scopeId} onChange={event=>edit(()=>setScopeId(event.target.value))} /></label>}</Localized>
          <label><Localized>{'Role'}</Localized><select name="role" value={role}
            onChange={event=>edit(()=>setRole(event.target.value))}>
            <Localized>{registrationRoles[kind].map(value=><option key={value} value={value}><Localized>{value}</Localized></option>)}</Localized>
          </select></label>
          <p className="muted"><Localized>{'Registration creates one suspended grant. The recipient must be eligible; a separate audited resume is required before it becomes effective.'}</Localized></p>
          <Localized>{kind!=='GLOBAL' && <p className="muted"><Localized>{
            'Project and software registration cannot target a principal with a platform administrator grant. The API decides eligibility.'}</Localized></p>}</Localized>
        </>}</Localized>
        <label><Localized>{'Audit event number'}</Localized><input required name="event_no" maxLength={50} value={eventNo}
          onChange={event=>edit(()=>setEventNo(event.target.value))} /></label>
        <button className="btn" type="button" onClick={()=>edit(()=>setEventNo('ADM-'+crypto.randomUUID()))}>
          <Localized>{'Generate audit number'}</Localized>
        </button>
        <label><Localized>{'Reason'}</Localized><textarea required name="reason" value={reason}
          onChange={event=>edit(()=>setReason(event.target.value))} /></label>
        <button className="btn" type="submit"><Localized>{'Preview registration request'}</Localized></button>
      </fieldset>
    </form>
    <p className="muted"><Localized>{'Keep the same registration UUID, audit number and exact body for retries. A preview does not prove that the server will accept the operation.'}</Localized></p>
    <p aria-live="polite"><Localized>{message}</Localized></p>
    <Localized>{review && <>
      <p><Localized>{'Initial registration status'}</Localized><Localized>{': '}</Localized><Localized>{review.initialStatus}</Localized></p>
      <pre><code>{JSON.stringify(review.request,null,2)}</code></pre>
      <label><input type="checkbox" checked={review.confirmed} disabled={busy || locked}
        onChange={event=>{if (copyPending.current || submission.current || recovery.current || active.current!==review) return;const next=confirmRegistration(review,event.target.checked);active.current=next;setReview(next);setRecoveryText('');setMessage('');}} />
        <Localized>{'I reviewed the exact identity or grant, initial status, role, target, reason and audit number.'}</Localized>
      </label>
      <button className="btn" type="button" disabled={!review.confirmed || copying} onClick={copy}>
        <Localized>{'Copy confirmed registration request'}</Localized>
      </button>
      <Localized>{submissionEnabled && !result && !imported.current && !recovered && <button className="btn" type="button"
        disabled={!review.confirmed || copying} onClick={send}><Localized>{'Send confirmed registration request'}</Localized></button>}</Localized>
      <Localized>{!imported.current && recovered?.phase!=='confirmed' && result && ['unknown','rejected'].includes(result.phase) && <button className="btn" type="button"
        disabled={!submissionEnabled || busy} onClick={send}><Localized>{'Retry original registration request'}</Localized></button>}</Localized>
      <Localized>{!imported.current && recovered?.phase!=='confirmed' && result && <AdminRegistrationResult state={result} />}</Localized>
      <Localized>{(recovered?.phase==='confirmed'||result && ['confirmed','rejected'].includes(result.phase)) && <button className="btn" type="button"
        disabled={copying} onClick={newRequest}><Localized>{'Prepare another registration with new identifiers'}</Localized></button>}</Localized>
      <p className="notice"><Localized>{'Recovery text contains sensitive identity metadata, including subject, display name and reason. Keep it locally and securely; do not share or upload it. It is not credentials, permission or execution proof.'}</Localized></p>
      <button type="button" disabled={!review.confirmed||busy} onClick={revealRecovery}><Localized>{'Reveal registration recovery text locally'}</Localized></button>
      {recoveryText&&<><pre><code>{recoveryText}</code></pre><button type="button" disabled={busy} onClick={copyRecovery}><Localized>{'Copy sensitive registration recovery text'}</Localized></button></>}
      {review.confirmed&&recovered?.phase!=='confirmed'&&<button type="button" disabled={!recoveryEnabled||busy} onClick={recover}><Localized>{'Query original registration audit without resubmitting'}</Localized></button>}
      {imported.current&&<p><Localized>{'Imported registration recovery is audit-only. Import does not create identities, grant access, submit or retry.'}</Localized></p>}
      {recovered&&<AdminRegistrationRecoveryResult state={recovered}/>}
    </>}</Localized>
    {!review&&!locked&&<section><h3><Localized>{'Restore original registration audit query'}</Localized></h3>
      <p><Localized>{'Paste recovery text from this exact site. Import is local-only; query the original audit explicitly after authentication.'}</Localized></p>
      <label><Localized>{'Registration recovery text'}</Localized><textarea name="importText" maxLength={registrationRecoveryTextLimit} value={importText} onChange={e=>{if(copyPending.current||submission.current||recovery.current)return;importSource.current=e.target.value;setImportText(e.target.value);}}/></label>
      <button type="button" disabled={busy||!importText} onClick={stageRecovery}><Localized>{'Import registration recovery without sending'}</Localized></button>
    </section>}
  </section></Localized>;
}
