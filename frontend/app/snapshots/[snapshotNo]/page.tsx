
import { Localized, LocalizedAttributes } from "../../../components/localized";
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
  if (!snapshot) return <section className="panel"><h1><Localized>{"Snapshot unavailable"}</Localized></h1><p className="muted"><Localized>{"The exact snapshot was not found or the API could not be reached. No substitute snapshot is shown."}</Localized></p><Link href="/search"><Localized>{"Search records →"}</Localized></Link></section>;
  const releasePath = snapshot.release ? `/releases/${snapshot.release.type === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(snapshot.release.id)}` : null;
  return <>
    <p><Link href={`/resources?entity_type=SNAPSHOT&entity_id=${snapshot.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{"EXACT FROZEN SNAPSHOT"}</Localized></div><h1><Localized>{snapshot.snapshot_no}</Localized></h1><p className="muted"><Localized>{"Snapshot #"}</Localized><Localized>{snapshot.snapshot_number}</Localized><Localized>{" · "}</Localized><Localized>{snapshot.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</Localized></p></div><span className="status"><Localized>{snapshot.status}</Localized></span></div>
    <section className="panel"><h2><Localized>{"Snapshot identity"}</Localized></h2><div className="kv">
      <span><Localized>{"Snapshot UUID"}</Localized></span><b><Localized>{snapshot.id}</Localized></b>
      <span><Localized>{"Release UUID"}</Localized></span><b><Localized>{snapshot.release?.id || 'Unavailable'}</Localized></b>
      <span><Localized>{"Release"}</Localized></span><b><Localized>{snapshot.release && releasePath ? <Link href={releasePath}><Localized>{snapshot.release.type}</Localized> <Localized>{snapshot.release.version}</Localized></Link> : 'Release unavailable'}</Localized></b>
      <span><Localized>{"Frozen at"}</Localized></span><b><Localized>{snapshot.created_at.slice(0, 16).replace('T', ' ')}</Localized><Localized>{" UTC"}</Localized></b>
      <span><Localized>{"Content hash"}</Localized></span><code style={{overflowWrap: 'anywhere'}}>{snapshot.content_hash}</code>
    </div><p className="muted"><Localized>{"This page shows only this snapshot’s frozen files and recipient rules. Current release status does not establish approval of this snapshot."}</Localized></p>
      <Localized>{!snapshot.is_current_snapshot && <p className="muted"><Localized>{"A newer snapshot exists. These historical records are not replaced by the current manifest."}</Localized></p>}</Localized>
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Frozen manifest · "}</Localized><Localized>{snapshot.artifacts.length}</Localized><Localized>{" files"}</Localized></h2><table><thead><tr><th><Localized>{"File / component"}</Localized></th><th><Localized>{"Full SHA-256"}</Localized></th><th><Localized>{"Classification / distribution"}</Localized></th><th><Localized>{"AI policy"}</Localized></th><th><Localized>{"Frozen recipient rules"}</Localized></th></tr></thead><tbody>
      <Localized>{snapshot.artifacts.map(row => <tr key={row.id} id={`artifact-${row.id}`}>
        <td><b><Localized>{row.filename}</Localized></b><div className="muted"><Localized>{"Snapshot artifact UUID: "}</Localized><Localized>{row.id}</Localized></div><div className="muted"><Localized>{row.artifact_type}</Localized><Localized>{" · "}</Localized><Localized>{row.component_code}</Localized> <Localized>{row.component_version || ''}</Localized></div></td>
        <td><code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 240}}>{row.sha256}</code></td>
        <td><Localized>{row.classification}</Localized><div><Localized>{row.distribution_level}</Localized></div></td><td><Localized>{row.ai_access_policy}</Localized></td>
        <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.policy_rules.length ? row.policy_rules.map((rule, index) => <div key={index}><Localized>{rule.recipient_type}</Localized> <Localized>{rule.recipient_code || ''}</Localized><Localized>{" · "}</Localized><Localized>{rule.purpose}</Localized><Localized>{" · "}</Localized><Localized>{rule.decision}</Localized></div>) : 'No frozen rule recorded'}</Localized></td>
      </tr>)}</Localized>
    </tbody></table><Localized>{snapshot.artifacts.length === 0 && <p className="muted"><Localized>{"No frozen artifacts recorded for this snapshot."}</Localized></p>}</Localized></section>
    <p><Link href={`/snapshots/${encodeURIComponent(snapshot.snapshot_no)}/compare`}><Localized>{"Compare frozen files and policies →"}</Localized></Link></p>
    <Localized>{snapshot.release && <p><Link href={`/commands?${new URLSearchParams({operation: 'test-release', target: snapshot.release.id, snapshot: snapshot.id})}`}><Localized>{"Prepare test draft for this exact snapshot →"}</Localized></Link></p>}</Localized>
    <Localized>{snapshot.release && <p><Link href={`/commands?${new URLSearchParams({operation: 'delivery', target: snapshot.release.id})}`}><Localized>{"Prepare delivery for this release →"}</Localized></Link><Localized>{" · Review the latest approved RELEASE decision first; this snapshot is not automatically selected."}</Localized></p>}</Localized>
    <Localized>{snapshot.release && <p><Link href={`/releases/${encodeURIComponent(snapshot.release.id)}/snapshots`}><Localized>{"View snapshot history →"}</Localized></Link></p>}</Localized>
    <Localized>{releasePath && <p><Link href={releasePath}><Localized>{"← Release profile"}</Localized></Link></p>}</Localized>
  </>;
}
