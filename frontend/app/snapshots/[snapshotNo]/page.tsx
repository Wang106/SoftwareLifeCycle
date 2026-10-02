
import { Localized } from "../../../components/localized";
import { SnapshotManifest } from '../../../components/snapshot-manifest';
import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Snapshot = {
  id: string; snapshot_no: string; snapshot_number: number; status: string;
  content_hash: string; created_at: string; is_current_snapshot: boolean;
  release: { id: string; type: string; version: string } | null;
  release_id: string; artifact_count: number; rule_count: number;
};

export default async function Page({ params, searchParams }: { params: Promise<{ snapshotNo: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { snapshotNo } = await params;
  const search = await searchParams;
  const snapshot = await apiGet<Snapshot>(`/api/v1/snapshots/${encodeURIComponent(snapshotNo)}/summary`);
  if (!snapshot || snapshot.snapshot_no !== snapshotNo || (search.manifest_snapshot_id !== undefined && search.manifest_snapshot_id !== snapshot.id)) return <section className="panel"><h1><Localized>{"Snapshot unavailable"}</Localized></h1><p className="muted"><Localized>{"The exact snapshot was not found or the API could not be reached. No substitute snapshot is shown."}</Localized></p><Link href="/search"><Localized>{"Search records →"}</Localized></Link></section>;
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
    <SnapshotManifest snapshot={snapshot} search={search} />
    <p><Link href={`/snapshots/${encodeURIComponent(snapshot.snapshot_no)}/compare`}><Localized>{"Compare frozen files and policies →"}</Localized></Link></p>
    <Localized>{snapshot.release && <p><Link href={`/commands?${new URLSearchParams({operation: 'test-release', target: snapshot.release.id, snapshot: snapshot.id})}`}><Localized>{"Prepare test draft for this exact snapshot →"}</Localized></Link></p>}</Localized>
    <Localized>{snapshot.release && <p><Link href={`/commands?${new URLSearchParams({operation: 'delivery', target: snapshot.release.id})}`}><Localized>{"Prepare delivery for this release →"}</Localized></Link><Localized>{" · Review the latest approved RELEASE decision first; this snapshot is not automatically selected."}</Localized></p>}</Localized>
    <Localized>{snapshot.release && <p><Link href={`/releases/${encodeURIComponent(snapshot.release.id)}/snapshots`}><Localized>{"View snapshot history →"}</Localized></Link></p>}</Localized>
    <Localized>{releasePath && <p><Link href={releasePath}><Localized>{"← Release profile"}</Localized></Link></p>}</Localized>
  </>;
}
