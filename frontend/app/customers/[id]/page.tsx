import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Customer } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Customer>(`/api/v1/organizations/customers/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1>Customer unavailable</h1><p className="muted">The customer was not found or the API could not be reached.</p><Link href="/customers">Back to customers →</Link></section>;
  return <>
    <p><Link href={`/resources?entity_type=CUSTOMER&entity_id=${row.id}`}>Materials & evidence references →</Link></p><div className="top"><div><div className="eyebrow">CUSTOMER · {row.code}</div><h1>{row.name}</h1><p className="muted">Application software and projects.</p></div><span className="status pass">{row.status}</span></div>
    <p>{row.region || 'Unassigned region'} · <Link href={`/releases/matrix?customer=${encodeURIComponent(row.code)}`}>View complete release history →</Link></p>
    <div className="cards"><div className="card"><span className="muted">PROJECTS</span><div className="metric">{row.projects.length}</div><small>Customer programs</small></div><div className="card"><span className="muted">APPLICATION RELEASES</span><div className="metric">{row.projects.filter(p => p.release).length}</div><small>Projects with software release</small></div></div>
    <section className="panel tablewrap"><h2>Projects and current software</h2><table><thead><tr><th>Project</th><th>Status</th><th>Latest Application Release</th><th>Release Status</th></tr></thead><tbody>{row.projects.map(p => <tr key={p.id}><td><Link href={`/projects/${p.id}`}><b>{p.name}</b></Link> · {p.code}</td><td>{p.status}</td><td>{p.release ? <Link href={`/releases/application/${p.release.id}`}>ASR {p.release.version}</Link> : '—'}</td><td>{p.release?.status || '—'}</td></tr>)}</tbody></table>{row.projects.length === 0 && <p className="muted">No projects found.</p>}</section>
  </>;
}
