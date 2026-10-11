import Link from 'next/link';
import { Localized } from './localized';
import type { ImpactCorrection } from '../lib/issue-views';

/** Relationship metadata only: not a submission or a claim about the original receipt. */
export default function ImpactCorrectionHistory({ judgment, issueNo }: { judgment: ImpactCorrection & {id?:string;release_id?:string;snapshot_id?:string|null;decision?:string|null;reason?:string;actor_name?:string;created_at?:string}; issueNo?:string }) {
  // A bounded preparation link is review context, never evidence of current effectiveness.
  const ids=[judgment.id,judgment.release_id,judgment.snapshot_id];
  const canPrepare=typeof issueNo==='string'&&!!issueNo.trim()&&issueNo.length<=50&&judgment.superseded_by_id===null&&judgment.action!=='WITHDRAW'&&judgment.is_context_terminal!==false&&
    ids.every(id=>typeof id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id))&&
    ['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW'].includes(judgment.decision??'');
  if (judgment.action==='WITHDRAW') return <Localized><div className="muted"><p><Localized>{'Impact judgment withdrawn'}</Localized></p><p><Localized>{'Withdrawal reason'}</Localized>: {judgment.reason}</p><p><Localized>{'Correction reason'}</Localized>: {judgment.correction_reason}</p><p><Localized>{'Withdraws judgment'}</Localized>: <code>{judgment.supersedes_id}</code>{judgment.supersedes_id&&<Link href={'/activity/'+encodeURIComponent('EVT-IMPACT-'+judgment.supersedes_id)} prefetch={false}><Localized>{'Open predecessor audit'}</Localized></Link>}</p><p><Localized>{'Declared reviewer'}</Localized>: {judgment.actor_name} · {judgment.created_at}</p><Link href={'/activity/'+encodeURIComponent('EVT-IMPACT-'+judgment.id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open original withdrawal audit'}</Localized></Link><p><Localized>{'Withdrawal does not revive older judgments or grant release permission.'}</Localized></p></div></Localized>;
  if (!judgment.supersedes_id && !judgment.superseded_by_id && !judgment.after_withdrawal_id && !canPrepare) return null;
  const audit = (id: string) => '/activity/' + encodeURIComponent('EVT-IMPACT-' + id);
  return <Localized><div className="muted">
    {judgment.after_withdrawal_id && <p><Localized>{'New judgment after withdrawal'}</Localized>: <code>{judgment.after_withdrawal_id}</code><Link href={audit(judgment.after_withdrawal_id)} prefetch={false}><Localized>{'Open original withdrawal audit'}</Localized></Link></p>}
    {judgment.supersedes_id && <p><Localized>{'Supersedes judgment'}</Localized>: <code>{judgment.supersedes_id}</code>
      <Localized>{' · '}</Localized><Link href={audit(judgment.supersedes_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open predecessor audit'}</Localized></Link></p>}
    {judgment.correction_reason && <p><Localized>{'Correction reason'}</Localized>: {judgment.correction_reason}</p>}
    {judgment.superseded_by_id && <p><Localized>{'Explicitly superseded by'}</Localized>: <code>{judgment.superseded_by_id}</code>
      <Localized>{' · '}</Localized><Link href={audit(judgment.superseded_by_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open replacement audit'}</Localized></Link></p>}
    {canPrepare&&<p><Link href={'/commands?'+new URLSearchParams({operation:'impact-correction',target:issueNo!,release:judgment.release_id!,snapshot:judgment.snapshot_id!,predecessor:judgment.id!,previous_decision:judgment.decision!})}>
      <Localized>{'Prepare replacement of this judgment →'}</Localized></Link></p>}
    {canPrepare&&<p><Localized>{'The API rechecks the current predecessor and frozen context. This history link does not grant permission or confirm an operation.'}</Localized></p>}
    <p><Localized>{'Correction history preserves original judgments. It does not prove test success or release permission.'}</Localized></p>
  </div></Localized>;
}
