'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { type GovernanceError, type GovernanceState } from '../lib/governance-command-transport';

export const governanceCommandMessages: Record<GovernanceError, string> = {
  governance_submission_disabled: 'Business command submission is disabled in this environment.',
  cross_origin_request: 'The request origin was rejected.', json_required: 'A JSON request is required.',
  request_too_large: 'The request exceeds the allowed size.', invalid_request: 'The business request is invalid.',
  session_required: 'Sign in again before submitting or querying your original operation.',
  read_only_mode: 'This environment is read-only. The original audit may still be queried.',
  submission_forbidden: 'The API denied this operation. Review the exact scope and permission.',
  request_conflict: 'This request ID conflicts with recorded content. Keep the original request.',
  step_conflict: 'The expected approval step is stale. Review the exact approval detail.',
  submission_conflict: 'The API reported a business conflict. Review current evidence and constraints.',
  outcome_unknown: 'No matching original audit receipt was confirmed. Absence is not proof that nothing was committed.',
};
export default function GovernanceCommandResult({ state }: { state: GovernanceState }) {
  if (state.phase === 'idle') return null;
  const receipt = state.receipt;
  const detail = receipt?.operation === 'decision' ? '/release-decisions/' + encodeURIComponent(String(receipt.result.decision_no)) : state.review.draft.trace;
  return <Localized><section aria-live="polite" aria-busy={state.phase === 'sending' || state.phase === 'checking'}>
    <h3><Localized>{'Business command result'}</Localized></h3>
    <Localized>{state.phase === 'sending' && <p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'checking' && <p><Localized>{'Querying the original audit. This does not repeat the business write.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && <p role="alert"><Localized>{'The outcome is unknown. Keep the original request ID, target and exact body.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'rejected' && <p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}</Localized>
    <Localized>{state.error && <p><Localized>{governanceCommandMessages[state.error]}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && state.error !== 'outcome_unknown' && <p><Localized>{'The latest attempt was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}</Localized>
    <Localized>{receipt && <>
      <p><Localized>{'The original operation was confirmed by its matching atomic audit.'}</Localized></p>
      <p className="muted"><Localized>{receipt.operation === 'approval' ?
        'An approved step may leave the original approval pending. This receipt does not approve another step or authorize release.' :
        'Decision and readiness are recorded declarations. This receipt does not calculate readiness or authorize distribution.'}</Localized></p>
      <Localized>{receipt.operation === 'decision' && <p><Link target="_blank" rel="noopener noreferrer" prefetch={false}
        href={'/snapshots/' + encodeURIComponent(String(receipt.result.snapshot_no))}><Localized>{'Open original frozen snapshot'}</Localized></Link></p>}</Localized>
      <pre><code>{JSON.stringify(receipt, null, 2)}</code></pre>
      <p className="muted"><Localized>{'These are the original applied values. Current records may have changed; no replay or current status is inferred.'}</Localized></p>
    </>}</Localized>
    <p><Link target="_blank" rel="noopener noreferrer" prefetch={false} href={detail}><Localized>{'Open exact business detail'}</Localized></Link>
      <Localized>{' · '}</Localized><Link target="_blank" rel="noopener noreferrer" prefetch={false} href={state.review.draft.audit}><Localized>{'Open original audit event'}</Localized></Link></p>
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
    <p className="muted"><Localized>{'Copy the original request and receipt before leaving. Recovery is kept only in this page memory and is lost on reload.'}</Localized></p>
  </section></Localized>;
}
