'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { acceptanceCorrectionEvent, type AcceptanceCorrectionState } from '../lib/acceptance-correction-transport';
import { evidenceResourceMessages } from './evidence-resource-command-result';

export default function AcceptanceCorrectionResult({state}:{state:AcceptanceCorrectionState}) {
  if(state.phase==='idle')return null;
  const c=state.command;
  const link=(href:string,label:string)=><Link href={href} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{label}</Localized></Link>;
  return <Localized><section aria-live="polite" aria-busy={state.phase==='sending'||state.phase==='checking'}>
    <h3><Localized>{'Acceptance correction result'}</Localized></h3>
    {state.phase==='sending'&&<p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}
    {state.phase==='checking'&&<p><Localized>{'Querying the original audit. This does not repeat the business write.'}</Localized></p>}
    {state.phase==='unknown'&&<p role="alert"><Localized>{'The outcome is unknown. Keep the original request ID, target and exact body.'}</Localized></p>}
    {state.phase==='rejected'&&<p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}
    {state.error&&<p><Localized>{state.error==='acceptance_correction_disabled'?'Acceptance correction submission is disabled in this environment.':evidenceResourceMessages[state.error]}</Localized></p>}
    {state.phase==='unknown'&&state.error!=='outcome_unknown'&&<p><Localized>{'The latest attempt was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}
    {state.receipt&&<>
      <p><Localized>{'The original operation was confirmed by its matching atomic audit.'}</Localized></p>
      <p className="muted"><Localized>{'This confirms the original replacement or withdrawal only. Current effectiveness, test success and acceptance completion are separate observations.'}</Localized></p>
      <pre><code>{JSON.stringify(state.receipt,null,2)}</code></pre>
      <p><Localized>{'These are the original applied values. Current records may have changed; no replay or current status is inferred.'}</Localized></p>
    </>}
    <p>{link('/changes/'+encodeURIComponent(c.target)+'/coverage?'+new URLSearchParams({group_kind:'acceptance',group_id:c.body.criterion_id}),'Open exact business detail')}
      {' · '}{link('/activity/'+encodeURIComponent(acceptanceCorrectionEvent(c)),'Open original audit event')}</p>
    <p>{link('/activity/'+encodeURIComponent('EVT-AC-'+c.predecessor.id),'Open predecessor audit')}
      {' · '}{link('/testing/dvp/'+encodeURIComponent(c.predecessor.dvp_item_id),'Open predecessor DVP item')}
      {c.body.action==='SUPERSEDE'&&<>{' · '}{link('/testing/dvp/'+encodeURIComponent(c.body.dvp_item_id),'Open replacement DVP item')}</>}</p>
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
    <p className="muted"><Localized>{'Correction recovery is kept only in page memory. Reloading loses it; copying a request does not create a recovery import.'}</Localized></p>
  </section></Localized>;
}
