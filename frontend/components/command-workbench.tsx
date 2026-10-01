'use client';
import Link from 'next/link';
import { useState } from 'react';
import { blankFields, confirm, exportRequest, Fields, Operation, prepare, Review, resourceTypes, locationKinds } from '../lib/command-draft';

const labels: Record<Operation, string> = {
  snapshot: 'Freeze Snapshot', actual: 'Report / correct actual software', batch: 'Create Production Batch',
  approval: 'Record Approval Action', decision: 'Record Release Decision',
  'test-release': 'Create Test Release Draft', deployment: 'Create Deployment Expectation', changeover: 'Record Software Changeover',
  delivery: 'Create Delivery Package', distribution: 'Record Distribution', authorization: 'Create Production Authorization',
  impact: 'Record Impact Assessment', acceptance: 'Link Acceptance to DVP', resource: 'Register Resource Reference',
};
export default function CommandWorkbench({ initialOperation, initialTarget, initialStep, initialContext }: {
  initialOperation: Operation; initialTarget: string; initialStep: string; initialContext: Partial<Fields>;
}) {
  const [operation, setOperation] = useState<Operation>(initialOperation);
  const [fields, setFields] = useState<Fields>({ ...blankFields, ...initialContext, target: initialTarget, step: initialStep });
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
        {input('target', operation === 'deployment' ? 'Authorization UUID' : operation === 'test-release' || operation === 'delivery' ? 'Release UUID' : operation === 'distribution' ? 'Delivery package UUID — exact revision' : operation === 'authorization' ? 'Distribution UUID' : operation === 'resource' ? 'Resource object UUID' : operation === 'impact' ? 'Issue number' : operation === 'acceptance' ? 'SCR number' : operation === 'snapshot' ? 'Release UUID' : operation === 'approval' || operation === 'decision' ? 'Approval number' : 'Deployment number', true, ['snapshot','resource','delivery','distribution','authorization','test-release','deployment'].includes(operation) ? 36 : 50)}
        {operation === 'test-release' && <>
          {input('testReleaseNo', 'Test release number', true, 50)}{input('snapshot', 'Frozen snapshot UUID', true, 36)}
          <label>Test purpose<select required value={fields.purposeScope} onChange={event => edit('purposeScope', event.target.value)}>
            <option value="">Select a test purpose</option>{['SOFTWARE_TEST','BATTERY_TEST','CUSTOMER_TEST'].map(value => <option key={value}>{value}</option>)}
          </select></label>
          {input('actor', 'Declared operator — retained text, not authenticated identity', true, 120)}
          <label>Reason<textarea required maxLength={4000} value={fields.reason} onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted">The API requires this release's exact FROZEN snapshot and creates DRAFT. Test purpose does not activate a record, grant distribution rights or authorize production.</p>
        </>}
        {operation === 'deployment' && <>
          {input('deploymentNo', 'New deployment number', true, 50)}{input('productionLine', 'Production line UUID', true, 36)}
          <p className="muted">The API checks an APPROVED authorization and exact active customer/project/site/line scope. Expected release and snapshot come from that authorization. Creation is PENDING and does not report actual software or perform flashing.</p>
        </>}
        {operation === 'changeover' && <>
          {input('changeoverNo', 'Changeover number', true, 50)}{input('fromRelease', 'Source release UUID — explicitly reviewed previous version', true, 36)}
          <label>Optional changeover note<textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
          <p className="muted">The target is the deployment's expected release; source must exist and differ. No previous version is inferred from the current actual report. The API records COMPLETED history but this does not prove physical flashing or update actual software. General reversal/revocation is pending.</p>
        </>}
        {(operation === 'delivery' || operation === 'distribution' || operation === 'authorization') && <>
          {operation === 'delivery' && <>
            {input('packageNo', 'Package number', true, 50)}{input('revision', 'Package revision — explicit positive integer', true, 10)}
            {input('actor', 'Optional declared creator — text, not authenticated identity', false, 120)}
            <label>Snapshot artifact UUIDs — one per line<textarea required maxLength={8000} value={fields.artifacts} onChange={event => edit('artifacts', event.target.value)} /></label>
            <p className="muted">Choose exact frozen artifact UUIDs from the approved decision snapshot. The API selects the latest RELEASE decision and checks approval, file membership, INTERNAL_ONLY and recipient/purpose rules. This form cannot pin a decision or certify eligibility.</p>
          </>}
          {operation === 'distribution' && <>
            {input('distributionNo', 'Distribution number', true, 50)}
            <p className="muted">The package UUID identifies one exact revision. Recipient values must exactly match that package. Creating a record does not send files or acknowledge receipt.</p>
          </>}
          {(operation === 'delivery' || operation === 'distribution') && <>
            {input('recipientType', 'Recipient type — exact API policy value', true, 50)}
            {input('recipientCode', 'Recipient code — exact stored value', true, 80)}
          </>}
          {operation === 'authorization' && <>
            {input('authorizationNo', 'Authorization number', true, 50)}
            {input('release', 'Application release UUID', true, 36)}{input('customer', 'Customer UUID', true, 36)}{input('project', 'Project UUID', true, 36)}
            {input('site', 'Site code — exact value', true, 80)}{input('line', 'Line code — exact value', true, 80)}
            <label>Batch scope<select required value={fields.limitMode} onChange={event => edit('limitMode', event.target.value)}>
              <option value="">Select finite or unlimited scope</option><option value="FINITE">FINITE</option><option value="UNLIMITED">UNLIMITED</option>
            </select></label>
            {input('limit', 'Finite batch limit — clear for unlimited scope', fields.limitMode === 'FINITE', 10)}
            <label>Optional restriction note<textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
            <p className="muted">Review the full customer distribution, application release, snapshot, project, site/line and purpose chain. New authorizations are DRAFT; creation does not approve deployment or production. Unlimited scope is explicit, never a missing finite limit.</p>
          </>}
          {(operation === 'delivery' || operation === 'authorization') && input('purpose', 'Purpose — exact policy value', true, 50)}
          <p className="muted">The API checks current exact scope and binds the authenticated actor separately. These declarations and copied requests grant no permission.</p>
        </>}
        {(operation === 'impact' || operation === 'acceptance' || operation === 'resource') && <>
          {input('actor', 'Declared operator — retained text, not authenticated identity', true, 120)}
          <label>Reason<textarea required maxLength={4000} value={fields.reason} onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted">The API authenticates separately and checks exact scope. Preparation does not verify object membership, evidence or permission.</p>
          {operation === 'impact' && <>
            {input('release', 'Release UUID', true, 36)}{input('snapshot', 'Frozen snapshot UUID', true, 36)}
            <label>Impact judgment<select required value={fields.decision} onChange={event => edit('decision', event.target.value)}>
              <option value="">Select a judgment</option>{['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'].map(value => <option key={value}>{value}</option>)}
            </select></label>
            {input('evidence', 'Optional evidence reference — text only', false, 2000)}
            <p className="muted">A shared version or test PASS does not establish impact. Review the exact frozen snapshot; this appends a judgment and does not supersede an earlier record.</p>
          </>}
          {operation === 'acceptance' && <>
            {input('criterion', 'Acceptance criterion UUID', true, 36)}{input('dvp', 'DVP item UUID', true, 36)}
            <p className="muted">Both objects must belong to this exact SCR. Assignment does not prove test execution or release readiness.</p>
            {fields.target.trim() && <Link href={`/changes/${encodeURIComponent(fields.target.trim())}/coverage`}>Review exact SCR coverage →</Link>}
          </>}
          {operation === 'resource' && <>
            <label>Resource object type<select required value={fields.entityType} onChange={event => edit('entityType', event.target.value)}>
              <option value="">Select an object type</option>{resourceTypes.map(value => <option key={value}>{value}</option>)}
            </select></label>
            {input('title', 'Resource title', true, 240)}
            <label>Location kind<select required value={fields.locationKind} onChange={event => edit('locationKind', event.target.value)}>
              <option value="">Select a location kind</option>{locationKinds.map(value => <option key={value}>{value}</option>)}
            </select></label>
            {input('location', 'Resource location — text only, never opened or fetched', true, 4000)}
            <label>Optional description<textarea maxLength={4000} value={fields.description} onChange={event => edit('description', event.target.value)} /></label>
            <p className="muted">HTTP(S) references exclude embedded credentials and encoded controls. Paths must be absolute local paths or server/share paths. These are references, not uploaded files, verified availability or distribution rights. Supplier/customer registration requires PLATFORM_ADMIN in OIDC mode.</p>
          </>}
        </>}
        {(operation === 'approval' || operation === 'decision') && <>
          {input('actor', 'Declared operator — retained request text, not authenticated identity', true, 120)}
          <p className="muted">The controlled API client must authenticate separately. In OIDC mode the API binds the actual actor to its trusted principal; this declaration never grants a role.</p>
          {operation === 'approval' ? <>
            {input('step', 'Expected approval step UUID — read from exact approval detail', true, 36)}
            <label>Approval action<select required value={fields.action} onChange={event => edit('action', event.target.value)}>
              <option value="">Select an action</option><option value="APPROVED">APPROVED</option>
              <option value="RETURNED">RETURNED</option><option value="REJECTED">REJECTED</option>
            </select></label>
            <p className="muted">Review the original release, frozen snapshot and exact step. A stale or wrong step conflicts; this form cannot establish that it is currently active.</p>
          </> : <>
            {input('decisionNo', 'Decision number', true, 50)}
            {input('readiness', 'Recorded readiness status — declaration, not a calculated check', true, 30)}
            {input('decision', 'Decision — exact API value, e.g. RELEASE or HOLD', true, 30)}
            <p className="muted">Review the approved request and its original snapshot evidence. The API records these exact declarations; preparing this form does not verify readiness or permit distribution.</p>
          </>}
          <label>Optional {operation === 'approval' ? 'comment' : 'decision notes'}<textarea value={fields.note}
            onChange={event => edit('note', event.target.value)} /></label>
          {fields.target.trim() && <Link href={`/approvals/${encodeURIComponent(fields.target.trim())}`}>Review exact approval evidence →</Link>}
        </>}
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
        {(operation === 'actual' || operation === 'batch' || operation === 'changeover') && <>
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
        I have reviewed the exact target, evidence, declarations and request content.</label>
      <button type="button" disabled={!review.confirmed || copying} onClick={copy}>{copying ? 'Copying…' : 'Copy confirmed request'}</button>
      <pre className="auditpayload">{review.confirmed ? exportRequest(review) : JSON.stringify(review.draft.payload, null, 2)}</pre>
      <p><Link href={review.draft.trace}>Review business record / history →</Link> · <Link href={review.draft.audit}>Expected audit event after execution →</Link></p>
      <button type="button" disabled={copying} onClick={() => { setReview(null); setMessage("Start a new command only after resolving any earlier API result. This will generate a new request ID."); }}>Start a new request</button>
      <p className="muted">These links show existing records. A prepared or copied request is not a successful business write.
        After execution, use the API result identifiers to verify the exact new record and audit event.</p>
    </section>}
  </>;
}
