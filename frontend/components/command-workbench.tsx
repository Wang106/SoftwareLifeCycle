'use client';
import { Localized, LocalizedAttributes } from "./localized";

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
    return <label><Localized>{label}</Localized><input name={name} value={fields[name]} required={required}
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
      <p className="notice"><Localized>{"Request preparation only. This page does not submit commands or authenticate an operator. Business requests and credentials are not saved in browser storage; only the language preference is remembered. Keep the same request ID and content when retrying through your controlled API client."}</Localized></p>
      <form className="commandform" onSubmit={event => {
        event.preventDefault();
        try { setReview(prepare(operation, fields, crypto.randomUUID())); setMessage('Review the target and request before copying.'); }
        catch (error) { setReview(null); setMessage(error instanceof Error ? error.message : 'Unable to prepare request.'); }
      }}>
        <fieldset disabled={copying} className="commandfields">
        <label><Localized>{"Command"}</Localized><select value={operation} onChange={event => {
          setOperation(event.target.value as Operation); setFields({ ...blankFields }); setReview(null); setMessage('');
        }}><Localized>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}><Localized>{label}</Localized></option>)}</Localized></select></label>
        <Localized>{input('target', operation === 'deployment' ? 'Authorization UUID' : operation === 'test-release' || operation === 'delivery' ? 'Release UUID' : operation === 'distribution' ? 'Delivery package UUID — exact revision' : operation === 'authorization' ? 'Distribution UUID' : operation === 'resource' ? 'Resource object UUID' : operation === 'impact' ? 'Issue number' : operation === 'acceptance' ? 'SCR number' : operation === 'snapshot' ? 'Release UUID' : operation === 'approval' || operation === 'decision' ? 'Approval number' : 'Deployment number', true, ['snapshot','resource','delivery','distribution','authorization','test-release','deployment'].includes(operation) ? 36 : 50)}</Localized>
        <Localized>{operation === 'test-release' && <>
          <Localized>{input('testReleaseNo', 'Test release number', true, 50)}</Localized><Localized>{input('snapshot', 'Frozen snapshot UUID', true, 36)}</Localized>
          <label><Localized>{"Test purpose"}</Localized><select required value={fields.purposeScope} onChange={event => edit('purposeScope', event.target.value)}>
            <option value=""><Localized>{"Select a test purpose"}</Localized></option><Localized>{['SOFTWARE_TEST','BATTERY_TEST','CUSTOMER_TEST'].map(value => <option value={value} key={value}><Localized>{value}</Localized></option>)}</Localized>
          </select></label>
          <Localized>{input('actor', 'Declared operator — retained text, not authenticated identity', true, 120)}</Localized>
          <label><Localized>{"Reason"}</Localized><textarea required maxLength={4000} value={fields.reason} onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted"><Localized>{"The API requires this release's exact FROZEN snapshot and creates DRAFT. Test purpose does not activate a record, grant distribution rights or authorize production."}</Localized></p>
        </>}</Localized>
        <Localized>{operation === 'deployment' && <>
          <Localized>{input('deploymentNo', 'New deployment number', true, 50)}</Localized><Localized>{input('productionLine', 'Production line UUID', true, 36)}</Localized>
          <p className="muted"><Localized>{"The API checks an APPROVED authorization and exact active customer/project/site/line scope. Expected release and snapshot come from that authorization. Creation is PENDING and does not report actual software or perform flashing."}</Localized></p>
        </>}</Localized>
        <Localized>{operation === 'changeover' && <>
          <Localized>{input('changeoverNo', 'Changeover number', true, 50)}</Localized><Localized>{input('fromRelease', 'Source release UUID — explicitly reviewed previous version', true, 36)}</Localized>
          <label><Localized>{"Optional changeover note"}</Localized><textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
          <p className="muted"><Localized>{"The target is the deployment's expected release; source must exist and differ. No previous version is inferred from the current actual report. The API records COMPLETED history but this does not prove physical flashing or update actual software. General reversal/revocation is pending."}</Localized></p>
        </>}</Localized>
        <Localized>{(operation === 'delivery' || operation === 'distribution' || operation === 'authorization') && <>
          <Localized>{operation === 'delivery' && <>
            <Localized>{input('packageNo', 'Package number', true, 50)}</Localized><Localized>{input('revision', 'Package revision — explicit positive integer', true, 10)}</Localized>
            <Localized>{input('actor', 'Optional declared creator — text, not authenticated identity', false, 120)}</Localized>
            <label><Localized>{"Snapshot artifact UUIDs — one per line"}</Localized><textarea required maxLength={8000} value={fields.artifacts} onChange={event => edit('artifacts', event.target.value)} /></label>
            <p className="muted"><Localized>{"Choose exact frozen artifact UUIDs from the approved decision snapshot. The API selects the latest RELEASE decision and checks approval, file membership, INTERNAL_ONLY and recipient/purpose rules. This form cannot pin a decision or certify eligibility."}</Localized></p>
          </>}</Localized>
          <Localized>{operation === 'distribution' && <>
            <Localized>{input('distributionNo', 'Distribution number', true, 50)}</Localized>
            <p className="muted"><Localized>{"The package UUID identifies one exact revision. Recipient values must exactly match that package. Creating a record does not send files or acknowledge receipt."}</Localized></p>
          </>}</Localized>
          <Localized>{(operation === 'delivery' || operation === 'distribution') && <>
            <Localized>{input('recipientType', 'Recipient type — exact API policy value', true, 50)}</Localized>
            <Localized>{input('recipientCode', 'Recipient code — exact stored value', true, 80)}</Localized>
          </>}</Localized>
          <Localized>{operation === 'authorization' && <>
            <Localized>{input('authorizationNo', 'Authorization number', true, 50)}</Localized>
            <Localized>{input('release', 'Application release UUID', true, 36)}</Localized><Localized>{input('customer', 'Customer UUID', true, 36)}</Localized><Localized>{input('project', 'Project UUID', true, 36)}</Localized>
            <Localized>{input('site', 'Site code — exact value', true, 80)}</Localized><Localized>{input('line', 'Line code — exact value', true, 80)}</Localized>
            <label><Localized>{"Batch scope"}</Localized><select required value={fields.limitMode} onChange={event => edit('limitMode', event.target.value)}>
              <option value=""><Localized>{"Select finite or unlimited scope"}</Localized></option><option value="FINITE"><Localized>{"FINITE"}</Localized></option><option value="UNLIMITED"><Localized>{"UNLIMITED"}</Localized></option>
            </select></label>
            <Localized>{input('limit', 'Finite batch limit — clear for unlimited scope', fields.limitMode === 'FINITE', 10)}</Localized>
            <label><Localized>{"Optional restriction note"}</Localized><textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
            <p className="muted"><Localized>{"Review the full customer distribution, application release, snapshot, project, site/line and purpose chain. New authorizations are DRAFT; creation does not approve deployment or production. Unlimited scope is explicit, never a missing finite limit."}</Localized></p>
          </>}</Localized>
          <Localized>{(operation === 'delivery' || operation === 'authorization') && input('purpose', 'Purpose — exact policy value', true, 50)}</Localized>
          <p className="muted"><Localized>{"The API checks current exact scope and binds the authenticated actor separately. These declarations and copied requests grant no permission."}</Localized></p>
        </>}</Localized>
        <Localized>{(operation === 'impact' || operation === 'acceptance' || operation === 'resource') && <>
          <Localized>{input('actor', 'Declared operator — retained text, not authenticated identity', true, 120)}</Localized>
          <label><Localized>{"Reason"}</Localized><textarea required maxLength={4000} value={fields.reason} onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted"><Localized>{"The API authenticates separately and checks exact scope. Preparation does not verify object membership, evidence or permission."}</Localized></p>
          <Localized>{operation === 'impact' && <>
            <Localized>{input('release', 'Release UUID', true, 36)}</Localized><Localized>{input('snapshot', 'Frozen snapshot UUID', true, 36)}</Localized>
            <label><Localized>{"Impact judgment"}</Localized><select required value={fields.decision} onChange={event => edit('decision', event.target.value)}>
              <option value=""><Localized>{"Select a judgment"}</Localized></option><Localized>{['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'].map(value => <option value={value} key={value}><Localized>{value}</Localized></option>)}</Localized>
            </select></label>
            <Localized>{input('evidence', 'Optional evidence reference — text only', false, 2000)}</Localized>
            <p className="muted"><Localized>{"A shared version or test PASS does not establish impact. Review the exact frozen snapshot; this appends a judgment and does not supersede an earlier record."}</Localized></p>
          </>}</Localized>
          <Localized>{operation === 'acceptance' && <>
            <Localized>{input('criterion', 'Acceptance criterion UUID', true, 36)}</Localized><Localized>{input('dvp', 'DVP item UUID', true, 36)}</Localized>
            <p className="muted"><Localized>{"Both objects must belong to this exact SCR. Assignment does not prove test execution or release readiness."}</Localized></p>
            <Localized>{fields.target.trim() && <Link href={`/changes/${encodeURIComponent(fields.target.trim())}/coverage`}><Localized>{"Review exact SCR coverage →"}</Localized></Link>}</Localized>
          </>}</Localized>
          <Localized>{operation === 'resource' && <>
            <label><Localized>{"Resource object type"}</Localized><select required value={fields.entityType} onChange={event => edit('entityType', event.target.value)}>
              <option value=""><Localized>{"Select an object type"}</Localized></option><Localized>{resourceTypes.map(value => <option value={value} key={value}><Localized>{value}</Localized></option>)}</Localized>
            </select></label>
            <Localized>{input('title', 'Resource title', true, 240)}</Localized>
            <label><Localized>{"Location kind"}</Localized><select required value={fields.locationKind} onChange={event => edit('locationKind', event.target.value)}>
              <option value=""><Localized>{"Select a location kind"}</Localized></option><Localized>{locationKinds.map(value => <option value={value} key={value}><Localized>{value}</Localized></option>)}</Localized>
            </select></label>
            <Localized>{input('location', 'Resource location — text only, never opened or fetched', true, 4000)}</Localized>
            <label><Localized>{"Optional description"}</Localized><textarea maxLength={4000} value={fields.description} onChange={event => edit('description', event.target.value)} /></label>
            <p className="muted"><Localized>{"HTTP(S) references exclude embedded credentials and encoded controls. Paths must be absolute local paths or server/share paths. These are references, not uploaded files, verified availability or distribution rights. Supplier/customer registration requires PLATFORM_ADMIN in OIDC mode."}</Localized></p>
          </>}</Localized>
        </>}</Localized>
        <Localized>{(operation === 'approval' || operation === 'decision') && <>
          <Localized>{input('actor', 'Declared operator — retained request text, not authenticated identity', true, 120)}</Localized>
          <p className="muted"><Localized>{"The controlled API client must authenticate separately. In OIDC mode the API binds the actual actor to its trusted principal; this declaration never grants a role."}</Localized></p>
          <Localized>{operation === 'approval' ? <>
            <Localized>{input('step', 'Expected approval step UUID — read from exact approval detail', true, 36)}</Localized>
            <label><Localized>{"Approval action"}</Localized><select required value={fields.action} onChange={event => edit('action', event.target.value)}>
              <option value=""><Localized>{"Select an action"}</Localized></option><option value="APPROVED"><Localized>{"APPROVED"}</Localized></option>
              <option value="RETURNED"><Localized>{"RETURNED"}</Localized></option><option value="REJECTED"><Localized>{"REJECTED"}</Localized></option>
            </select></label>
            <p className="muted"><Localized>{"Review the original release, frozen snapshot and exact step. A stale or wrong step conflicts; this form cannot establish that it is currently active."}</Localized></p>
          </> : <>
            <Localized>{input('decisionNo', 'Decision number', true, 50)}</Localized>
            <Localized>{input('readiness', 'Recorded readiness status — declaration, not a calculated check', true, 30)}</Localized>
            <Localized>{input('decision', 'Decision — exact API value, e.g. RELEASE or HOLD', true, 30)}</Localized>
            <p className="muted"><Localized>{"Review the approved request and its original snapshot evidence. The API records these exact declarations; preparing this form does not verify readiness or permit distribution."}</Localized></p>
          </>}</Localized>
          <label><Localized>{"Optional "}</Localized><Localized>{operation === 'approval' ? 'comment' : 'decision notes'}</Localized><textarea value={fields.note}
            onChange={event => edit('note', event.target.value)} /></label>
          <Localized>{fields.target.trim() && <Link href={`/approvals/${encodeURIComponent(fields.target.trim())}`}><Localized>{"Review exact approval evidence →"}</Localized></Link>}</Localized>
        </>}</Localized>
        <Localized>{operation === 'actual' && <>
          <Localized>{input('release', 'Actual release UUID', true, 36)}</Localized><Localized>{input('snapshot', 'Actual snapshot UUID', true, 36)}</Localized>
          <Localized>{input('version', 'Expected version — read actual_version from deployment detail')}</Localized>
          <label><Localized>{"Report / correction reason"}</Localized><textarea required maxLength={2000} value={fields.reason}
            onChange={event => edit('reason', event.target.value)} /></label>
          <p className="muted"><Localized>{"A reason is required here for every report, including version-zero legacy records. A stale version returns a conflict. This corrects a recorded fact; it does not reverse flashing or batch history."}</Localized></p>
        </>}</Localized>
        <Localized>{operation === 'batch' && <>
          <Localized>{input('batch', 'Batch number', true, 80)}</Localized><Localized>{input('changeover', 'Optional changeover UUID', false, 36)}</Localized>
          <label><Localized>{"Optional note"}</Localized><textarea value={fields.note} onChange={event => edit('note', event.target.value)} /></label>
          <p className="muted"><Localized>{"Available capacity and MATCH status are informational. The API rechecks authorization, software and quota in its transaction."}</Localized></p>
        </>}</Localized>
        <Localized>{(operation === 'actual' || operation === 'batch' || operation === 'changeover') && <>
          <Localized>{input('timestamp', 'Optional time — e.g. 2026-10-01T08:00:00Z', false, 35)}</Localized>
          <p className="muted"><Localized>{"Use an explicit timezone. An omitted time stays null in the request; the API generates it once on success."}</Localized></p>
        </>}</Localized>
        <button type="submit" disabled={Boolean(review) || copying}><Localized>{"Prepare request"}</Localized></button>
        </fieldset>
      </form>
      <p role="status" aria-live="polite"><Localized>{message}</Localized></p>
    </section>
    <Localized>{review && <section className="panel">
      <h2><Localized>{"Review "}</Localized><Localized>{labels[review.draft.operation]}</Localized></h2>
      <p><Localized>{"POST "}</Localized><code>{review.draft.path}</code></p>
      <p><Localized>{"Request ID: "}</Localized><code>{review.draft.payload.request_id}</code></p>
      <p className="muted"><Localized>{"Editing any field discards this review. Preparing a new command generates a new key; preserve the exported request until an uncertain API result has been resolved."}</Localized></p>
      <label className="commandconfirm"><input type="checkbox" disabled={copying} checked={review.confirmed}
        onChange={event => { setReview(confirm(review, event.target.checked)); setMessage(''); }} /><Localized>{" I have reviewed the exact target, evidence, declarations and request content."}</Localized></label>
      <button type="button" disabled={!review.confirmed || copying} onClick={copy}><Localized>{copying ? 'Copying…' : 'Copy confirmed request'}</Localized></button>
      <pre className="auditpayload">{review.confirmed ? exportRequest(review) : JSON.stringify(review.draft.payload, null, 2)}</pre>
      <p><Link href={review.draft.trace}><Localized>{"Review business record / history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={review.draft.audit}><Localized>{"Expected audit event after execution →"}</Localized></Link></p>
      <button type="button" disabled={copying} onClick={() => { setReview(null); setMessage("Start a new command only after resolving any earlier API result. This will generate a new request ID."); }}><Localized>{"Start a new request"}</Localized></button>
      <p className="muted"><Localized>{"These links show existing records. A prepared or copied request is not a successful business write. After execution, use the API result identifiers to verify the exact new record and audit event."}</Localized></p>
    </section>}</Localized>
  </>;
}
