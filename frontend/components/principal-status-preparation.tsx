'use client';
import { useEffect, useRef, useState } from 'react';
import { Localized } from './localized';
import PrincipalStatusResult from './principal-status-result';
import { PrincipalSubmission, type PrincipalSubmissionState } from '../lib/principal-status-transport';
import { preparePrincipalStatus, confirmPrincipalStatus, exportPrincipalStatus, principalPreparationError,
  samePrincipalTarget, type PrincipalTarget, type PrincipalReview } from '../lib/principal-status-draft';

export default function PrincipalStatusPreparation({ target, submissionEnabled = false }: { target: PrincipalTarget; submissionEnabled?: boolean }) {
  const [eventNo, setEventNo] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<PrincipalReview | null>(null);
  const [message, setMessage] = useState('');
  const [copying, setCopying] = useState(false);
  const submission = useRef<PrincipalSubmission | null>(null);
  const [result, setResult] = useState<PrincipalSubmissionState | null>(null);
  const copyPending = useRef(false);
  const capability = useRef(submissionEnabled);
  capability.current = submissionEnabled;
  const locked = result !== null;
  const displayedTarget = result?.review.target ?? target;
  const targetKey = JSON.stringify([target.id.toLowerCase(), target.principalType, target.status,
    target.historyStatus, target.protectedAdministrator, target.issuerMatchesConfiguration]);
  const currentKey = useRef(targetKey);
  currentKey.current = targetKey;
  const previousKey = useRef(targetKey);
  const error = principalPreparationError(target);
  const currentReview = result?.review ?? (review && !error && samePrincipalTarget(review.target, target) ? review : null);
  useEffect(() => {
    if (previousKey.current !== targetKey) {
      previousKey.current = targetKey;
      if (!submission.current) { setReview(null); setMessage(''); }
    }
  }, [targetKey]);
  useEffect(() => {
    if (result?.phase !== 'sending' && result?.phase !== 'unknown') return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [result?.phase]);
  async function send() {
    if (!currentReview?.confirmed || !capability.current || copyPending.current) return;
    if (!submission.current) {
      if (currentKey.current !== targetKey || error || !samePrincipalTarget(currentReview.target, target)) return;
      submission.current = new PrincipalSubmission(currentReview);
    }
    const controller = submission.current;
    const pending = controller.send(capability.current);
    setResult(controller.state); setMessage('');
    setResult(await pending);
  }
  function newRequest() {
    if (copyPending.current || !submission.current ||
      !['confirmed', 'rejected'].includes(submission.current.state.phase)) return;
    submission.current = null; setResult(null); setReview(null);
    setEventNo('ADM-' + crypto.randomUUID()); setReason('');
    setMessage('A new audit number was generated. Review current detail and history before preparing another operation.');
  }
  function edit(change: () => void) {
    if (copyPending.current || submission.current) return;
    change(); setReview(null); setMessage('');
  }
  async function copy() {
    if (!currentReview?.confirmed || copyPending.current) return;
    const key = targetKey;
    copyPending.current = true; setCopying(true);
    try {
      await navigator.clipboard.writeText(exportPrincipalStatus(currentReview));
      if (submission.current || currentKey.current === key) setMessage(submission.current ?
        'Original identity request copied. Copying does not send another operation.' : 'Identity request copied. No identity change was sent.');
    } catch {
      if (submission.current || currentKey.current === key) setMessage('Clipboard unavailable. Select and copy the confirmed request below.');
    } finally { copyPending.current = false; setCopying(false); }
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare identity status change'}</Localized></h2>
    <p className="notice"><Localized>{locked && !submissionEnabled ? 'Identity status submission is disabled in this environment.' : submissionEnabled ?
      'Controlled submission is available. Review and confirm the exact request before sending.' :
      'Preparation only. This form does not change identities or send an API request.'}</Localized></p>
    <p className="muted"><Localized>{'Disabling revokes existing browser sessions. Enabling does not restore old sessions, grant roles or create a provider account.'}</Localized></p>
    <p className="muted"><Localized>{'The API must independently verify administrator permission, protection and expected status. This preview is not authorization.'}</Localized></p>
    <Localized>{!displayedTarget.issuerMatchesConfiguration && <p className="muted"><Localized>{'Issuer mismatch is informational; changing local status does not repair provider configuration.'}</Localized></p>}</Localized>
    <Localized>{error && !locked ? <p role="alert"><Localized>{error}</Localized></p> : <>
      <p><Localized>{displayedTarget.id.toLowerCase()}</Localized><Localized>{' · '}</Localized><Localized>{displayedTarget.principalType}</Localized></p>
      <p><Localized>{'Expected status'}</Localized><Localized>{': '}</Localized><Localized>{displayedTarget.status}</Localized>
        <Localized>{' · '}</Localized><Localized>{'Requested status'}</Localized><Localized>{': '}</Localized>
        <Localized>{displayedTarget.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'}</Localized></p>
      <form className="commandform" onSubmit={event => {
        event.preventDefault(); if (copyPending.current || submission.current) return;
        try { setReview(preparePrincipalStatus(target, eventNo, reason)); setMessage('Review the exact identity, status change, reason and audit number.'); }
        catch (caught) { setReview(null); setMessage(caught instanceof Error ? caught.message : 'Unable to prepare request.'); }
      }}>
        <fieldset disabled={copying || locked} className="commandfields">
          <label><Localized>{'Audit event number'}</Localized><input required name="event_no" maxLength={50}
            value={eventNo} onChange={event => edit(() => setEventNo(event.target.value))} /></label>
          <button className="btn" type="button" onClick={() => edit(() => setEventNo('ADM-' + crypto.randomUUID()))}>
            <Localized>{'Generate audit number'}</Localized></button>
          <label><Localized>{'Reason'}</Localized><textarea required name="reason" value={reason}
            onChange={event => edit(() => setReason(event.target.value))} /></label>
          <button className="btn" type="submit"><Localized>{'Preview status request'}</Localized></button>
        </fieldset>
      </form>
      <p className="muted"><Localized>{'Keep the same audit number and exact body for retries. Changed content needs a new audit number.'}</Localized></p>
      <p aria-live="polite"><Localized>{message}</Localized></p>
      <Localized>{currentReview && <>
        <pre><code><Localized>{JSON.stringify(currentReview.request, null, 2)}</Localized></code></pre>
        <label><input type="checkbox" checked={currentReview.confirmed} disabled={copying || locked}
          onChange={event => { if (!copyPending.current && !submission.current && currentKey.current === targetKey) { setReview(confirmPrincipalStatus(currentReview, event.target.checked)); setMessage(''); } }} />
          <Localized>{'I reviewed the exact identity, status change, session consequences, reason and audit number.'}</Localized></label>
        <button className="btn" type="button" disabled={!currentReview.confirmed || copying} onClick={copy}>
          <Localized>{'Copy confirmed identity request'}</Localized></button>
        <Localized>{submissionEnabled && !result && <button className="btn" type="button"
          disabled={!currentReview.confirmed || copying} onClick={send}><Localized>{'Send confirmed identity request'}</Localized></button>}</Localized>
        <Localized>{result && ['unknown', 'rejected'].includes(result.phase) && <button className="btn" type="button"
          disabled={!submissionEnabled || copying} onClick={send}><Localized>{'Retry original identity request'}</Localized></button>}</Localized>
        <Localized>{result && <PrincipalStatusResult state={result} />}</Localized>
        <Localized>{result && ['confirmed', 'rejected'].includes(result.phase) && <button className="btn" type="button"
          disabled={copying} onClick={newRequest}><Localized>{'Prepare another operation with a new audit number'}</Localized></button>}</Localized>
      </>}</Localized>
    </>}</Localized>
  </section></Localized>;
}

