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
  if (!policy) return <section className="panel"><h1>Snapshot policy unavailable</h1>
    <p className="muted">The application release was not found or the API could not be reached.</p>
    <Link href={base}>← Release profile</Link></section>;
  const artifacts = policy.artifacts;
  const shaComplete = artifacts.filter(row => Boolean(row.sha256)).length;
  const policyComplete = artifacts.filter(row => row.distribution_level === 'INTERNAL_ONLY' || row.policy_rules.length > 0).length;
  return <>
    <div className="top"><div><div className="eyebrow">FROZEN ARTIFACT POLICY</div><h1>{policy.snapshot?.snapshot_no || 'No snapshot'}</h1>
      <p className="muted">Files and recipient rules captured with this application release snapshot.</p></div>
      {policy.snapshot && <span className="status pass">{policy.snapshot.status}</span>}</div>
    {policy.snapshot ? <>
      <div className="cards">
        <div className="card"><span className="muted">FROZEN FILES</span><div className="metric">{artifacts.length}</div></div>
        <div className="card"><span className="muted">SHA RECORDED</span><div className="metric">{shaComplete} / {artifacts.length}</div></div>
        <div className="card"><span className="muted">POLICY RECORDED</span><div className="metric">{policyComplete} / {artifacts.length}</div></div>
      </div>
      <section className="panel"><h2>Snapshot content hash</h2><code className="hash">{policy.snapshot.content_hash}</code></section>
      <section className="panel tablewrap"><h2>Frozen artifact manifest</h2>
        <p className="muted">An internal-only file cannot be distributed externally. A recorded ALLOW or APPROVAL_REQUIRED rule applies only to its named recipient and purpose; it is not a general permission.</p>
        <table><thead><tr><th>File</th><th>Component</th><th>SHA-256</th><th>Classification</th><th>Distribution</th><th>AI Policy</th><th>Recipient Rules</th></tr></thead>
          <tbody>{artifacts.map(row => <tr key={row.id}><td><b>{row.filename}</b><br />{row.artifact_type}</td>
            <td>{row.component_code}{row.component_version ? ` · ${row.component_version}` : ''}</td>
            <td><code>{row.sha256 ? `${row.sha256.slice(0, 12)}…` : 'Missing'}</code></td>
            <td>{row.classification}</td>
            <td><span className={'status ' + (row.distribution_level === 'INTERNAL_ONLY' ? '' : 'warning')}>{row.distribution_level}</span></td>
            <td>{row.ai_access_policy}</td>
            <td>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.policy_rules.length ? row.policy_rules.map((rule, index) =>
              <span key={`${rule.recipient_type}-${rule.purpose}-${rule.recipient_code || ''}`}>{index > 0 ? '; ' : ''}{rule.recipient_type}{rule.recipient_code ? ` ${rule.recipient_code}` : ''} · {rule.purpose} · {rule.decision}</span>
            ) : 'No rule recorded'}</td>
          </tr>)}</tbody></table>
        {artifacts.length === 0 && <p className="muted">No frozen artifacts recorded.</p>}
      </section>
    </> : <section className="panel"><p className="muted">No snapshot has been recorded for this application release.</p></section>}
    <p className="datasource"><Link href={base}>← Release profile</Link></p>
  </>;
}
