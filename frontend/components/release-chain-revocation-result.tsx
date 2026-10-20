'use client';
import Link from 'next/link';
import {Localized} from './localized';
import type {ReleaseChainRevocationState} from '../lib/release-chain-revocation-transport';
export default function ReleaseChainRevocationResult({state}:{state:ReleaseChainRevocationState}){
 const r=state.receipt?.result;
 return <section className="panel"><h3><Localized>{'Release-chain revocation result'}</Localized></h3>
  <Localized>{state.phase==='confirmed'&&r?<><p><Localized>{'The matching atomic audit confirmed the original revocation operation.'}</Localized></p>
   <p><Localized>{'Revocation record'}</Localized>: <code>{String(r.revocation_no)}</code></p>
   <p><Localized>{'Revoked target kind'}</Localized>: <Localized>{String(r.target_kind)}</Localized></p>
   <p><Localized>{'Revocation reason'}</Localized>: <span style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{String(r.reason)}</span></p>
   <p><Link href={'/activity/'+state.receipt!.audit_event_no} target="_blank" rel="noopener noreferrer"><Localized>{'Original atomic audit →'}</Localized></Link></p>
   <p className="muted"><Localized>{'This confirmation preserves the original applied values. It ends future authority and does not recall existing delivery or production facts.'}</Localized></p></>:
   state.phase==='unknown'?<p><Localized>{'The revocation outcome is unknown. Query the original audit before retrying the exact request.'}</Localized></p>:
   state.phase==='rejected'?<p><Localized>{'The revocation request was rejected before confirmation.'}</Localized></p>:
   <p><Localized>{'No confirmed revocation result yet.'}</Localized></p>}</Localized>
 </section>;
}
