import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Customer } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Customer[]>('/api/v1/organizations/customers');
  return <><div className="top"><div><div className="eyebrow">ORGANIZATION</div><h1>Customers</h1><p className="muted">Customer-specific projects and application software.</p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th>Customer</th><th>Code</th><th>Projects</th><th>Application Release</th><th>Status</th></tr></thead><tbody>{rows?.map(row => <tr key={row.code}><td><Link href={`/customers/${encodeURIComponent(row.code)}`}><b>{row.name}</b></Link></td><td>{row.code}</td><td>{row.projects.map(p => p.name).join(', ') || '—'}</td><td>{row.projects.map(p => p.release && `ASR ${p.release.version}`).filter(Boolean).join(', ') || '—'}</td><td><span className="status pass">{row.status}</span></td></tr>)}</tbody></table>{rows?.length === 0 && <p className="muted">No customers found.</p>}</section>
    {!rows && <p className="datasource">Customer API unavailable · configure API_BASE_URL to load records.</p>}
  </>;
}
