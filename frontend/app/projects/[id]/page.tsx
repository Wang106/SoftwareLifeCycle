import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Project } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Project>(`/api/v1/organizations/projects/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1>Project unavailable</h1><p className="muted">The project was not found or the API could not be reached.</p><Link href="/projects">Back to projects →</Link></section>;
  return <><div className="top"><div><div className="eyebrow">PROJECT · {row.code}</div><h1>{row.name}</h1><p className="muted">{row.customer.name} · {row.vehicle_platform || 'Vehicle platform not specified'}</p></div><span className="status pass">{row.status}</span></div>
      <p><Link href={`/releases/matrix?project_id=${encodeURIComponent(row.id)}`}>View project release history →</Link></p>
    <div className="grid2"><section className="panel"><h2>Project profile</h2><div className="kv"><span>Customer</span><Link href={`/customers/${encodeURIComponent(row.customer.code)}`}><b>{row.customer.name}</b></Link><span>Project Code</span><b>{row.code}</b><span>Vehicle Platform</span><b>{row.vehicle_platform || '—'}</b><span>Latest Application Release</span><b>{row.release ? <Link href={`/releases/application/${row.release.id}`}>ASR {row.release.version} · {row.release.status}</Link> : '—'}</b></div></section>
    <section className="panel"><h2>Manufacturing sites</h2>{row.sites.length ? row.sites.map(site => <Link className="entityrow" href={`/manufacturing/sites/${encodeURIComponent(site.code)}`} key={site.code}><div><b>{site.name}</b><span>{site.code}</span></div><span>{site.status}</span></Link>) : <p className="muted">No manufacturing sites found.</p>}</section></div>
  </>;
}
