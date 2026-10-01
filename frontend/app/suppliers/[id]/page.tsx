
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { Supplier } from '../../../lib/organizations';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const row = await apiGet<Supplier>(`/api/v1/organizations/suppliers/${encodeURIComponent(id)}`);
  if (!row) return <section className="panel"><h1><Localized>{"Supplier unavailable"}</Localized></h1><p className="muted"><Localized>{"The supplier was not found or the API could not be reached."}</Localized></p><Link href="/suppliers"><Localized>{"Back to suppliers →"}</Localized></Link></section>;
  return <>
    <p><Link href={`/resources?entity_type=SUPPLIER&entity_id=${row.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p><div className="top"><div><div className="eyebrow"><Localized>{"SUPPLIER · "}</Localized><Localized>{row.code}</Localized></div><h1><Localized>{row.name}</Localized></h1><p className="muted"><Localized>{"Standard software source organization"}</Localized></p></div><span className="status pass"><Localized>{row.status}</Localized></span></div>
    <div className="grid2"><section className="panel"><h2><Localized>{"Profile"}</Localized></h2><div className="kv"><span><Localized>{"Supplier Code"}</Localized></span><b><Localized>{row.code}</Localized></b><span><Localized>{"Country"}</Localized></span><b><Localized>{row.country || '—'}</Localized></b><span><Localized>{"Website"}</Localized></span><b><Localized>{row.website || '—'}</Localized></b><span><Localized>{"Description"}</Localized></span><b><Localized>{row.description || '—'}</Localized></b></div></section>
      <section className="panel"><h2><Localized>{"Software portfolio"}</Localized></h2><Localized>{row.software.length ? row.software.map(product => <Link className="entityrow" href="/releases/standard" key={product.code}><div><b><Localized>{product.name}</Localized></b><span><Localized>{product.code}</Localized><Localized>{" · "}</Localized><Localized>{product.type || 'Software'}</Localized></span></div><div><b><Localized>{product.standard_version ? `SSR ${product.standard_version}` : 'No standard release'}</Localized></b><span><Localized>{product.status}</Localized></span></div></Link>) : <p className="muted"><Localized>{"No software products found."}</Localized></p>}</Localized></section></div>
  </>;
}
