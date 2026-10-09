import Link from 'next/link';
import { Localized } from './localized';
import type { ImpactCorrection } from '../lib/issue-views';

/** Relationship metadata only: not a submission or a claim about the original receipt. */
export default function ImpactCorrectionHistory({ judgment }: { judgment: ImpactCorrection }) {
  if (!judgment.supersedes_id && !judgment.superseded_by_id) return null;
  const audit = (id: string) => '/activity/' + encodeURIComponent('EVT-IMPACT-' + id);
  return <Localized><div className="muted">
    {judgment.supersedes_id && <p><Localized>{'Supersedes judgment'}</Localized>: <code>{judgment.supersedes_id}</code>
      <Localized>{' · '}</Localized><Link href={audit(judgment.supersedes_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open predecessor audit'}</Localized></Link></p>}
    {judgment.correction_reason && <p><Localized>{'Correction reason'}</Localized>: {judgment.correction_reason}</p>}
    {judgment.superseded_by_id && <p><Localized>{'Explicitly superseded by'}</Localized>: <code>{judgment.superseded_by_id}</code>
      <Localized>{' · '}</Localized><Link href={audit(judgment.superseded_by_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open replacement audit'}</Localized></Link></p>}
    <p><Localized>{'Correction history preserves original judgments. It does not prove test success or release permission.'}</Localized></p>
  </div></Localized>;
}
