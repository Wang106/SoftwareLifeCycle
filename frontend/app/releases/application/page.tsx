
import { Localized, LocalizedAttributes } from "../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type ApplicationRelease = {
  id: string; version: string; status: string; customer: string | null; project: string | null;
  base_id: string | null; base_version: string | null; snapshot_no: string | null;
};

export default async function Page() {
  const rows = await apiGet<ApplicationRelease[]>('/api/v1/releases/application');
  return <><div className="top"><div><h1><Localized>{"Application Releases"}</Localized></h1><p className="muted"><Localized>{"Customer-specific application software releases and their latest snapshots."}</Localized></p></div></div>
    <p><Link href="/releases/standard"><Localized>{"Browse standard releases →"}</Localized></Link></p>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Version"}</Localized></th><th><Localized>{"Customer"}</Localized></th><th><Localized>{"Project"}</Localized></th><th><Localized>{"Base SSR"}</Localized></th><th><Localized>{"Latest Snapshot"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody><Localized>{rows?.map(row => <tr key={row.id}><td><Link href={`/releases/application/${row.id}`}><b><Localized>{"ASR "}</Localized><Localized>{row.version}</Localized></b></Link></td><td><Localized>{row.customer || '—'}</Localized></td><td><Localized>{row.project || '—'}</Localized></td><td><Localized>{row.base_id && row.base_version ? <Link href={`/releases/standard/${encodeURIComponent(row.base_id)}`}><Localized>{"SSR "}</Localized><Localized>{row.base_version}</Localized></Link> : '—'}</Localized></td><td><Localized>{row.snapshot_no || '—'}</Localized></td><td><span className={'status ' + (row.status === 'READY' || row.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{row.status}</Localized></span></td></tr>)}</Localized></tbody></table><Localized>{rows?.length === 0 && <p className="muted"><Localized>{"No application releases found."}</Localized></p>}</Localized></section>
    <Localized>{!rows && <p className="datasource"><Localized>{"Release API unavailable · configure API_BASE_URL to load records."}</Localized></p>}</Localized>
  </>;
}
