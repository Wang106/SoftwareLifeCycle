
import { Localized, LocalizedAttributes } from "../../../../../components/localized";
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
  if (!readiness) return <section className="panel"><h1><Localized>{"Readiness unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p>
    <Link href={base}><Localized>{"← Release profile"}</Localized></Link></section>;
  const rawPass = readiness.rules.filter(row => row.raw === 'PASS').length;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"APPLICATION RELEASE READINESS"}</Localized></div><h1><Localized>{readiness.overall}</Localized></h1>
      <p className="muted"><Localized>{readiness.coverage.snapshot_no || 'No snapshot'}</Localized><Localized>{" · Rules evaluated for this exact application release."}</Localized></p></div>
      <span className={'status ' + (readiness.approval_eligible ? 'pass' : 'warning')}><Localized>{readiness.approval_eligible ? 'ELIGIBLE' : 'BLOCKED'}</Localized></span></div>
    <div className="cards">
      <div className="card"><span className="muted"><Localized>{"RAW PASS"}</Localized></span><div className="metric"><Localized>{rawPass}</Localized><Localized>{" / "}</Localized><Localized>{readiness.rules.length}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"CURRENT SNAPSHOT DVP"}</Localized></span><div className="metric"><Localized>{readiness.coverage.dvp_execution_coverage}</Localized><Localized>{"%"}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"SHA COMPLETE"}</Localized></span><div className="metric"><Localized>{readiness.artifact_policy.sha_completeness}</Localized><Localized>{"%"}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"POLICY COMPLETE"}</Localized></span><div className="metric"><Localized>{readiness.artifact_policy.policy_completeness}</Localized><Localized>{"%"}</Localized></div></div>
    </div>
    <section className="panel tablewrap"><h2><Localized>{"Readiness gates"}</Localized></h2>
      <p className="muted"><Localized>{"Raw evidence remains visible when an approved exception changes an effective result."}</Localized></p>
      <table><thead><tr><th><Localized>{"Group"}</Localized></th><th><Localized>{"Rule"}</Localized></th><th><Localized>{"Raw"}</Localized></th><th><Localized>{"Effective"}</Localized></th><th><Localized>{"Evidence"}</Localized></th></tr></thead>
        <tbody><Localized>{readiness.rules.map(row => <tr key={`${row.group}-${row.rule}`}><td><Localized>{row.group}</Localized></td><td><Localized>{row.rule}</Localized></td>
          <td><span className={'status ' + (row.raw === 'PASS' ? 'pass' : 'warning')}><Localized>{row.raw}</Localized></span></td>
          <td><span className={'status ' + (row.effective === 'PASS' ? 'pass' : 'warning')}><Localized>{row.effective}</Localized></span></td>
          <td><Localized>{row.evidence}</Localized></td></tr>)}</Localized></tbody></table>
    </section>
    <Localized>{readiness.exceptions.length ? <section className="panel"><h2><Localized>{"Approved exceptions"}</Localized></h2>
      <Localized>{readiness.exceptions.map(row => <div className="kv" key={row.exception_no}>
        <span><Localized>{"Exception"}</Localized></span><b><Localized>{row.exception_no}</Localized><Localized>{" · "}</Localized><Localized>{row.status}</Localized></b>
        <span><Localized>{"Scope"}</Localized></span><b><Localized>{row.scope}</Localized></b><span><Localized>{"Rule"}</Localized></span><b><Localized>{row.rule_code}</Localized></b>
        <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{row.snapshot_no || '—'}</Localized></b>
        <span><Localized>{"Reason"}</Localized></span><b><Localized>{row.reason}</Localized></b>
        <span><Localized>{"Compensating control"}</Localized></span><b><Localized>{row.compensating_control || '—'}</Localized></b>
      </div>)}</Localized></section> : <section className="panel"><h2><Localized>{"Approved exceptions"}</Localized></h2><p className="muted"><Localized>{"None recorded for the current snapshot."}</Localized></p></section>}</Localized>
    <p className="datasource"><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
