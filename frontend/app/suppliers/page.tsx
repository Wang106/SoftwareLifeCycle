import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Supplier } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Supplier[]>('/api/v1/organizations/suppliers');
  return <><div className="top"><div><div className="eyebrow">ORGANIZATION</div><h1>Suppliers</h1><p className="muted">Upstream software ownership and standard release context.</p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th>Supplier</th><th>Code</th><th>Country</th><th>Software</th><th>Status</th></tr></thead><tbody>{rows?.map(row => <tr key={row.code}><td><Link href={`/suppliers/${encodeURIComponent(row.code)}`}><b>{row.name}</b></Link></td><td>{row.code}</td><td>{row.country || '—'}</td><td>{row.software.map(p => p.name).join(', ') || '—'}</td><td><span className="status pass">{row.status}</span></td></tr>)}</tbody></table>{rows?.length === 0 && <p className="muted">No suppliers found.</p>}</section>
    {!rows && <p className="datasource">Supplier API unavailable · configure API_BASE_URL to load records.</p>}
  </>;
}
