
import { Localized, LocalizedAttributes } from "../../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  base_release: { id: string; version: string; status: string } | null;
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
type DecisionHistory = {
  release_id: string; current_snapshot_no: string | null;
  decisions: {
    decision_no: string; decision: string; readiness_status: string;
    decided_by: string; decision_notes: string | null; decided_at: string;
    snapshot_id: string; snapshot_no: string | null; snapshot_content_hash: string | null;
    is_current_snapshot: boolean; approval_no: string | null; approval_status: string | null;
  }[];
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
  const [profile, decisionResponse, decisionHistory, downstream] = await Promise.all([
    apiGet<Profile>(apiPath),
    apiGet<DecisionResponse>(`${apiPath}/decision`),
    apiGet<DecisionHistory>(`${apiPath}/decisions`),
    apiGet<Downstream>(`${apiPath}/downstream`),
  ]);
  if (!profile) return <section className="panel"><h1><Localized>{"Software passport unavailable"}</Localized></h1><p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p><Link href="/releases/application"><Localized>{"Back to releases →"}</Localized></Link></section>;

  const decision = decisionResponse?.decision;
  const formallyReleased = decision?.decision === 'RELEASE' && decision.is_current_snapshot;
  const lifecycle = formallyReleased ? 'FORMALLY RELEASED' : decision?.decision === 'RELEASE' ? 'HISTORICAL RELEASE' : 'NOT RELEASED';
  const deliveryRows = downstream?.deliveries.filter(row => !decision?.snapshot_no || row.snapshot_no === decision.snapshot_no) || [];

  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"SOFTWARE PASSPORT"}</Localized></div><h1><Localized>{"ASR "}</Localized><Localized>{profile.version}</Localized></h1><p className="muted"><Localized>{"Exact release identity · "}</Localized><Localized>{profile.id}</Localized></p></div><span className={'status ' + (formallyReleased ? 'pass' : 'warning')}><Localized>{lifecycle}</Localized></span></div>
    <div className="cards">
      <div className="card"><span className="muted"><Localized>{"CURRENT SNAPSHOT"}</Localized></span><div className="metric"><Localized>{profile.snapshot?.snapshot_no || '—'}</Localized></div><small><Localized>{profile.snapshot?.status || 'No snapshot'}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"RELEASE DECISION"}</Localized></span><div className="metric"><Localized>{decision?.decision || '—'}</Localized></div><small><Localized>{decision?.decision_no || 'No formal decision'}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"APPROVAL"}</Localized></span><div className="metric"><Localized>{decision?.approval_status || '—'}</Localized></div><small><Localized>{decision?.approval_no || 'No linked approval'}</Localized></small></div>
      <div className="card"><span className="muted"><Localized>{"DELIVERIES"}</Localized></span><div className="metric"><Localized>{deliveryRows.length}</Localized></div><small><Localized>{"For decision snapshot"}</Localized></small></div>
    </div>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Release identity"}</Localized></h2><div className="kv">
        <span><Localized>{"Software"}</Localized></span><b><Localized>{profile.software ? `${profile.software.name} · ${profile.software.code}` : '—'}</Localized></b>
        <span><Localized>{"Customer"}</Localized></span><b><Localized>{profile.customer?.name || '—'}</Localized></b>
        <span><Localized>{"Project"}</Localized></span><b><Localized>{profile.project ? `${profile.project.name} · ${profile.project.code}` : '—'}</Localized></b>
        <span><Localized>{"Standard Base"}</Localized></span><b><Localized>{profile.base_release ? <Link href={`/releases/standard/${encodeURIComponent(profile.base_release.id)}`}><Localized>{"SSR "}</Localized><Localized>{profile.base_release.version}</Localized></Link> : '—'}</Localized></b>
        <span><Localized>{"Release status"}</Localized></span><b><Localized>{profile.status}</Localized></b>
        <span><Localized>{"Snapshot hash"}</Localized></span><code style={{overflowWrap: 'anywhere'}}>{profile.snapshot?.content_hash || '—'}</code>
      </div></section>
      <section className="panel"><h2><Localized>{"Formal release decision"}</Localized></h2><Localized>{decision ? <div className="kv">
        <span><Localized>{"Decision"}</Localized></span><b><Localized>{decision.decision_no}</Localized><Localized>{" · "}</Localized><Localized>{decision.decision}</Localized></b>
        <span><Localized>{"Decision snapshot"}</Localized></span><b><Localized>{decision.snapshot_no || '—'}</Localized><Localized>{decision.is_current_snapshot ? ' · CURRENT' : ' · NOT CURRENT'}</Localized></b>
        <span><Localized>{"Readiness"}</Localized></span><b><Localized>{decision.readiness_status}</Localized></b>
        <span><Localized>{"Approval"}</Localized></span><b><Localized>{decision.approval_no || '—'}</Localized><Localized>{" · "}</Localized><Localized>{decision.approval_status || 'Unknown'}</Localized></b>
        <span><Localized>{"Decided by"}</Localized></span><b><Localized>{decision.decided_by}</Localized></b>
        <span><Localized>{"Decided at"}</Localized></span><b><Localized>{decision.decided_at.slice(0, 16).replace('T', ' ')}</Localized></b>
        <span><Localized>{"Notes"}</Localized></span><b><Localized>{decision.decision_notes || '—'}</Localized></b>
      </div> : <p className="muted"><Localized>{"No formal release decision is recorded for this exact application release."}</Localized></p>}</Localized>
      <Localized>{decision && !decision.is_current_snapshot && <p className="muted"><Localized>{"The recorded decision belongs to an older snapshot. The current snapshot is not presented as formally released."}</Localized></p>}</Localized></section>
    </div>
    <section className="panel tablewrap"><h2><Localized>{"Formal decision history"}</Localized></h2>
      <p className="muted"><Localized>{"Every recorded decision remains visible with its frozen snapshot and approval. A historical decision does not release the current snapshot."}</Localized></p>
      <Localized>{decisionHistory ? <><table><thead><tr><th><Localized>{"Decision"}</Localized></th><th><Localized>{"Snapshot / hash"}</Localized></th><th><Localized>{"Readiness"}</Localized></th><th><Localized>{"Approval"}</Localized></th><th><Localized>{"Decided by / at"}</Localized></th><th><Localized>{"Notes"}</Localized></th></tr></thead><tbody>
        <Localized>{decisionHistory.decisions.map(row => <tr key={row.decision_no}>
          <td><b><Localized>{row.decision_no}</Localized></b><div><span className={'status ' + (row.decision === 'RELEASE' && row.is_current_snapshot ? 'pass' : 'warning')}><Localized>{row.decision}</Localized></span></div></td>
          <td><Localized>{row.snapshot_no || '—'}</Localized><Localized>{" · "}</Localized><Localized>{row.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</Localized><div className="muted"><code>{row.snapshot_content_hash ? `${row.snapshot_content_hash.slice(0, 16)}…` : 'Hash unavailable'}</code></div></td>
          <td><Localized>{row.readiness_status}</Localized></td>
          <td><Localized>{row.approval_no ? <Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}><Localized>{row.approval_no}</Localized></Link> : '—'}</Localized><div className="muted"><Localized>{row.approval_status || 'Unknown'}</Localized></div></td>
          <td><Localized>{row.decided_by}</Localized><div className="muted"><Localized>{row.decided_at.slice(0, 16).replace('T', ' ')}</Localized><Localized>{" UTC"}</Localized></div></td>
          <td><Localized>{row.decision_notes || '—'}</Localized></td>
        </tr>)}</Localized></tbody></table><Localized>{decisionHistory.decisions.length === 0 && <p className="muted"><Localized>{"No formal decisions recorded."}</Localized></p>}</Localized></> : <p className="muted"><Localized>{"Decision history API unavailable."}</Localized></p>}</Localized>
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Authorized outbound chain"}</Localized></h2><p className="muted"><Localized>{"Only recorded downstream objects are shown; this passport does not infer approval or authorization."}</Localized></p>
      <table><thead><tr><th><Localized>{"Stage"}</Localized></th><th><Localized>{"Record"}</Localized></th><th><Localized>{"Context"}</Localized></th><th><Localized>{"Snapshot"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody>
        <Localized>{deliveryRows.map(row => <tr key={row.id}><td><Localized>{"Delivery"}</Localized></td><td><Link href={`/distribution/deliveries/${encodeURIComponent(row.package_no)}/${row.revision}`}><b><Localized>{row.package_no}</Localized><Localized>{" Rev"}</Localized><Localized>{row.revision}</Localized></b></Link></td><td><Localized>{row.recipient_code}</Localized></td><td><Localized>{row.snapshot_no || '—'}</Localized></td><td><Localized>{row.status}</Localized></td></tr>)}</Localized>
        <Localized>{(downstream?.distributions || []).map(row => <tr key={row.id}><td><Localized>{"Distribution"}</Localized></td><td><Link href={`/distribution/distributions/${encodeURIComponent(row.distribution_no)}`}><b><Localized>{row.distribution_no}</Localized></b></Link></td><td><Localized>{row.package_no}</Localized><Localized>{" Rev"}</Localized><Localized>{row.package_revision}</Localized><Localized>{" · "}</Localized><Localized>{row.recipient_code}</Localized></td><td><Localized>{"—"}</Localized></td><td><Localized>{row.status}</Localized></td></tr>)}</Localized>
        <Localized>{(downstream?.authorizations || []).map(row => <tr key={row.id}><td><Localized>{"Authorization"}</Localized></td><td><Link href={`/distribution/authorizations/${encodeURIComponent(row.authorization_no)}`}><b><Localized>{row.authorization_no}</Localized></b></Link></td><td><Localized>{row.distribution_no || 'No distribution'}</Localized><Localized>{" · "}</Localized><Localized>{row.site_code}</Localized><Localized>{"/"}</Localized><Localized>{row.line_code}</Localized></td><td><Localized>{row.snapshot_no || '—'}</Localized></td><td><Localized>{row.status}</Localized></td></tr>)}</Localized>
      </tbody></table><Localized>{!deliveryRows.length && !downstream?.distributions.length && !downstream?.authorizations.length && <p className="muted"><Localized>{"No outbound records linked to this release."}</Localized></p>}</Localized>
    </section>
    <p className="datasource"><Link href={pagePath}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
