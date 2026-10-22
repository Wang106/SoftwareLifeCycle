import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Snapshot = {
  id: string; snapshot_no: string; status: string; content_hash: string;
};
type Readiness = {
  overall: string; approval_eligible: boolean;
  coverage: { required_dvp_total: number; current_snapshot_executed: number; current_snapshot_passed: number; snapshot_match: boolean };
  rules: { group: string; rule: string; evidence: string; effective: string }[];
};
type Approval = { approval_no: string; status: string; current_snapshot_bound: boolean };
type Decision = { decision_no: string; decision: string; readiness_status: string; snapshot_id: string; current_evidence_bound: boolean };
type Evidence = {
  release: { id: string; version: string; release_type: string; record_status: string };
  snapshot: Snapshot | null;
  readiness: Readiness;
  approval: Approval | null;
  decision: Decision | null;
  current_release_confirmed: boolean;
};

export async function ReleaseEvidenceSummary({ releaseId }: { releaseId: string }) {
  const data = await apiGet<Evidence>(`/api/v1/releases/${encodeURIComponent(releaseId)}/evidence-summary`);
  if (!data || data.release.id !== releaseId) {
    return <Localized><section className="panel"><h2><Localized>{'Evidence summary'}</Localized></h2>
      <p className="datasource"><Localized>{'Evidence summary unavailable. Counts are unknown; no unbounded fallback is used.'}</Localized></p></section></Localized>;
  }
  return <Localized>
    <section className="panel">
      <h2><Localized>{'Release evidence summary'}</Localized></h2>
      <p className="muted"><Localized>{'Read-only projection of the current frozen snapshot, readiness gates, approval and the effective release decision. It does not infer a formal release from record status or stage counts.'}</Localized></p>
      <p><Localized>{'Record status'}</Localized><Localized>{': '}</Localized><Localized>{data.release.record_status}</Localized><Localized>{' · '}</Localized><Localized>{'Current Readiness'}</Localized><Localized>{': '}</Localized><Localized>{data.readiness.overall}</Localized></p>
      <p><Localized>{data.current_release_confirmed ? 'Formal release evidence matches the current snapshot.' : 'Current evidence does not confirm a formal release.'}</Localized></p>
      <p className="muted"><Localized>{'All stages approved does not mean formally released'}</Localized></p>
      <dl>
        <dt><Localized>{'Current snapshot'}</Localized></dt>
        <dd>{data.snapshot ? <><Link href={`/snapshots/${encodeURIComponent(data.snapshot.snapshot_no)}`}><Localized>{data.snapshot.snapshot_no}</Localized></Link><Localized>{' · '}</Localized><Localized>{data.snapshot.status}</Localized><br/><code style={{overflowWrap:'anywhere'}}>{data.snapshot.content_hash}</code></> : <Localized>{'—'}</Localized>}</dd>
        <dt><Localized>{'Approval'}</Localized></dt>
        <dd>{data.approval ? <><Link href={`/approvals/${encodeURIComponent(data.approval.approval_no)}`}><Localized>{data.approval.approval_no}</Localized></Link><Localized>{' · '}</Localized><Localized>{data.approval.status}</Localized><Localized>{' · '}</Localized><Localized>{data.approval.current_snapshot_bound ? 'Current snapshot bound' : 'Current snapshot mismatch'}</Localized></> : <Localized>{'—'}</Localized>}</dd>
        <dt><Localized>{'Release Decision'}</Localized></dt>
        <dd>{data.decision ? <><Link href={`/release-decisions/${encodeURIComponent(data.decision.decision_no)}`}><Localized>{data.decision.decision_no}</Localized></Link><Localized>{' · '}</Localized><Localized>{data.decision.decision}</Localized><Localized>{' · '}</Localized><Localized>{'Recorded Readiness'}</Localized><Localized>{': '}</Localized><Localized>{data.decision.readiness_status}</Localized><Localized>{' · '}</Localized><Localized>{data.decision.current_evidence_bound ? 'Current evidence bound' : 'Current evidence mismatch'}</Localized></> : <Localized>{'—'}</Localized>}</dd>
      </dl>
      <h3><Localized>{'Exact snapshot test evidence'}</Localized></h3>
      <p><Localized>{'Required test items'}</Localized><Localized>{': '}</Localized>{data.readiness.coverage.required_dvp_total}<Localized>{' · '}</Localized><Localized>{'Executed on current snapshot'}</Localized><Localized>{': '}</Localized>{data.readiness.coverage.current_snapshot_executed}<Localized>{' · '}</Localized><Localized>{'Passed on current snapshot'}</Localized><Localized>{': '}</Localized>{data.readiness.coverage.current_snapshot_passed}</p>
      {!data.readiness.coverage.snapshot_match && <p className="muted"><Localized>{'Tests on an older snapshot do not verify the current snapshot, even when their content hashes are identical.'}</Localized></p>}
      <div className="tablewrap"><table><thead><tr><th><Localized>{'Rule'}</Localized></th><th><Localized>{'Status'}</Localized></th></tr></thead><tbody>{data.readiness.rules.map(rule => <tr key={rule.rule}><td><Localized>{rule.rule}</Localized><Localized>{' · '}</Localized>{rule.evidence}</td><td><Localized>{rule.effective}</Localized></td></tr>)}</tbody></table></div>
    </section>
  </Localized>;
}
