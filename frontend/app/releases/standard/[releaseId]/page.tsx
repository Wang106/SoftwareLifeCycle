
import { Localized } from "../../../../components/localized";
import Link from 'next/link';
import { StandardReleaseCollections } from '../../../../components/standard-release-collections';
import { apiGet } from '../../../../lib/api';

type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  supplier: { code: string; name: string } | null;
  previous_release: { id: string; version: string } | null;
  source: { branch: string | null; commit: string | null } | null;
  component_count: number; application_count: number;
};

export default async function Page({ params, searchParams }: { params: Promise<{ releaseId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [{ releaseId }, search] = await Promise.all([params, searchParams]);
  const profile = await apiGet<Profile>(`/api/v1/releases/standard/id/${encodeURIComponent(releaseId)}/summary`);
  if (!profile || profile.id !== releaseId) return <section className="panel"><h1><Localized>{"Standard release unavailable"}</Localized></h1><p className="muted"><Localized>{"The release was not found or the API could not be reached."}</Localized></p><Link href="/releases/standard"><Localized>{"Back to standard releases →"}</Localized></Link></section>;
  return <>
    <p><Link href={`/commands?${new URLSearchParams({operation: "snapshot", target: profile.id})}`}><Localized>{"Prepare Snapshot request →"}</Localized></Link></p>
    <p><Link href={`/approvals?release_id=${profile.id}`}><Localized>{"Approval history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/release-decisions?release_id=${profile.id}`}><Localized>{"Release decision history →"}</Localized></Link></p>
    <p><Link href={`/deployments?release_id=${profile.id}`}><Localized>{"Deployment history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/production/batches?release_id=${profile.id}`}><Localized>{"Batch history →"}</Localized></Link></p>
    <p><Link href={`/distribution/deliveries?release_id=${profile.id}`}><Localized>{"Delivery history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/distribution/distributions?release_id=${profile.id}`}><Localized>{"Distribution history →"}</Localized></Link><Localized>{" · "}</Localized><Link href={`/distribution/authorizations?release_id=${profile.id}`}><Localized>{"Production authorizations →"}</Localized></Link></p>
    <p><Link href={`/resources?entity_type=RELEASE&entity_id=${profile.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{"STANDARD SOFTWARE RELEASE"}</Localized></div><h1><Localized>{"SSR "}</Localized><Localized>{profile.version}</Localized></h1><p className="muted"><Localized>{profile.software?.name || 'Software unavailable'}</Localized><Localized>{" · "}</Localized><Localized>{profile.software?.code || 'No code'}</Localized></p></div><span className={'status ' + (profile.status === 'READY' || profile.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{profile.status}</Localized></span></div>
    <div className="grid2"><section className="panel"><h2><Localized>{"Baseline identity"}</Localized></h2><div className="kv">
      <span><Localized>{"Supplier"}</Localized></span><b><Localized>{profile.supplier ? <Link href={`/suppliers/${encodeURIComponent(profile.supplier.code)}`}><Localized>{profile.supplier.name}</Localized></Link> : '—'}</Localized></b>
      <span><Localized>{"Previous SSR"}</Localized></span><b><Localized>{profile.previous_release ? <Link href={`/releases/standard/${encodeURIComponent(profile.previous_release.id)}`}><Localized>{"SSR "}</Localized><Localized>{profile.previous_release.version}</Localized></Link> : '—'}</Localized></b>
      <span><Localized>{"Source branch"}</Localized></span><b><Localized>{profile.source?.branch || '—'}</Localized></b>
      <span><Localized>{"Source commit"}</Localized></span><code>{profile.source?.commit || '—'}</code>
    </div></section><section className="panel"><h2><Localized>{"Release notes"}</Localized></h2><p><Localized>{profile.release_notes || 'No release notes recorded.'}</Localized></p></section></div>
    <p><Link href={`/releases/${encodeURIComponent(profile.id)}/snapshots`}><Localized>{"View snapshot history →"}</Localized></Link></p>
    <StandardReleaseCollections releaseId={profile.id} search={search} componentCount={profile.component_count} applicationCount={profile.application_count} />
    <p className="datasource"><Link href="/releases/standard"><Localized>{"← All standard releases"}</Localized></Link></p>
  </>;
}
