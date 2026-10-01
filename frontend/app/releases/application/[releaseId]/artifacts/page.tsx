
import { Localized, LocalizedAttributes } from "../../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type ArtifactPolicy = {
  snapshot: { snapshot_no: string; status: string; content_hash: string } | null;
  artifacts: {
    id: string; component_code: string; component_version: string | null;
    filename: string; artifact_type: string; sha256: string; classification: string;
    distribution_level: string; ai_access_policy: string;
    policy_rules: { recipient_type: string; purpose: string; recipient_code: string | null; decision: string }[];
  }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const base = `/releases/application/${encodeURIComponent(releaseId)}`;
  const policy = await apiGet<ArtifactPolicy>(`/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/snapshot-policy`);
  if (!policy) return <section className="panel"><h1><Localized>{"Snapshot policy unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p>
    <Link href={base}><Localized>{"← Release profile"}</Localized></Link></section>;
  const artifacts = policy.artifacts;
  const shaComplete = artifacts.filter(row => Boolean(row.sha256)).length;
  const policyComplete = artifacts.filter(row => row.distribution_level === 'INTERNAL_ONLY' || row.policy_rules.length > 0).length;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"FROZEN ARTIFACT POLICY"}</Localized></div><h1><Localized>{policy.snapshot?.snapshot_no || 'No snapshot'}</Localized></h1>
      <p className="muted"><Localized>{"Files and recipient rules captured with this application release snapshot."}</Localized></p></div>
      <Localized>{policy.snapshot && <span className="status pass"><Localized>{policy.snapshot.status}</Localized></span>}</Localized></div>
    <Localized>{policy.snapshot ? <>
      <div className="cards">
        <div className="card"><span className="muted"><Localized>{"FROZEN FILES"}</Localized></span><div className="metric"><Localized>{artifacts.length}</Localized></div></div>
        <div className="card"><span className="muted"><Localized>{"SHA RECORDED"}</Localized></span><div className="metric"><Localized>{shaComplete}</Localized><Localized>{" / "}</Localized><Localized>{artifacts.length}</Localized></div></div>
        <div className="card"><span className="muted"><Localized>{"POLICY RECORDED"}</Localized></span><div className="metric"><Localized>{policyComplete}</Localized><Localized>{" / "}</Localized><Localized>{artifacts.length}</Localized></div></div>
      </div>
      <section className="panel"><h2><Localized>{"Snapshot content hash"}</Localized></h2><code className="hash">{policy.snapshot.content_hash}</code></section>
      <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest"}</Localized></h2>
        <p className="muted"><Localized>{"An internal-only file cannot be distributed externally. A recorded ALLOW or APPROVAL_REQUIRED rule applies only to its named recipient and purpose; it is not a general permission."}</Localized></p>
        <table><thead><tr><th><Localized>{"File"}</Localized></th><th><Localized>{"Component"}</Localized></th><th><Localized>{"SHA-256"}</Localized></th><th><Localized>{"Classification"}</Localized></th><th><Localized>{"Distribution"}</Localized></th><th><Localized>{"AI Policy"}</Localized></th><th><Localized>{"Recipient Rules"}</Localized></th></tr></thead>
          <tbody><Localized>{artifacts.map(row => <tr key={row.id}><td><b><Localized>{row.filename}</Localized></b><br /><Localized>{row.artifact_type}</Localized></td>
            <td><Localized>{row.component_code}</Localized><Localized>{row.component_version ? ` · ${row.component_version}` : ''}</Localized></td>
            <td><code>{row.sha256 ? `${row.sha256.slice(0, 12)}…` : 'Missing'}</code></td>
            <td><Localized>{row.classification}</Localized></td>
            <td><span className={'status ' + (row.distribution_level === 'INTERNAL_ONLY' ? '' : 'warning')}><Localized>{row.distribution_level}</Localized></span></td>
            <td><Localized>{row.ai_access_policy}</Localized></td>
            <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.policy_rules.length ? row.policy_rules.map((rule, index) =>
              <span key={`${rule.recipient_type}-${rule.purpose}-${rule.recipient_code || ''}`}><Localized>{index > 0 ? '; ' : ''}</Localized><Localized>{rule.recipient_type}</Localized><Localized>{rule.recipient_code ? ` ${rule.recipient_code}` : ''}</Localized><Localized>{" · "}</Localized><Localized>{rule.purpose}</Localized><Localized>{" · "}</Localized><Localized>{rule.decision}</Localized></span>
            ) : 'No rule recorded'}</Localized></td>
          </tr>)}</Localized></tbody></table>
        <Localized>{artifacts.length === 0 && <p className="muted"><Localized>{"No frozen artifacts recorded."}</Localized></p>}</Localized>
      </section>
    </> : <section className="panel"><p className="muted"><Localized>{"No snapshot has been recorded for this application release."}</Localized></p></section>}</Localized>
    <p className="datasource"><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
