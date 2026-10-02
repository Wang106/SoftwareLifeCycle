
import { Localized } from "../../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Readiness = {
  release_id: string; snapshot_id: string; snapshot: { id: string; snapshot_no: string; content_hash: string; status: string } | null;
  exception_total: number; overall: string; approval_eligible: boolean;
  coverage: { snapshot_no: string | null; dvp_execution_coverage: number };
  artifact_policy: { sha_completeness: number; policy_completeness: number };
  rules: { group: string; rule: string; raw: string; effective: string; evidence: string }[];
};
type ExceptionRow = { exception_no: string; status: string; scope: string; reason: string;
    compensating_control: string | null; snapshot_no: string | null; rule_code: string; id: string;
};

type ExceptionPage = { release_id: string; snapshot_id: string; total: number; next_offset: number | null; items: ExceptionRow[] };
type Search = Record<string, string | string[] | undefined>;
function value(search: Search, key: string, fallback: string) {
  const raw = search[key]; return raw === undefined ? fallback : typeof raw === 'string' ? raw : 'invalid';
}
export default async function Page({ params, searchParams }: { params: Promise<{ releaseId: string }>; searchParams?: Promise<Search> }) {
  const { releaseId } = await params;
  const search = await searchParams || {};
  const base = `/releases/application/${encodeURIComponent(releaseId)}`;
  const endpoint = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/readiness`;
  const requested = new URLSearchParams();
  if (search.readiness_snapshot_id !== undefined) requested.set('snapshot_id', value(search, 'readiness_snapshot_id', 'invalid'));
  const readiness = await apiGet<Readiness>(`${endpoint}/summary?${requested}`);
  if (!readiness || readiness.release_id !== releaseId || readiness.snapshot_id !== (readiness.snapshot?.id || 'none') ||
      (requested.has('snapshot_id') && readiness.snapshot_id !== requested.get('snapshot_id')))
    return <section className="panel"><h1><Localized>{"Readiness unavailable"}</Localized></h1>
      <p className="muted"><Localized>{"The current readiness selection changed or the API is unavailable."}</Localized></p>
      <Link href={`${base}/readiness`}><Localized>{"Read latest readiness"}</Localized></Link><p><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p></section>;
  const limit = value(search, 'readiness_limit', '50');
  const offset = value(search, 'readiness_exception_offset', '0');
  const query = new URLSearchParams({ snapshot_id: readiness.snapshot_id, limit, offset });
  const response = await apiGet<ExceptionPage>(`${endpoint}/exceptions?${query}`);
  const exceptionPage = response && response.release_id === releaseId && response.snapshot_id === readiness.snapshot_id ? response : null;
  function href(next: number) {
    return `${base}/readiness?${new URLSearchParams({ readiness_snapshot_id: readiness!.snapshot_id, readiness_limit: limit, readiness_exception_offset: String(next) })}`;
  }
  const rawPass = readiness.rules.filter(row => row.raw === 'PASS').length;
  return <Localized><>
    <div className="top"><div><div className="eyebrow"><Localized>{"APPLICATION RELEASE READINESS"}</Localized></div><h1><Localized>{readiness.overall}</Localized></h1>
      <p className="muted"><Localized>{readiness.coverage.snapshot_no || 'No snapshot'}</Localized><Localized>{" · Rules evaluated for this exact application release."}</Localized></p></div>
      <span className={'status ' + (readiness.approval_eligible ? 'pass' : 'warning')}><Localized>{readiness.approval_eligible ? 'ELIGIBLE' : 'BLOCKED'}</Localized></span></div>
    <p className="muted"><Localized>{"Snapshot hash"}</Localized>: <code style={{overflowWrap: "anywhere"}}>{readiness.snapshot?.content_hash || "—"}</code></p>
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
    <section className="panel"><h2><Localized>{"Approved exceptions"}</Localized></h2>
      <p className="muted"><Localized>{"Total approved exceptions"}</Localized>: <Localized>{readiness.exception_total}</Localized> · <Localized>{"Page records"}</Localized>: <Localized>{exceptionPage ? exceptionPage.items.length : '—'}</Localized></p>
      <Link href={href(0)}><Localized>{"First page"}</Localized></Link>
      <Localized>{exceptionPage?.next_offset !== null && exceptionPage?.next_offset !== undefined && <> · <Link href={href(exceptionPage.next_offset)}><Localized>{"Next page"}</Localized></Link></>}</Localized>
      <Localized>{!exceptionPage ? <p className="muted"><Localized>{"Readiness exception page unavailable."}</Localized></p> : <>
        {exceptionPage.items.map(row => <div className="kv" key={row.id}>
          <span><Localized>{"Exception"}</Localized></span><b><Localized>{row.exception_no}</Localized><Localized>{" · "}</Localized><Localized>{row.status}</Localized></b>
          <span><Localized>{"Scope"}</Localized></span><b><Localized>{row.scope}</Localized></b><span><Localized>{"Rule"}</Localized></span><b><Localized>{row.rule_code}</Localized></b>
          <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{row.snapshot_no || '—'}</Localized></b>
          <span><Localized>{"Reason"}</Localized></span><b><Localized>{row.reason}</Localized></b>
          <span><Localized>{"Compensating control"}</Localized></span><b><Localized>{row.compensating_control || '—'}</Localized></b>
        </div>)}
        {!exceptionPage.items.length && <p className="muted"><Localized>{readiness.exception_total ? "No approved exceptions on this page." : "None recorded for the current snapshot."}</Localized></p>}
      </>}</Localized>
    </section>
    <p className="muted"><Localized>{"Artifact checks use current release declarations; evidence and exceptions use the selected current snapshot. This observation does not grant approval or write permission."}</Localized></p>
    <p><Localized>{"Snapshot UUID"}</Localized>: <code>{readiness.snapshot_id}</code> · <Link href={`${base}/readiness`}><Localized>{"Read latest readiness"}</Localized></Link></p>
    <p className="datasource"><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p>
  </></Localized>;
}
