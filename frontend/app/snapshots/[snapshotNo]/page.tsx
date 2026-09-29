import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Snapshot = {
  id: string; snapshot_no: string; snapshot_number: number; status: string;
  content_hash: string; created_at: string; is_current_snapshot: boolean;
  release: { id: string; type: string; version: string } | null;
  artifacts: {
    id: string; filename: string; artifact_type: string; component_code: string;
    component_version: string | null; sha256: string; classification: string;
    distribution_level: string; ai_access_policy: string;
    policy_rules: { recipient_type: string; purpose: string; recipient_code: string | null; decision: string }[];
  }[];
};

export default async function Page({ params }: { params: Promise<{ snapshotNo: string }> }) {
  const { snapshotNo } = await params;
  const snapshot = await apiGet<Snapshot>(`/api/v1/snapshots/${encodeURIComponent(snapshotNo)}`);
  if (!snapshot) return <section className="panel"><h1>Snapshot unavailable</h1><p className="muted">The exact snapshot was not found or the API could not be reached. No substitute snapshot is shown.</p><Link href="/search">Search records →</Link></section>;
  const releasePath = snapshot.release ? `/releases/${snapshot.release.type === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(snapshot.release.id)}` : null;
  return <>
    <div className="top"><div><div className="eyebrow">EXACT FROZEN SNAPSHOT</div><h1>{snapshot.snapshot_no}</h1><p className="muted">Snapshot #{snapshot.snapshot_number} · {snapshot.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</p></div><span className="status">{snapshot.status}</span></div>
    <section className="panel"><h2>Snapshot identity</h2><div className="kv">
      <span>Release</span><b>{snapshot.release && releasePath ? <Link href={releasePath}>{snapshot.release.type} {snapshot.release.version}</Link> : 'Release unavailable'}</b>
      <span>Frozen at</span><b>{snapshot.created_at.slice(0, 16).replace('T', ' ')} UTC</b>
      <span>Content hash</span><code style={{overflowWrap: 'anywhere'}}>{snapshot.content_hash}</code>
    </div><p className="muted">This page shows only this snapshot’s frozen files and recipient rules. Current release status does not establish approval of this snapshot.</p>
      {!snapshot.is_current_snapshot && <p className="muted">A newer snapshot exists. These historical records are not replaced by the current manifest.</p>}
    </section>
    <section className="panel tablewrap"><h2>Frozen manifest · {snapshot.artifacts.length} files</h2><table><thead><tr><th>File / component</th><th>Full SHA-256</th><th>Classification / distribution</th><th>AI policy</th><th>Frozen recipient rules</th></tr></thead><tbody>
      {snapshot.artifacts.map(row => <tr key={row.id} id={`artifact-${row.id}`}>
        <td><b>{row.filename}</b><div className="muted">{row.artifact_type} · {row.component_code} {row.component_version || ''}</div></td>
        <td><code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 240}}>{row.sha256}</code></td>
        <td>{row.classification}<div>{row.distribution_level}</div></td><td>{row.ai_access_policy}</td>
        <td>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.policy_rules.length ? row.policy_rules.map((rule, index) => <div key={index}>{rule.recipient_type} {rule.recipient_code || ''} · {rule.purpose} · {rule.decision}</div>) : 'No frozen rule recorded'}</td>
      </tr>)}
    </tbody></table>{snapshot.artifacts.length === 0 && <p className="muted">No frozen artifacts recorded for this snapshot.</p>}</section>
    {releasePath && <p><Link href={releasePath}>← Release profile</Link></p>}
  </>;
}
