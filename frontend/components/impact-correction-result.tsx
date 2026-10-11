'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { impactCorrectionEvent, type ImpactCorrectionState } from '../lib/impact-correction-transport';
import { evidenceResourceMessages } from './evidence-resource-command-result';

export default function ImpactCorrectionResult({state}:{state:ImpactCorrectionState}) {
  if(state.phase==='idle')return null;
  const c=state.command;
  const link=(href:string,label:string)=><Link href={href} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{label}</Localized></Link>;
  return <Localized><section aria-live="polite" aria-busy={state.phase==='sending'||state.phase==='checking'}>
    <h3><Localized>{'Impact correction result'}</Localized></h3>
    {state.phase==='sending'&&<p><Localized>{'Sending the frozen request. Do not submit another operation.'}</Localized></p>}
    {state.phase==='checking'&&<p><Localized>{'Querying the original audit. This does not repeat the business write.'}</Localized></p>}
    {state.phase==='unknown'&&<p role="alert"><Localized>{'The outcome is unknown. Keep the original request ID, target and exact body.'}</Localized></p>}
    {state.phase==='rejected'&&<p role="alert"><Localized>{'This attempt was rejected.'}</Localized></p>}
    {state.error&&<p><Localized>{state.error==='impact_correction_disabled'?'Impact correction submission is disabled in this environment.':evidenceResourceMessages[state.error]}</Localized></p>}
    {state.phase==='unknown'&&state.error!=='outcome_unknown'&&<p><Localized>{'The latest attempt was rejected, but the earlier uncertain operation may have committed.'}</Localized></p>}
    {state.receipt&&<>
      <p><Localized>{'The original operation was confirmed by its matching atomic audit.'}</Localized></p>
      <p className="muted"><Localized>{'This confirms the original impact replacement only. Current impact, test success and release permission are separate observations.'}</Localized></p>
      <pre><code>{JSON.stringify(state.receipt,null,2)}</code></pre>
      <p><Localized>{'These are the original applied values. Current records may have changed; no replay or current status is inferred.'}</Localized></p>
    </>}
    <p>{link('/issues/'+encodeURIComponent(c.target)+'/impact/'+c.body.release_id+'?'+new URLSearchParams({snapshot_id:c.body.snapshot_id}),'Open exact business detail')}
      {' · '}{link('/activity/'+encodeURIComponent(impactCorrectionEvent(c)),'Open original audit event')}</p>
    <p>{link('/activity/'+encodeURIComponent('EVT-IMPACT-'+c.predecessor.id),'Open predecessor audit')}</p>
    {state.receipt&&<p>{link('/snapshots/'+encodeURIComponent(String(state.receipt.result.snapshot_no)),'Open original frozen snapshot')}</p>}
    <p className="muted"><Localized>{'Current detail and history are independent observations; they do not prove the result of the original request.'}</Localized></p>
    <p className="muted"><Localized>{'In-memory recovery is lost on reload. Export original recovery text to restore an audit-only query in a later session.'}</Localized></p>
  </section></Localized>;
}
