'use client';
import Link from 'next/link';
import {Localized} from './localized';
import type {ReleaseDecisionSupersessionState} from '../lib/release-decision-supersession-transport';
export default function ReleaseDecisionSupersessionResult({state}:{state:ReleaseDecisionSupersessionState}){
 const r=state.receipt?.result;
 return <section className="panel"><h3><Localized>{'Release decision replacement result'}</Localized></h3>
  <Localized>{state.phase==='confirmed'&&r?<><p><Localized>{'The matching atomic audit confirmed the original replacement operation.'}</Localized></p>
   <p><Localized>{'New decision'}</Localized>: <Link href={'/release-decisions/'+encodeURIComponent(String(r.decision_no))}>{String(r.decision_no)}</Link></p>
   <p><Localized>{'Predecessor decision UUID'}</Localized>: <code>{String(r.supersedes_id)}</code></p>
   <p><Localized>{'Frozen snapshot'}</Localized>: <Link href={'/snapshots/'+encodeURIComponent(String(r.snapshot_no))}>{String(r.snapshot_no)}</Link></p>
   <p><Link href={'/activity/'+state.receipt!.audit_event_no} target="_blank" rel="noopener noreferrer"><Localized>{'Original atomic audit →'}</Localized></Link></p>
   <p className="muted"><Localized>{'This confirmation preserves the original applied values. It does not revoke earlier delivery or production facts.'}</Localized></p></>:
   state.phase==='unknown'?<p><Localized>{'The replacement outcome is unknown. Query the original audit before retrying the exact request.'}</Localized></p>:
   state.phase==='rejected'?<p><Localized>{'The replacement request was rejected before confirmation.'}</Localized></p>:
   <p><Localized>{'No confirmed replacement result yet.'}</Localized></p>}</Localized>
 </section>;
}
