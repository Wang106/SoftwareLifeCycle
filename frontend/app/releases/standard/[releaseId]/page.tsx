import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  supplier: { code: string; name: string } | null;
  previous_release: { id: string; version: string } | null;
  source: { branch: string | null; commit: string | null } | null;
  components: { id: string; code: string | null; name: string | null; version: string | null }[];
  applications: { id: string; version: string; status: string }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const profile = await apiGet<Profile>(`/api/v1/releases/standard/id/${encodeURIComponent(releaseId)}`);
  if (!profile) return <section className="panel"><h1>Standard release unavailable</h1><p className="muted">The release was not found or the API could not be reached.</p><Link href="/releases/standard">Back to standard releases →</Link></section>;
  return <>
    <p><Link href={`/approvals?release_id=${profile.id}`}>Approval history →</Link> · <Link href={`/release-decisions?release_id=${profile.id}`}>Release decision history →</Link></p>
    <p><Link href={`/deployments?release_id=${profile.id}`}>Deployment history →</Link> · <Link href={`/production/batches?release_id=${profile.id}`}>Batch history →</Link></p>
    <p><Link href={`/distribution/deliveries?release_id=${profile.id}`}>Delivery history →</Link> · <Link href={`/distribution/distributions?release_id=${profile.id}`}>Distribution history →</Link> · <Link href={`/distribution/authorizations?release_id=${profile.id}`}>Production authorizations →</Link></p>
    <p><Link href={`/resources?entity_type=RELEASE&entity_id=${profile.id}`}>Materials & evidence references →</Link></p>
    <div className="top"><div><div className="eyebrow">STANDARD SOFTWARE RELEASE</div><h1>SSR {profile.version}</h1><p className="muted">{profile.software?.name || 'Software unavailable'} · {profile.software?.code || 'No code'}</p></div><span className={'status ' + (profile.status === 'READY' || profile.status === 'RELEASED' ? 'pass' : 'warning')}>{profile.status}</span></div>
    <div className="grid2"><section className="panel"><h2>Baseline identity</h2><div className="kv">
      <span>Supplier</span><b>{profile.supplier ? <Link href={`/suppliers/${encodeURIComponent(profile.supplier.code)}`}>{profile.supplier.name}</Link> : '—'}</b>
      <span>Previous SSR</span><b>{profile.previous_release ? <Link href={`/releases/standard/${encodeURIComponent(profile.previous_release.id)}`}>SSR {profile.previous_release.version}</Link> : '—'}</b>
      <span>Source branch</span><b>{profile.source?.branch || '—'}</b>
      <span>Source commit</span><code>{profile.source?.commit || '—'}</code>
    </div></section><section className="panel"><h2>Release notes</h2><p>{profile.release_notes || 'No release notes recorded.'}</p></section></div>
    <p><Link href={`/releases/${encodeURIComponent(profile.id)}/snapshots`}>View snapshot history →</Link></p>
    <section className="panel tablewrap"><h2>Recorded components</h2><table><thead><tr><th>Component</th><th>Version</th></tr></thead><tbody>{profile.components.map(row => <tr key={row.id}><td><b>{row.name || row.code || 'Unknown component'}</b><div className="muted">{row.code || 'No code'}</div></td><td>{row.version || '—'}</td></tr>)}</tbody></table>{profile.components.length === 0 && <p className="muted">No components recorded.</p>}</section>
    <section className="panel tablewrap"><h2>Application releases using this baseline</h2><table><thead><tr><th>Release</th><th>Status</th></tr></thead><tbody>{profile.applications.map(row => <tr key={row.id}><td><Link href={`/releases/application/${encodeURIComponent(row.id)}`}>ASR {row.version}</Link></td><td>{row.status}</td></tr>)}</tbody></table>{profile.applications.length === 0 && <p className="muted">No application releases linked to this SSR.</p>}</section>
    <p className="datasource"><Link href="/releases/standard">← All standard releases</Link></p>
  </>;
}
