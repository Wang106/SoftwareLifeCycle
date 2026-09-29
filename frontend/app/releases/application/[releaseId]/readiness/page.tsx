import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Readiness = {
  overall: string; approval_eligible: boolean;
  coverage: { snapshot_no: string | null; dvp_execution_coverage: number };
  artifact_policy: { sha_completeness: number; policy_completeness: number };
  rules: { group: string; rule: string; raw: string; effective: string; evidence: string }[];
  exceptions: { exception_no: string; status: string; scope: string; reason: string;
    compensating_control: string | null; snapshot_no: string | null; rule_code: string }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const base = `/releases/application/${encodeURIComponent(releaseId)}`;
  const readiness = await apiGet<Readiness>(`/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/readiness`);
  if (!readiness) return <section className="panel"><h1>Readiness unavailable</h1>
    <p className="muted">The application release was not found or the API could not be reached.</p>
    <Link href={base}>← Release profile</Link></section>;
  const rawPass = readiness.rules.filter(row => row.raw === 'PASS').length;
  return <>
    <div className="top"><div><div className="eyebrow">APPLICATION RELEASE READINESS</div><h1>{readiness.overall}</h1>
      <p className="muted">{readiness.coverage.snapshot_no || 'No snapshot'} · Rules evaluated for this exact application release.</p></div>
      <span className={'status ' + (readiness.approval_eligible ? 'pass' : 'warning')}>{readiness.approval_eligible ? 'ELIGIBLE' : 'BLOCKED'}</span></div>
    <div className="cards">
      <div className="card"><span className="muted">RAW PASS</span><div className="metric">{rawPass} / {readiness.rules.length}</div></div>
      <div className="card"><span className="muted">CURRENT SNAPSHOT DVP</span><div className="metric">{readiness.coverage.dvp_execution_coverage}%</div></div>
      <div className="card"><span className="muted">SHA COMPLETE</span><div className="metric">{readiness.artifact_policy.sha_completeness}%</div></div>
      <div className="card"><span className="muted">POLICY COMPLETE</span><div className="metric">{readiness.artifact_policy.policy_completeness}%</div></div>
    </div>
    <section className="panel tablewrap"><h2>Readiness gates</h2>
      <p className="muted">Raw evidence remains visible when an approved exception changes an effective result.</p>
      <table><thead><tr><th>Group</th><th>Rule</th><th>Raw</th><th>Effective</th><th>Evidence</th></tr></thead>
        <tbody>{readiness.rules.map(row => <tr key={`${row.group}-${row.rule}`}><td>{row.group}</td><td>{row.rule}</td>
          <td><span className={'status ' + (row.raw === 'PASS' ? 'pass' : 'warning')}>{row.raw}</span></td>
          <td><span className={'status ' + (row.effective === 'PASS' ? 'pass' : 'warning')}>{row.effective}</span></td>
          <td>{row.evidence}</td></tr>)}</tbody></table>
    </section>
    {readiness.exceptions.length ? <section className="panel"><h2>Approved exceptions</h2>
      {readiness.exceptions.map(row => <div className="kv" key={row.exception_no}>
        <span>Exception</span><b>{row.exception_no} · {row.status}</b>
        <span>Scope</span><b>{row.scope}</b><span>Rule</span><b>{row.rule_code}</b>
        <span>Snapshot</span><b>{row.snapshot_no || '—'}</b>
        <span>Reason</span><b>{row.reason}</b>
        <span>Compensating control</span><b>{row.compensating_control || '—'}</b>
      </div>)}</section> : <section className="panel"><h2>Approved exceptions</h2><p className="muted">None recorded for the current snapshot.</p></section>}
    <p className="datasource"><Link href={base}>← Release profile</Link></p>
  </>;
}
