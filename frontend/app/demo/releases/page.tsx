import Link from 'next/link';
import {apiGet} from '../../../lib/api';
import {Localized} from '../../../components/localized';

type Evidence = {sample_only: boolean; initialized: boolean; items: Row[]};
type Row = {release_id: string; version: string; release_type: string; record_status: string;
  snapshot: {id: string; snapshot_no: string; content_hash: string} | null;
  readiness: {overall: string; approval_eligible: boolean; coverage: {required_dvp_total: number; current_snapshot_executed: number; current_snapshot_passed: number; snapshot_match: boolean}; rules: {group: string; rule: string; evidence: string; effective: string}[]};
  approval: {approval_no: string; status: string; current_snapshot_bound: boolean} | null;
  decision: {decision_no: string; decision: string; readiness_status: string; snapshot_id: string; current_evidence_bound: boolean} | null;
  current_release_confirmed: boolean; change_request_no: string; dvp_items: {id: string; item_no: string}[]};

export default async function Page() {
  const result = await apiGet<Evidence>('/api/v1/demo/release-evidence', {timeoutMs: 15000});
  const data = result?.sample_only === true ? result : null;
  return <Localized>
    <div className="top"><div><h1><Localized>{'Release evidence demonstration'}</Localized></h1>
      <p className="muted"><Localized>{'Synthetic records only. Read-only review; no real approvals, firmware delivery or production authorization.'}</Localized></p></div></div>
    <p><Link href="/releases/standard"><Localized>{'Standard Releases'}</Localized></Link> <Localized>{' · '}</Localized> <Link href="/releases/application"><Localized>{'Application Releases'}</Localized></Link> <Localized>{' · '}</Localized> <Link href="/demo/zfi"><Localized>{'Excel demonstration overview'}</Localized></Link> <Localized>{' · '}</Localized> <Link href="/demo/status" prefetch={false}><Localized>{'Demonstration status'}</Localized></Link></p>
    {!data ? <section className="panel"><h2><Localized>{'Evidence API unavailable'}</Localized></h2><p><Localized>{'No sample evidence is fabricated when the API is unavailable.'}</Localized></p><p className="muted"><Localized>{'The read is bounded and stops waiting when the API does not settle in time.'}</Localized></p><p><a href="/demo/releases"><Localized>{'Read again'}</Localized></a></p></section> : !data.initialized ? <section className="panel"><h2><Localized>{'Evidence samples not installed'}</Localized></h2><p><Localized>{'The complete sample family must be explicitly installed in the cloud test database before this demonstration.'}</Localized></p></section> : data.items.map(row => {
      const kind = row.release_type === 'STANDARD' ? 'standard' : row.release_type === 'APPLICATION' ? 'application' : null;
      const path = kind ? `/releases/${kind}/${encodeURIComponent(row.release_id)}` : null;
      return <section className="panel" key={row.release_id}>
        <h2>{path ? <Link href={path}>{kind === 'standard' ? 'SSR' : 'ASR'} {row.version}</Link> : <><Localized>{'Unrecognized release type'}</Localized>: {row.version}</>}</h2>
        {!kind && <p className="muted"><Localized>{'Unknown values are not mapped to SSR or ASR.'}</Localized> <code>{row.release_type}</code></p>}
        <p><Localized>{'Record status'}</Localized>: <Localized>{row.record_status}</Localized> <Localized>{' · '}</Localized> <Localized>{'Current Readiness'}</Localized>: <Localized>{row.readiness.overall}</Localized></p>
        <p><Localized>{row.current_release_confirmed ? 'Formal release evidence matches the current snapshot.' : 'Current evidence does not confirm a formal release.'}</Localized></p>
        <p><Localized>{'All stages approved does not mean formally released'}</Localized></p>
        <dl>
          <dt><Localized>{'Current Snapshot'}</Localized></dt><dd>{row.snapshot ? <><Link href={`/snapshots/${encodeURIComponent(row.snapshot.snapshot_no)}`}>{row.snapshot.snapshot_no}</Link><br/><code>{row.snapshot.id}</code><br/><code style={{overflowWrap:'anywhere'}}>{row.snapshot.content_hash}</code></> : '—'}</dd>
          <dt><Localized>{'Approval'}</Localized></dt><dd>{row.approval ? <><Link href={`/approvals/${encodeURIComponent(row.approval.approval_no)}`}>{row.approval.approval_no}</Link> <Localized>{' · '}</Localized> <Localized>{row.approval.status}</Localized> <Localized>{' · '}</Localized> <Localized>{row.approval.current_snapshot_bound ? 'Current snapshot bound' : 'Current snapshot mismatch'}</Localized></> : '—'}</dd>
          <dt><Localized>{'Release Decision'}</Localized></dt><dd>{row.decision ? <><Link href={`/release-decisions/${encodeURIComponent(row.decision.decision_no)}`}>{row.decision.decision_no}</Link> <Localized>{' · '}</Localized> <Localized>{row.decision.decision}</Localized> <Localized>{' · '}</Localized> <Localized>{'Recorded Readiness'}</Localized>: <Localized>{row.decision.readiness_status}</Localized> <Localized>{' · '}</Localized> <Localized>{row.decision.current_evidence_bound ? 'Current evidence bound' : 'Current evidence mismatch'}</Localized><br/><code>{row.decision.snapshot_id}</code></> : '—'}</dd>
        </dl>
        <h3><Localized>{'Exact snapshot test evidence'}</Localized></h3>
        <p><Localized>{'Required test items'}</Localized>: {row.readiness.coverage.required_dvp_total} <Localized>{' · '}</Localized> <Localized>{'Executed on current snapshot'}</Localized>: {row.readiness.coverage.current_snapshot_executed} <Localized>{' · '}</Localized> <Localized>{'Passed on current snapshot'}</Localized>: {row.readiness.coverage.current_snapshot_passed}</p>
        {!row.readiness.coverage.snapshot_match && <p className="muted"><Localized>{'Tests on an older snapshot do not verify the current snapshot, even when their content hashes are identical.'}</Localized></p>}
        <p><Link href={`/changes/${encodeURIComponent(row.change_request_no)}`}><Localized>{'Change Request'}</Localized></Link> <Localized>{' · '}</Localized> {row.dvp_items.map(item => <span key={item.id}><Link href={`/testing/dvp/${encodeURIComponent(item.id)}?release_id=${encodeURIComponent(row.release_id)}${row.snapshot ? `&snapshot_no=${encodeURIComponent(row.snapshot.snapshot_no)}` : ''}`}>{item.item_no}</Link>{' '}</span>)}</p>
        <div className="tablewrap"><table><thead><tr><th><Localized>{'Rule'}</Localized></th><th><Localized>{'Status'}</Localized></th></tr></thead><tbody>{row.readiness.rules.map(rule => <tr key={rule.rule}><td><Localized>{rule.rule}</Localized> <Localized>{' · '}</Localized> {rule.evidence}</td><td><Localized>{rule.effective}</Localized></td></tr>)}</tbody></table></div>
        {kind === 'application' && path && <p><Link href={`${path}/readiness`}><Localized>{'Readiness'}</Localized></Link> <Localized>{' · '}</Localized> <Link href={`${path}/passport`}><Localized>{'Software Passport'}</Localized></Link></p>}
      </section>;
    })}
  </Localized>;
}
