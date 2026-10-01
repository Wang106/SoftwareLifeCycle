
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Project } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Project>(`/api/v1/organizations/projects/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1><Localized>{"Project unavailable"}</Localized></h1><p className="muted"><Localized>{"The project was not found or the API could not be reached."}</Localized></p><Link href="/projects"><Localized>{"Back to projects →"}</Localized></Link></section>;
  return <>
    <p><Link href={`/resources?entity_type=PROJECT&entity_id=${row.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p><div className="top"><div><div className="eyebrow"><Localized>{"PROJECT · "}</Localized><Localized>{row.code}</Localized></div><h1><Localized>{row.name}</Localized></h1><p className="muted"><Localized>{row.customer.name}</Localized><Localized>{" · "}</Localized><Localized>{row.vehicle_platform || 'Vehicle platform not specified'}</Localized></p></div><span className="status pass"><Localized>{row.status}</Localized></span></div>
      <p><Link href={`/releases/matrix?project_id=${encodeURIComponent(row.id)}`}><Localized>{"View project release history →"}</Localized></Link></p>
    <div className="grid2"><section className="panel"><h2><Localized>{"Project profile"}</Localized></h2><div className="kv"><span><Localized>{"Customer"}</Localized></span><Link href={`/customers/${encodeURIComponent(row.customer.code)}`}><b><Localized>{row.customer.name}</Localized></b></Link><span><Localized>{"Project Code"}</Localized></span><b><Localized>{row.code}</Localized></b><span><Localized>{"Vehicle Platform"}</Localized></span><b><Localized>{row.vehicle_platform || '—'}</Localized></b><span><Localized>{"Latest Application Release"}</Localized></span><b><Localized>{row.release ? <Link href={`/releases/application/${row.release.id}`}><Localized>{"ASR "}</Localized><Localized>{row.release.version}</Localized><Localized>{" · "}</Localized><Localized>{row.release.status}</Localized></Link> : '—'}</Localized></b></div></section>
    <section className="panel"><h2><Localized>{"Manufacturing sites"}</Localized></h2><Localized>{row.sites.length ? row.sites.map(site => <Link className="entityrow" href={`/manufacturing/sites/${encodeURIComponent(site.code)}`} key={site.code}><div><b><Localized>{site.name}</Localized></b><span><Localized>{site.code}</Localized></span></div><span><Localized>{site.status}</Localized></span></Link>) : <p className="muted"><Localized>{"No manufacturing sites found."}</Localized></p>}</Localized></section></div>
  </>;
}
