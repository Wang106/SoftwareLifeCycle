
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type StandardRelease = {
  id: string; version: string; status: string;
  software: { code: string; name: string } | null;
  supplier: { code: string; name: string } | null;
};

export default async function Page() {
  const rows = await apiGet<StandardRelease[]>('/api/v1/releases/standard');
  return <>
    <div className="top"><div><h1><Localized>{"Standard Releases"}</Localized></h1><p className="muted"><Localized>{"Recorded supplier software baselines used by application releases."}</Localized></p></div><Link href="/releases/application"><Localized>{"Application Releases →"}</Localized></Link></div>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Version"}</Localized></th><th><Localized>{"Software"}</Localized></th><th><Localized>{"Supplier"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody>
      <Localized>{rows?.map(row => <tr key={row.id}><td><Link href={`/releases/standard/${encodeURIComponent(row.id)}`}><b><Localized>{"SSR "}</Localized><Localized>{row.version}</Localized></b></Link></td><td><Localized>{row.software ? `${row.software.name} · ${row.software.code}` : '—'}</Localized></td><td><Localized>{row.supplier ? <Link href={`/suppliers/${encodeURIComponent(row.supplier.code)}`}><Localized>{row.supplier.name}</Localized></Link> : '—'}</Localized></td><td><span className={'status ' + (row.status === 'READY' || row.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{row.status}</Localized></span></td></tr>)}</Localized>
    </tbody></table><Localized>{rows?.length === 0 && <p className="muted"><Localized>{"No standard releases recorded."}</Localized></p>}</Localized></section>
    <Localized>{!rows && <p className="datasource"><Localized>{"Standard release API unavailable."}</Localized></p>}</Localized>
  </>;
}
