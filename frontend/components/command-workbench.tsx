'use client';
import Link from 'next/link';
import { useState } from 'react';
import { blankFields, confirm, exportRequest, Fields, Operation, prepare, Review } from '../lib/command-draft';

const labels: Record<Operation, string> = {
  snapshot: 'Freeze Snapshot', actual: 'Report / correct actual software', batch: 'Create Production Batch',
};
export default function CommandWorkbench({ initialOperation, initialTarget }: {
  initialOperation: Operation; initialTarget: string;
}) {
  const [operation, setOperation] = useState<Operation>(initialOperation);
  const [fields, setFields] = useState<Fields>({ ...blankFields, target: initialTarget });
  const [review, setReview] = useState<Review | null>(null);
  const [message, setMessage] = useState('');
  const [copying, setCopying] = useState(false);
  function edit(name: keyof Fields, value: string) {
    setFields(current => ({ ...current, [name]: value }));
    setReview(null); setMessage('');
  }
  function input(name: keyof Fields, label: string, required = true, maxLength?: number) {
    return <label>{label}<input name={name} value={fields[name]} required={required}
      maxLength={maxLength} onChange={event => edit(name, event.target.value)} /></label>;
  }
  async function copy() {
    if (!review || !review.confirmed || copying) return;
    setCopying(true);
    try {
      const text = exportRequest(review);
      await navigator.clipboard.writeText(text);
      setMessage('Request copied. No API write was sent. Reuse this exact body/key for a retry.');
    } catch { setMessage('Clipboard unavailable. Select and copy the reviewed request below. No API write was sent.'); }
    finally { setCopying(false); }
  }
  return <>
    <section className="panel">
      <p className="notice">Request preparation only. This page does not submit commands or authenticate an operator.
        Nothing is saved in browser storage. Keep the same request ID and content when retrying through your controlled API client.</p>
      <form className="commandform" onSubmit={event => {
        event.preventDefault();
        try { setReview(prepare(operation, fields, crypto.randomUUID())); setMessage('Review the target and request before copying.'); }
        catch (error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
      }}>
        <fieldset disabled={copying} className="commandfields">
        <label>Command<select value={operation} onChange={event => {
          setOperation(event.target.value as Operation); setFields({ ...blankFields }); setReview(null); setMessage('');
        }}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        {input('target', operation === 'snapshot' ? 'Release UUID' : 'Deployment number', true, operation === 'snapshot' ? 36 : 50)}
        {operation === 'actual' && <>
          {input('release', 'Actual release UUID', true, 36)}{input('snapshot', 'Actual snapshot UUID', true, 36)}
          {input('version', 'Expected version — read actual_version from deployment detail')}
          <label>Report / correction reason<textarea required maxLength={2000} value={fields.reason}
            onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted">A reason is required here for every report, including version-zero legacy records.
            A stale version returns a conflict. This corrects a recorded fact; it does not reverse flashing or batch history.</p>
        </>}
        {operation === 'batch' && <>
          {input('batch', 'Batch number', true, 80)}{input('changeover', 'Optional changeover UUID', false, 36)}
          <label>Optional note<textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
          <p className="muted">Available capacity and MATCH status are informational. The API rechecks authorization, software and quota in its transaction.</p>
        </>}
        {operation !== 'snapshot' && <>
          {input('timestamp', 'Optional time — e.g. 2026-10-01T08:00:00Z', false, 35)}
          <p className="muted">Use an explicit timezone. An omitted time stays null in the request; the API generates it once on success.</p>
        </>}
        <button type="submit" disabled={Boolean(review) || copying}>Prepare request</button>
        </fieldset>
      </form>
      <p role="status" aria-live="polite">{message}</p>
    </section>
    {review && <section className="panel">
      <h2>Review {labels[review.draft.operation]}</h2>
      <p>POST <code>{review.draft.path}</code></p>
      <p>Request ID: <code>{review.draft.payload.request_id}</code></p>
      <p className="muted">Editing any field discards this review. Preparing a new command generates a new key;
        preserve the exported request until an uncertain API result has been resolved.</p>
      <label className="commandconfirm"><input type="checkbox" disabled={copying} checked={review.confirmed}
        onChange={event => { setReview(confirm(review, event.target.checked)); setMessage(''); }} />
        I have reviewed the exact target, software identifiers and request content.</label>
      <button type="button" disabled={!review.confirmed || copying} onClick={copy}>{copying ? 'Copying…' : 'Copy confirmed request'}</button>
      <pre className="auditpayload">{review.confirmed ? exportRequest(review) : JSON.stringify(review.draft.payload, null, 2)}</pre>
      <p><Link href={review.draft.trace}>Review business record / history →</Link> · <Link href={review.draft.audit}>Expected audit event after execution →</Link></p>
      <button type="button" disabled={copying} onClick={() => { setReview(null); setMessage("Start a new command only after resolving any earlier API result. This will generate a new request ID."); }}>Start a new request</button>
      <p className="muted">These links show existing records. A prepared or copied request is not a successful business write.
        After execution, use the API result identifiers to verify the exact new record and audit event.</p>
    </section>}
  </>;
}
