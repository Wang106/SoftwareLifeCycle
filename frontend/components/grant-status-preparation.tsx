'use client';
import { useEffect, useRef, useState } from 'react';
import { Localized } from './localized';
import GrantStatusResult from './grant-status-result';
import { GrantSubmission, type SubmissionState } from '../lib/grant-status-submission';
import { prepareGrantStatus, confirmGrantStatus, exportGrantStatus, type GrantTarget, type GrantReview } from '../lib/grant-status-draft';

export default function GrantStatusPreparation({ target, submissionEnabled = false }: { target: GrantTarget; submissionEnabled?: boolean }) {
  const [eventNo, setEventNo] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<GrantReview | null>(null);
  const [message, setMessage] = useState('');
  const [copying, setCopying] = useState(false);
  const submission = useRef<GrantSubmission | null>(null);
  const [result, setResult] = useState<SubmissionState | null>(null);
  const locked = result !== null;
  const displayedTarget = result?.review.target ?? target;
  const sameTarget = (value: GrantReview) => value.target.id === target.id.toLowerCase() &&
    value.target.scope === target.scope && value.target.principalId === target.principalId.toLowerCase() &&
    value.target.role === target.role && value.target.status === target.status &&
    value.target.historyStatus === target.historyStatus;
  useEffect(() => {
    // Fresh data invalidates an unattempted preview, but never replaces recovery data.
    if (!submission.current && review && !sameTarget(review)) {
      setReview(null); setMessage('Refresh the grant before preparing a status change.');
    }
  }, [target.id, target.scope, target.principalId, target.role, target.status, target.historyStatus, review]);
  useEffect(() => {
    if (result?.phase !== 'sending' && result?.phase !== 'unknown') return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [result?.phase]);
  function edit(change: () => void) {
    if (submission.current) return;
    change(); setReview(null); setMessage('');
  }
  async function send() {
    if (!review?.confirmed || !submissionEnabled || copying) return;
    if (!submission.current) {
      if (!sameTarget(review)) { setReview(null); setMessage('Refresh the grant before preparing a status change.'); return; }
      submission.current = new GrantSubmission(review);
    }
    const controller = submission.current;
    const pending = controller.send(submissionEnabled);
    setResult(controller.state); setMessage('');
    setResult(await pending);
  }
  function newRequest() {
    if (!result || !['confirmed', 'rejected'].includes(result.phase)) return;
    submission.current = null; setResult(null); setReview(null);
    setEventNo('ADM-' + crypto.randomUUID());
    setMessage('A new audit number was generated. Review current detail and history before preparing another operation.');
  }
  async function copy() {
    if (!review?.confirmed || copying) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(exportGrantStatus(review));
      setMessage(submission.current ? 'Original grant request copied. Copying does not send another operation.' :
        'Grant request copied. No permission change was sent.');
    } catch { setMessage('Clipboard unavailable. Select and copy the confirmed request below.'); }
    finally { setCopying(false); }
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare grant status change'}</Localized></h2>
    <p className="notice"><Localized>{locked && !submissionEnabled ? 'Grant submission is disabled in this environment.' : submissionEnabled ? 'Controlled submission is available. Review and confirm the exact request before sending.' :
      'Preparation only. This form does not change permissions or send an API request.'}</Localized></p>
    <p><Localized>{'Expected status'}</Localized><Localized>{': '}</Localized><Localized>{displayedTarget.status}</Localized>
      <Localized>{' · '}</Localized><Localized>{'Requested status'}</Localized><Localized>{': '}</Localized>
      <Localized>{displayedTarget.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE'}</Localized></p>
    <Localized>{target.scope === 'GLOBAL' && target.role === 'PLATFORM_ADMIN' && <p className="muted">
      <Localized>{'The API protects the last active administrator. This preview does not prove that a suspension will be allowed.'}</Localized>
    </p>}</Localized>
    <Localized>{target.status !== target.historyStatus && <p role="alert">
      <Localized>{'Refresh the grant before preparing a status change.'}</Localized>
    </p>}</Localized>
    <form className="commandform" onSubmit={event => {
      event.preventDefault();
      if (submission.current) return;
      try { setReview(prepareGrantStatus(target, eventNo, reason)); setMessage('Review the exact grant, reason and audit number.'); }
      catch (error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
    }}>
      <fieldset disabled={copying || locked} className="commandfields">
        <label><Localized>{'Audit event number'}</Localized><input required name="event_no" maxLength={50}
          value={eventNo} onChange={event => edit(() => setEventNo(event.target.value))} /></label>
        <button className="btn" type="button" onClick={() => edit(() => setEventNo('ADM-' + crypto.randomUUID()))}>
          <Localized>{'Generate audit number'}</Localized>
        </button>
        <label><Localized>{'Reason'}</Localized><textarea required name="reason" value={reason}
          onChange={event => edit(() => setReason(event.target.value))} /></label>
        <button className="btn" type="submit"><Localized>{'Preview status request'}</Localized></button>
      </fieldset>
    </form>
    <p className="muted"><Localized>{'Keep the same audit number and exact body for retries. Changed content needs a new audit number.'}</Localized></p>
    <p aria-live="polite"><Localized>{message}</Localized></p>
    <Localized>{review && <>
      <p><Localized>{review.target.scope}</Localized><Localized>{' · '}</Localized><Localized>{review.target.role}</Localized>
        <Localized>{' · '}</Localized><Localized>{review.target.id}</Localized><Localized>{' · '}</Localized><Localized>{review.target.principalId}</Localized></p>
      <pre><code><Localized>{JSON.stringify(review.request, null, 2)}</Localized></code></pre>
      <label><input type="checkbox" checked={review.confirmed} disabled={copying || locked}
        onChange={event => { setReview(confirmGrantStatus(review, event.target.checked)); setMessage(''); }} />
        <Localized>{'I reviewed the exact grant, recipient, status change, reason and audit number.'}</Localized>
      </label>
      <button className="btn" type="button" disabled={!review.confirmed || copying} onClick={copy}>
        <Localized>{'Copy confirmed grant request'}</Localized>
      </button>
      <Localized>{submissionEnabled && (!result || result.phase === 'idle') && <button className="btn" type="button"
        disabled={!review.confirmed || copying} onClick={send}><Localized>{'Send confirmed grant request'}</Localized></button>}</Localized>
      <Localized>{result && ['unknown', 'rejected'].includes(result.phase) && <button className="btn" type="button"
        disabled={!submissionEnabled || copying} onClick={send}><Localized>{'Retry original grant request'}</Localized></button>}</Localized>
      <Localized>{result && <GrantStatusResult state={result} />}</Localized>
      <Localized>{result && ['confirmed', 'rejected'].includes(result.phase) && <button className="btn" type="button"
        disabled={copying} onClick={newRequest}><Localized>{'Prepare another operation with a new audit number'}</Localized></button>}</Localized>
    </>}</Localized>
  </section></Localized>;
}
