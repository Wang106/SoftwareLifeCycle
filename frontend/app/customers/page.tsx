
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';
import type { Customer } from '../../lib/organizations';

export default async function Page() {
  const rows = await apiGet<Customer[]>('/api/v1/organizations/customers');
  return <><div className="top"><div><div className="eyebrow"><Localized>{"ORGANIZATION"}</Localized></div><h1><Localized>{"Customers"}</Localized></h1><p className="muted"><Localized>{"Customer-specific projects and application software."}</Localized></p></div></div>
    <p><Link href="/releases/matrix"><Localized>{"View customer release matrix →"}</Localized></Link></p>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Customer"}</Localized></th><th><Localized>{"Code"}</Localized></th><th><Localized>{"Region"}</Localized></th><th><Localized>{"Projects"}</Localized></th><th><Localized>{"Application Release"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody><Localized>{rows?.map(row => <tr key={row.code}><td><Link href={`/customers/${encodeURIComponent(row.code)}`}><b><Localized>{row.name}</Localized></b></Link></td><td><Localized>{row.code}</Localized></td><td><Localized>{row.region || 'Unassigned'}</Localized></td><td><Localized>{row.projects.map(p => p.name).join(', ') || '—'}</Localized></td><td><Localized>{row.projects.map(p => p.release && `ASR ${p.release.version}`).filter(Boolean).join(', ') || '—'}</Localized></td><td><span className="status pass"><Localized>{row.status}</Localized></span></td></tr>)}</Localized></tbody></table><Localized>{rows?.length === 0 && <p className="muted"><Localized>{"No customers found."}</Localized></p>}</Localized></section>
    <Localized>{!rows && <p className="datasource"><Localized>{"Customer API unavailable · configure API_BASE_URL to load records."}</Localized></p>}</Localized>
  </>;
}
