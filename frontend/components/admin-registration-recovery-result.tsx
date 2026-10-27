'use client';
import Link from 'next/link';
import {Localized} from './localized';
import type {RegistrationRecoveryState} from '../lib/admin-registration-recovery';
export default function AdminRegistrationRecoveryResult({state}:{state:RegistrationRecoveryState}){
 const labels:Record<string,string>={kind:'Registration operation',id:'Original registration UUID',audit_event_no:'Audit event number',applied_status:'Original applied status',principal_id:'Existing principal UUID',role:'Role',scope_id:'Original scope UUID'};
 return <Localized><section className="panel" aria-live="polite"><h3><Localized>{'Original registration audit result'}</Localized></h3>
  <p><Localized>{'Operation phase'}</Localized>: <Localized>{state.phase}</Localized></p>
  <p><Localized>{'Historical audit only. This does not establish current identity status, effective grants, replay success or permission.'}</Localized></p>
  {state.error&&<p><Localized>{'Result code'}</Localized>: <code>{state.error}</code></p>}
  {state.historicalreceipt&&<><dl>{Object.entries(state.historicalreceipt).map(([key,value])=><div key={key}><dt><Localized>{labels[key]??key}</Localized></dt><dd>{String(value)}</dd></div>)}</dl>
   <Link href={'/activity/'+encodeURIComponent(state.historicalreceipt.audit_event_no)} prefetch={false} target="_blank" rel="noopener noreferrer"><Localized>{'Open original registration audit'}</Localized></Link></>}
 </section></Localized>;
}
