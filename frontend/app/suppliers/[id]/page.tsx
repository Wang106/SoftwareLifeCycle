import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Supplier } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Supplier>(`/api/v1/organizations/suppliers/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1>Supplier unavailable</h1><p className="muted">The supplier was not found or the API could not be reached.</p><Link href="/suppliers">Back to suppliers →</Link></section>;
  return <><div className="top"><div><div className="eyebrow">SUPPLIER · {row.code}</div><h1>{row.name}</h1><p className="muted">Standard software source organization</p></div><span className="status pass">{row.status}</span></div>
    <div className="grid2"><section className="panel"><h2>Profile</h2><div className="kv"><span>Supplier Code</span><b>{row.code}</b><span>Country</span><b>{row.country || '—'}</b><span>Website</span><b>{row.website || '—'}</b><span>Description</span><b>{row.description || '—'}</b></div></section>
      <section className="panel"><h2>Software portfolio</h2>{row.software.length ? row.software.map(product => <Link className="entityrow" href="/releases/application" key={product.code}><div><b>{product.name}</b><span>{product.code} · {product.type || 'Software'}</span></div><div><b>{product.standard_version ? `SSR ${product.standard_version}` : 'No standard release'}</b><span>{product.status}</span></div></Link>) : <p className="muted">No software products found.</p>}</section></div>
  </>;
}
