'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { registrationMessages, type RegistrationSubmissionState } from '../lib/admin-registration-transport';

export default function AdminRegistrationResult({ state }: { state: RegistrationSubmissionState }) {
  if (state.phase === 'idle') return null;
  const kind = state.review.kind, body = state.review.request.body;
  const id = kind === 'PRINCIPAL' ? body.principal_id : kind === 'GLOBAL' ? body.grant_id : body.membership_id;
  return <Localized><section aria-live="polite" aria-busy={state.phase === 'sending'}>
    <h3><Localized>{'Registration submission result'}</Localized></h3>
    <Localized>{state.phase === 'sending' && <p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && <p role="alert"><Localized>{'The outcome is unknown. Keep the original audit number and exact request.'}</Localized></p>}</Localized>
    <Localized>{state.phase === 'rejected' && <p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}</Localized>
    <Localized>{state.error && <p><Localized>{Object.prototype.hasOwnProperty.call(registrationMessages,state.error) ? registrationMessages[state.error] : registrationMessages.outcome_unknown}</Localized></p>}</Localized>
    <Localized>{state.phase === 'unknown' && state.error !== 'outcome_unknown' && <p><Localized>{
      'The latest retry was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}</Localized>
    <Localized>{state.receipt && <>
      <p><Localized>{'The exact operation receipt was confirmed.'}</Localized></p>
      <p><Localized>{'Applied status for this operation'}</Localized><Localized>{': '}</Localized><Localized>{state.receipt.applied_status}</Localized></p>
      <p><Localized>{'Status observed in the receipt'}</Localized><Localized>{': '}</Localized><Localized>{state.receipt.current_status}</Localized></p>
      <p><Localized>{state.receipt.replayed ? 'Previously recorded operation replayed.' : 'New operation recorded.'}</Localized></p>
      <p className="muted"><Localized>{'The observed status may differ from the original applied status and may change again.'}</Localized></p>
      <pre><code>{JSON.stringify(state.receipt,null,2)}</code></pre>
    </>}</Localized>
    <p className="muted"><Localized>{'Copy the original request and receipt before leaving. This page keeps recovery data only in memory.'}</Localized></p>
    <p className="muted"><Localized>{'Registration does not activate the identity or resume the grant. Activation requires a separate audited operation.'}</Localized></p>
    <Localized>{kind === 'PRINCIPAL' ? <p className="muted"><Localized>{
      'Identity detail reading is not available yet. Keep the exact principal UUID and receipt.'}</Localized></p> :
      <Link target="_blank" rel="noopener noreferrer" prefetch={false} href={'/account/grants/'+kind+'/'+id+'?offset=0'}>
        <Localized>{'Open current grant detail and history'}</Localized>
      </Link>}</Localized>
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
  </section></Localized>;
}
