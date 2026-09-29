import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Project } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Project[]>('/api/v1/organizations/projects');
  return <><div className="top"><div><div className="eyebrow">ORGANIZATION</div><h1>Projects</h1><p className="muted">Customer programs connecting requirements, software and production.</p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th>Project</th><th>Customer</th><th>Vehicle Platform</th><th>Latest Release</th><th>Manufacturing Sites</th></tr></thead><tbody>{rows?.map(row => <tr key={row.id}><td><Link href={`/projects/${row.id}`}><b>{row.name}</b></Link> · {row.code}</td><td>{row.customer.name}</td><td>{row.vehicle_platform || '—'}</td><td>{row.release ? `ASR ${row.release.version} · ${row.release.status}` : '—'}</td><td>{row.sites.map(s => s.name).join(', ') || '—'}</td></tr>)}</tbody></table>{rows?.length === 0 && <p className="muted">No projects found.</p>}</section>
    {!rows && <p className="datasource">Project API unavailable · configure API_BASE_URL to load records.</p>}
  </>;
}
