'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { type EvidenceError, type EvidenceState } from '../lib/evidence-command-transport';
import { type ResourceError, type ResourceState } from '../lib/resource-command-transport';

export const evidenceResourceMessages: Record<EvidenceError | ResourceError, string> = {
  evidence_submission_disabled: 'Business command submission is disabled in this environment.',
  resource_submission_disabled: 'Business command submission is disabled in this environment.',
  cross_origin_request: 'The request origin was rejected.', json_required: 'A JSON request is required.',
  request_too_large: 'The request exceeds the allowed size.', invalid_request: 'The business request is invalid.',
  session_required: 'Sign in again before submitting or querying your original operation.',
  read_only_mode: 'This environment is read-only. The original audit may still be queried.',
  submission_forbidden: 'The API denied this operation. Review the exact scope and permission.',
  request_conflict: 'This request ID conflicts with recorded content. Keep the original request.',
  submission_conflict: 'The API reported a business conflict. Review current evidence and constraints.',
  outcome_unknown: 'No matching original audit receipt was confirmed. Absence is not proof that nothing was committed.',
};
export default function EvidenceResourceCommandResult({ state }: { state: EvidenceState | ResourceState }) {
  if (state.phase === 'idle') return null;
  const receipt = state.receipt;
  return <Localized><section aria-live="polite" aria-busy={state.phase === 'sending' || state.phase === 'checking'}>
    <h3><Localized>{'Business command result'}</Localized></h3>
    <Localized>{state.phase === 'sending' && <p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'checking' && <p><Localized>{'Querying the original audit. This does not repeat the business write.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && <p role="alert"><Localized>{'The outcome is unknown. Keep the original request ID, target and exact body.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'rejected' && <p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}</Localized>
    <Localized>{state.error && <p><Localized>{evidenceResourceMessages[state.error]}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && state.error !== 'outcome_unknown' && <p><Localized>{'The latest attempt was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}</Localized>
    <Localized>{receipt && <>
      <p><Localized>{'The original operation was confirmed by its matching atomic audit.'}</Localized></p>
      <p className="muted"><Localized>{receipt.operation === 'impact' ?
        'This confirms the original impact judgment, frozen snapshot and declared evidence reference. It does not prove test success, current impact or release permission.' :
        receipt.operation === 'acceptance' ? 'This confirms the original acceptance-criterion-to-DVP assignment. It does not prove test success or acceptance completion.' :
        'This confirms the original resource registration and reference text. It does not prove file availability, verified content or distribution rights. The location is not opened or fetched.'}</Localized></p>
      <Localized>{receipt.operation === 'impact' && <p><Link target="_blank" rel="noopener noreferrer" prefetch={false}
        href={'/snapshots/' + encodeURIComponent(String(receipt.result.snapshot_no))}><Localized>{'Open original frozen snapshot'}</Localized></Link></p>}</Localized>
      <Localized>{receipt.operation === 'acceptance' && <p><Link target="_blank" rel="noopener noreferrer" prefetch={false}
        href={'/testing/dvp/' + encodeURIComponent(String(receipt.result.dvp_item_id))}><Localized>{'Open assigned DVP item'}</Localized></Link></p>}</Localized>
      <pre><code>{JSON.stringify(receipt, null, 2)}</code></pre>
      <p className="muted"><Localized>{'These are the original applied values. Current records may have changed; no replay or current status is inferred.'}</Localized></p>
    </>}</Localized>
    <p><Link target="_blank" rel="noopener noreferrer" prefetch={false} href={state.review.draft.trace}><Localized>{'Open exact business detail'}</Localized></Link>
      <Localized>{' · '}</Localized><Link target="_blank" rel="noopener noreferrer" prefetch={false} href={state.review.draft.audit}><Localized>{'Open original audit event'}</Localized></Link></p>
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
    <p className="muted"><Localized>{'In-memory recovery is lost on reload. Export original recovery text to restore an audit-only query in a later session.'}</Localized></p>
  </section></Localized>;
}
