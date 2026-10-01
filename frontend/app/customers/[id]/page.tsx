
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Customer } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Customer>(`/api/v1/organizations/customers/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1><Localized>{"Customer unavailable"}</Localized></h1><p className="muted"><Localized>{"The customer was not found or the API could not be reached."}</Localized></p><Link href="/customers"><Localized>{"Back to customers →"}</Localized></Link></section>;
  return <>
    <p><Link href={`/resources?entity_type=CUSTOMER&entity_id=${row.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p><div className="top"><div><div className="eyebrow"><Localized>{"CUSTOMER · "}</Localized><Localized>{row.code}</Localized></div><h1><Localized>{row.name}</Localized></h1><p className="muted"><Localized>{"Application software and projects."}</Localized></p></div><span className="status pass"><Localized>{row.status}</Localized></span></div>
    <p><Localized>{row.region || 'Unassigned region'}</Localized><Localized>{" · "}</Localized><Link href={`/releases/matrix?customer=${encodeURIComponent(row.code)}`}><Localized>{"View complete release history →"}</Localized></Link></p>
    <div className="cards"><div className="card"><span className="muted"><Localized>{"PROJECTS"}</Localized></span><div className="metric"><Localized>{row.projects.length}</Localized></div><small><Localized>{"Customer programs"}</Localized></small></div><div className="card"><span className="muted"><Localized>{"APPLICATION RELEASES"}</Localized></span><div className="metric"><Localized>{row.projects.filter(p => p.release).length}</Localized></div><small><Localized>{"Projects with software release"}</Localized></small></div></div>
    <section className="panel tablewrap"><h2><Localized>{"Projects and current software"}</Localized></h2><table><thead><tr><th><Localized>{"Project"}</Localized></th><th><Localized>{"Status"}</Localized></th><th><Localized>{"Latest Application Release"}</Localized></th><th><Localized>{"Release Status"}</Localized></th></tr></thead><tbody><Localized>{row.projects.map(p => <tr key={p.id}><td><Link href={`/projects/${p.id}`}><b><Localized>{p.name}</Localized></b></Link><Localized>{" · "}</Localized><Localized>{p.code}</Localized></td><td><Localized>{p.status}</Localized></td><td><Localized>{p.release ? <Link href={`/releases/application/${p.release.id}`}><Localized>{"ASR "}</Localized><Localized>{p.release.version}</Localized></Link> : '—'}</Localized></td><td><Localized>{p.release?.status || '—'}</Localized></td></tr>)}</Localized></tbody></table><Localized>{row.projects.length === 0 && <p className="muted"><Localized>{"No projects found."}</Localized></p>}</Localized></section>
  </>;
}
