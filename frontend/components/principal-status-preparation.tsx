'use client';
import { useEffect, useRef, useState } from 'react';
import { Localized } from './localized';
import { preparePrincipalStatus, confirmPrincipalStatus, exportPrincipalStatus, principalPreparationError,
  samePrincipalTarget, type PrincipalTarget, type PrincipalReview } from '../lib/principal-status-draft';

export default function PrincipalStatusPreparation({ target }: { target: PrincipalTarget }) {
  const [eventNo, setEventNo] = useState('');
  const [reason, setReason] = useState('');
  const [review, setReview] = useState<PrincipalReview | null>(null);
  const [message, setMessage] = useState('');
  const [copying, setCopying] = useState(false);
  const targetKey = JSON.stringify([target.id.toLowerCase(), target.principalType, target.status,
    target.historyStatus, target.protectedAdministrator, target.issuerMatchesConfiguration]);
  const currentKey = useRef(targetKey);
  currentKey.current = targetKey;
  const previousKey = useRef(targetKey);
  const error = principalPreparationError(target);
  const currentReview = review && !error && samePrincipalTarget(review.target, target) ? review : null;
  useEffect(() => {
    if (previousKey.current !== targetKey) {
      previousKey.current = targetKey; setReview(null); setMessage('');
    }
  }, [targetKey]);
  function edit(change: () => void) {
    if (copying) return;
    change(); setReview(null); setMessage('');
  }
  async function copy() {
    if (!currentReview?.confirmed || copying) return;
    const key = targetKey;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(exportPrincipalStatus(currentReview));
      if (currentKey.current === key) setMessage('Identity request copied. No identity change was sent.');
    } catch {
      if (currentKey.current === key) setMessage('Clipboard unavailable. Select and copy the confirmed request below.');
    } finally { setCopying(false); }
  }
  return <Localized><section className="panel">
    <h2><Localized>{'Prepare identity status change'}</Localized></h2>
    <p className="notice"><Localized>{'Preparation only. This form does not change identities or send an API request.'}</Localized></p>
    <p className="muted"><Localized>{'Disabling revokes existing browser sessions. Enabling does not restore old sessions, grant roles or create a provider account.'}</Localized></p>
    <p className="muted"><Localized>{'The API must independently verify administrator permission, protection and expected status. This preview is not authorization.'}</Localized></p>
    <Localized>{!target.issuerMatchesConfiguration && <p className="muted"><Localized>{'Issuer mismatch is informational; changing local status does not repair provider configuration.'}</Localized></p>}</Localized>
    <Localized>{error ? <p role="alert"><Localized>{error}</Localized></p> : <>
      <p><Localized>{target.id.toLowerCase()}</Localized><Localized>{' · '}</Localized><Localized>{target.principalType}</Localized></p>
      <p><Localized>{'Expected status'}</Localized><Localized>{': '}</Localized><Localized>{target.status}</Localized>
        <Localized>{' · '}</Localized><Localized>{'Requested status'}</Localized><Localized>{': '}</Localized>
        <Localized>{target.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'}</Localized></p>
      <form className="commandform" onSubmit={event => {
        event.preventDefault(); if (copying) return;
        try { setReview(preparePrincipalStatus(target, eventNo, reason)); setMessage('Review the exact identity, status change, reason and audit number.'); }
        catch (caught) { setReview(null); setMessage(caught instanceof Error ? caught.message : 'Unable to prepare request.'); }
      }}>
        <fieldset disabled={copying} className="commandfields">
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
        <label><input type="checkbox" checked={currentReview.confirmed} disabled={copying}
          onChange={event => { if (!copying) { setReview(confirmPrincipalStatus(currentReview, event.target.checked)); setMessage(''); } }} />
          <Localized>{'I reviewed the exact identity, status change, session consequences, reason and audit number.'}</Localized></label>
        <button className="btn" type="button" disabled={!currentReview.confirmed || copying} onClick={copy}>
          <Localized>{'Copy confirmed identity request'}</Localized></button>
      </>}</Localized>
    </>}</Localized>
  </section></Localized>;
}
