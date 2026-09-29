import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  base_release: { version: string; status: string } | null;
  snapshot: { snapshot_no: string; status: string; content_hash: string } | null;
};
type DecisionResponse = {
  release_id: string; current_snapshot_no: string | null;
  decision: null | {
    decision_no: string; decision: string; readiness_status: string;
    decided_by: string; decision_notes: string | null; decided_at: string;
    snapshot_id: string; snapshot_no: string | null; is_current_snapshot: boolean;
    approval_no: string | null; approval_status: string | null;
  };
};
type Downstream = {
  deliveries: { id: string; package_no: string; revision: number; status: string; snapshot_no: string | null; recipient_code: string }[];
  distributions: { id: string; distribution_no: string; status: string; package_no: string; package_revision: number; recipient_code: string }[];
  authorizations: { id: string; authorization_no: string; status: string; snapshot_no: string | null; distribution_no: string | null; site_code: string; line_code: string }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const apiPath = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}`;
  const pagePath = `/releases/application/${encodeURIComponent(releaseId)}`;
  const [profile, decisionResponse, downstream] = await Promise.all([
    apiGet<Profile>(apiPath),
    apiGet<DecisionResponse>(`${apiPath}/decision`),
    apiGet<Downstream>(`${apiPath}/downstream`),
  ]);
  if (!profile) return <section className="panel"><h1>Software passport unavailable</h1><p className="muted">The application release was not found or the API could not be reached.</p><Link href="/releases/application">Back to releases →</Link></section>;

  const decision = decisionResponse?.decision;
  const formallyReleased = decision?.decision === 'RELEASE' && decision.is_current_snapshot;
  const lifecycle = formallyReleased ? 'FORMALLY RELEASED' : decision?.decision === 'RELEASE' ? 'HISTORICAL RELEASE' : 'NOT RELEASED';
  const deliveryRows = downstream?.deliveries.filter(row => !decision?.snapshot_no || row.snapshot_no === decision.snapshot_no) || [];

  return <>
    <div className="top"><div><div className="eyebrow">SOFTWARE PASSPORT</div><h1>ASR {profile.version}</h1><p className="muted">Exact release identity · {profile.id}</p></div><span className={'status ' + (formallyReleased ? 'pass' : 'warning')}>{lifecycle}</span></div>
    <div className="cards">
      <div className="card"><span className="muted">CURRENT SNAPSHOT</span><div className="metric">{profile.snapshot?.snapshot_no || '—'}</div><small>{profile.snapshot?.status || 'No snapshot'}</small></div>
      <div className="card"><span className="muted">RELEASE DECISION</span><div className="metric">{decision?.decision || '—'}</div><small>{decision?.decision_no || 'No formal decision'}</small></div>
      <div className="card"><span className="muted">APPROVAL</span><div className="metric">{decision?.approval_status || '—'}</div><small>{decision?.approval_no || 'No linked approval'}</small></div>
      <div className="card"><span className="muted">DELIVERIES</span><div className="metric">{deliveryRows.length}</div><small>For decision snapshot</small></div>
    </div>
    <div className="grid2">
      <section className="panel"><h2>Release identity</h2><div className="kv">
        <span>Software</span><b>{profile.software ? `${profile.software.name} · ${profile.software.code}` : '—'}</b>
        <span>Customer</span><b>{profile.customer?.name || '—'}</b>
        <span>Project</span><b>{profile.project ? `${profile.project.name} · ${profile.project.code}` : '—'}</b>
        <span>Standard Base</span><b>{profile.base_release ? `SSR ${profile.base_release.version}` : '—'}</b>
        <span>Release status</span><b>{profile.status}</b>
        <span>Snapshot hash</span><code style={{overflowWrap: 'anywhere'}}>{profile.snapshot?.content_hash || '—'}</code>
      </div></section>
      <section className="panel"><h2>Formal release decision</h2>{decision ? <div className="kv">
        <span>Decision</span><b>{decision.decision_no} · {decision.decision}</b>
        <span>Decision snapshot</span><b>{decision.snapshot_no || '—'}{decision.is_current_snapshot ? ' · CURRENT' : ' · NOT CURRENT'}</b>
        <span>Readiness</span><b>{decision.readiness_status}</b>
        <span>Approval</span><b>{decision.approval_no || '—'} · {decision.approval_status || 'Unknown'}</b>
        <span>Decided by</span><b>{decision.decided_by}</b>
        <span>Decided at</span><b>{decision.decided_at.slice(0, 16).replace('T', ' ')}</b>
        <span>Notes</span><b>{decision.decision_notes || '—'}</b>
      </div> : <p className="muted">No formal release decision is recorded for this exact application release.</p>}
      {decision && !decision.is_current_snapshot && <p className="muted">The recorded decision belongs to an older snapshot. The current snapshot is not presented as formally released.</p>}</section>
    </div>
    <section className="panel tablewrap"><h2>Authorized outbound chain</h2><p className="muted">Only recorded downstream objects are shown; this passport does not infer approval or authorization.</p>
      <table><thead><tr><th>Stage</th><th>Record</th><th>Context</th><th>Snapshot</th><th>Status</th></tr></thead><tbody>
        {deliveryRows.map(row => <tr key={row.id}><td>Delivery</td><td><Link href={`/distribution/deliveries/${encodeURIComponent(row.package_no)}/${row.revision}`}><b>{row.package_no} Rev{row.revision}</b></Link></td><td>{row.recipient_code}</td><td>{row.snapshot_no || '—'}</td><td>{row.status}</td></tr>)}
        {(downstream?.distributions || []).map(row => <tr key={row.id}><td>Distribution</td><td><Link href={`/distribution/distributions/${encodeURIComponent(row.distribution_no)}`}><b>{row.distribution_no}</b></Link></td><td>{row.package_no} Rev{row.package_revision} · {row.recipient_code}</td><td>—</td><td>{row.status}</td></tr>)}
        {(downstream?.authorizations || []).map(row => <tr key={row.id}><td>Authorization</td><td><Link href={`/distribution/authorizations/${encodeURIComponent(row.authorization_no)}`}><b>{row.authorization_no}</b></Link></td><td>{row.distribution_no || 'No distribution'} · {row.site_code}/{row.line_code}</td><td>{row.snapshot_no || '—'}</td><td>{row.status}</td></tr>)}
      </tbody></table>{!deliveryRows.length && !downstream?.distributions.length && !downstream?.authorizations.length && <p className="muted">No outbound records linked to this release.</p>}
    </section>
    <p className="datasource"><Link href={pagePath}>← Release profile</Link></p>
  </>;
}
