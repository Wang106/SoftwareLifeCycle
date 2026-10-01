
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Supplier } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Supplier[]>('/api/v1/organizations/suppliers');
  return <><div className="top"><div><div className="eyebrow"><Localized>{"ORGANIZATION"}</Localized></div><h1><Localized>{"Suppliers"}</Localized></h1><p className="muted"><Localized>{"Upstream software ownership and standard release context."}</Localized></p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Supplier"}</Localized></th><th><Localized>{"Code"}</Localized></th><th><Localized>{"Country"}</Localized></th><th><Localized>{"Software"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody><Localized>{rows?.map(row => <tr key={row.code}><td><Link href={`/suppliers/${encodeURIComponent(row.code)}`}><b><Localized>{row.name}</Localized></b></Link></td><td><Localized>{row.code}</Localized></td><td><Localized>{row.country || '—'}</Localized></td><td><Localized>{row.software.map(p => p.name).join(', ') || '—'}</Localized></td><td><span className="status pass"><Localized>{row.status}</Localized></span></td></tr>)}</Localized></tbody></table><Localized>{rows?.length === 0 && <p className="muted"><Localized>{"No suppliers found."}</Localized></p>}</Localized></section>
    <Localized>{!rows && <p className="datasource"><Localized>{"Supplier API unavailable · configure API_BASE_URL to load records."}</Localized></p>}</Localized>
  </>;
}
