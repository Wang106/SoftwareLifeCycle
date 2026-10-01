
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Project } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Project[]>('/api/v1/organizations/projects');
  return <><div className="top"><div><div className="eyebrow"><Localized>{"ORGANIZATION"}</Localized></div><h1><Localized>{"Projects"}</Localized></h1><p className="muted"><Localized>{"Customer programs connecting requirements, software and production."}</Localized></p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Project"}</Localized></th><th><Localized>{"Customer"}</Localized></th><th><Localized>{"Vehicle Platform"}</Localized></th><th><Localized>{"Latest Release"}</Localized></th><th><Localized>{"Manufacturing Sites"}</Localized></th></tr></thead><tbody><Localized>{rows?.map(row => <tr key={row.id}><td><Link href={`/projects/${row.id}`}><b><Localized>{row.name}</Localized></b></Link><Localized>{" · "}</Localized><Localized>{row.code}</Localized></td><td><Localized>{row.customer.name}</Localized></td><td><Localized>{row.vehicle_platform || '—'}</Localized></td><td><Localized>{row.release ? `ASR ${row.release.version} · ${row.release.status}` : '—'}</Localized></td><td><Localized>{row.sites.map(s => s.name).join(', ') || '—'}</Localized></td></tr>)}</Localized></tbody></table><Localized>{rows?.length === 0 && <p className="muted"><Localized>{"No projects found."}</Localized></p>}</Localized></section>
    <Localized>{!rows && <p className="datasource"><Localized>{"Project API unavailable · configure API_BASE_URL to load records."}</Localized></p>}</Localized>
  </>;
}
