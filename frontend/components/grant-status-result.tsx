'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { submissionMessages, type SubmissionState } from '../lib/grant-status-submission';

export default function GrantStatusResult({ state }: { state: SubmissionState }) {
  if (state.phase === 'idle') return null;
  return <Localized><section aria-live="polite" aria-busy={state.phase === 'sending'}>
    <h3><Localized>{'Grant submission result'}</Localized></h3>
    <Localized>{state.phase === 'sending' && <p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && <p role="alert"><Localized>{'The outcome is unknown. Keep the original audit number and exact request.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'rejected' && <p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}</Localized>
    <Localized>{state.error && <p><Localized>{submissionMessages[state.error]}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && state.error !== 'outcome_unknown' && <p><Localized>{
      'The latest retry was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}</Localized>
    <Localized>{state.receipt && <>
      <p><Localized>{'The exact operation receipt was confirmed.'}</Localized></p>
      <p><Localized>{'Applied status for this operation'}</Localized><Localized>{': '}</Localized><Localized>{state.receipt.applied_status}</Localized></p>
      <p><Localized>{'Status observed in the receipt'}</Localized><Localized>{': '}</Localized><Localized>{state.receipt.current_status}</Localized></p>
      <p><Localized>{state.receipt.replayed ? 'Previously recorded operation replayed.' : 'New operation recorded.'}</Localized></p>
      <p className="muted"><Localized>{'The observed status may differ from the original applied status and may change again.'}</Localized></p>
      <pre><code>{JSON.stringify(state.receipt, null, 2)}</code></pre>
    </>}</Localized>
    <p className="muted"><Localized>{'Copy the original request and receipt before leaving. This page keeps recovery data only in memory.'}</Localized></p>
    <p className="muted"><Localized>{'Suspending your own administrator grant may prevent further reads or retries. Another administrator or the offline recovery procedure may be needed.'}</Localized></p>
    <Link target="_blank" rel="noopener noreferrer" prefetch={false} href={'/account/grants/' + state.review.target.scope + '/' + state.review.target.id + '?offset=0'}>
      <Localized>{'Open current grant detail and history'}</Localized>
    </Link>
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
  </section></Localized>;
}
