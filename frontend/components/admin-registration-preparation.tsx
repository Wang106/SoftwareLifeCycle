'use client';
import { useEffect, useRef, useState } from 'react';
import AdminRegistrationResult from './admin-registration-result';
import { RegistrationSubmission, type RegistrationSubmissionState } from '../lib/admin-registration-transport';
import { Localized } from './localized';
import { prepareRegistration, confirmRegistration, exportRegistration, registrationRoles,
  type RegistrationKind, type RegistrationInput, type RegistrationReview } from '../lib/admin-registration-draft';

export default function AdminRegistrationPreparation({ submissionEnabled = false }: { submissionEnabled?: boolean }) {
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
  const locked = result !== null;
  useEffect(() => {
    if (result?.phase !== 'sending' && result?.phase !== 'unknown') return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload',warn);
    return () => window.removeEventListener('beforeunload',warn);
  },[result?.phase]);
  function edit(change: () => void) { if (copying || submission.current) return; change(); setReview(null); setMessage(''); }
  async function send() {
    if (!review?.confirmed || !submissionEnabled || copying) return;
    if (!submission.current) submission.current = new RegistrationSubmission(review);
    const controller = submission.current, pending = controller.send(submissionEnabled);
    setResult(controller.state); setMessage('');
    setResult(await pending);
  }
  function newRequest() {
    if (!submission.current || !['confirmed','rejected'].includes(submission.current.state.phase)) return;
    submission.current = null; setResult(null); setReview(null);
    setNewId(crypto.randomUUID()); setEventNo('ADM-'+crypto.randomUUID());
    setSubject(''); setDisplayName(''); setPrincipalId(''); setScopeId(''); setReason('');
    setMessage('New registration UUID and audit number generated. Review all fields before another operation.');
  }
  function preview() {
    if (copying || submission.current) return;
    const common = {kind,newId,eventNo,reason};
    const input: RegistrationInput = kind === 'PRINCIPAL' ?
      {...common,kind,principalType,subject,displayName} : kind === 'GLOBAL' ?
      {...common,kind,principalId,role} : {...common,kind,principalId,scopeId,role};
    try { setReview(prepareRegistration(input)); setMessage('Review every exact identity, target, role and audit field.'); }
    catch(error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
  }
  async function copy() {
    if (!review?.confirmed || copying) return;
    setCopying(true);
    try { await navigator.clipboard.writeText(exportRegistration(review)); setMessage(submission.current ? 'Original registration request copied. Copying does not send another operation.' : 'Registration request copied. No identity or grant was created.'); }
    catch { setMessage('Clipboard unavailable. Select and copy the confirmed request below.'); }
    finally { setCopying(false); }
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare identity or grant registration'}</Localized></h2>
    <p className="notice"><Localized>{locked && !submissionEnabled ? 'Registration submission is disabled in this environment.' :
      submissionEnabled ? 'Controlled registration is available. Review and confirm the exact request before sending.' :
      'Preparation only. No identity or grant is created by this form.'}</Localized></p>
    <p className="muted"><Localized>{'Use only approved provider identifiers. Keep passwords, tokens and other secrets out of every field and reason.'}</Localized></p>
    <form className="commandform" onSubmit={event=>{event.preventDefault();preview();}}>
      <fieldset disabled={copying || locked} className="commandfields">
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
      <label><input type="checkbox" checked={review.confirmed} disabled={copying || locked}
        onChange={event=>{if (copying || submission.current) return;setReview(confirmRegistration(review,event.target.checked));setMessage('');}} />
        <Localized>{'I reviewed the exact identity or grant, initial status, role, target, reason and audit number.'}</Localized>
      </label>
      <button className="btn" type="button" disabled={!review.confirmed || copying} onClick={copy}>
        <Localized>{'Copy confirmed registration request'}</Localized>
      </button>
      <Localized>{submissionEnabled && !result && <button className="btn" type="button"
        disabled={!review.confirmed || copying} onClick={send}><Localized>{'Send confirmed registration request'}</Localized></button>}</Localized>
      <Localized>{result && ['unknown','rejected'].includes(result.phase) && <button className="btn" type="button"
        disabled={!submissionEnabled || copying} onClick={send}><Localized>{'Retry original registration request'}</Localized></button>}</Localized>
      <Localized>{result && <AdminRegistrationResult state={result} />}</Localized>
      <Localized>{result && ['confirmed','rejected'].includes(result.phase) && <button className="btn" type="button"
        disabled={copying} onClick={newRequest}><Localized>{'Prepare another registration with new identifiers'}</Localized></button>}</Localized>
    </>}</Localized>
  </section></Localized>;
}
