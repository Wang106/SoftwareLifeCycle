'use client';
import { useState } from 'react';
import { Localized } from './localized';
import { prepareGrantStatus, confirmGrantStatus, exportGrantStatus, type GrantTarget, type GrantReview } from '../lib/grant-status-draft';

export default function GrantStatusPreparation({ target }: { target: GrantTarget }) {
  const [eventNo, setEventNo] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<GrantReview | null>(null);
  const [message, setMessage] = useState('');
  const [copying, setCopying] = useState(false);
  function edit(change: () => void) { change(); setReview(null); setMessage(''); }
  async function copy() {
    if (!review?.confirmed || copying) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(exportGrantStatus(review));
      setMessage('Grant request copied. No permission change was sent.');
    } catch { setMessage('Clipboard unavailable. Select and copy the confirmed request below.'); }
    finally { setCopying(false); }
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare grant status change'}</Localized></h2>
    <p className="notice"><Localized>{'Preparation only. This form does not change permissions or send an API request.'}</Localized></p>
    <p><Localized>{'Expected status'}</Localized><Localized>{': '}</Localized><Localized>{target.status}</Localized>
      <Localized>{' · '}</Localized><Localized>{'Requested status'}</Localized><Localized>{': '}</Localized>
      <Localized>{target.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE'}</Localized></p>
    <Localized>{target.scope === 'GLOBAL' && target.role === 'PLATFORM_ADMIN' && <p className="muted">
      <Localized>{'The API protects the last active administrator. This preview does not prove that a suspension will be allowed.'}</Localized>
    </p>}</Localized>
    <Localized>{target.status !== target.historyStatus && <p role="alert">
      <Localized>{'Refresh the grant before preparing a status change.'}</Localized>
    </p>}</Localized>
    <form className="commandform" onSubmit={event => {
      event.preventDefault();
      try { setReview(prepareGrantStatus(target, eventNo, reason)); setMessage('Review the exact grant, reason and audit number.'); }
      catch (error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
    }}>
      <fieldset disabled={copying} className="commandfields">
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
      <label><input type="checkbox" checked={review.confirmed} disabled={copying}
        onChange={event => { setReview(confirmGrantStatus(review, event.target.checked)); setMessage(''); }} />
        <Localized>{'I reviewed the exact grant, recipient, status change, reason and audit number.'}</Localized>
      </label>
      <button className="btn" type="button" disabled={!review.confirmed || copying} onClick={copy}>
        <Localized>{'Copy confirmed grant request'}</Localized>
      </button>
    </>}</Localized>
  </section></Localized>;
}
