import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type ApplicationRelease = {
  id: string; version: string; status: string; customer: string | null; project: string | null;
  base_id: string | null; base_version: string | null; snapshot_no: string | null;
};

export default async function Page() {
  const rows = await apiGet<ApplicationRelease[]>('/api/v1/releases/application');
  return <><div className="top"><div><h1>Application Releases</h1><p className="muted">Customer-specific application software releases and their latest snapshots.</p></div></div>
    <p><Link href="/releases/standard">Browse standard releases →</Link></p>
    <section className="panel tablewrap"><table><thead><tr><th>Version</th><th>Customer</th><th>Project</th><th>Base SSR</th><th>Latest Snapshot</th><th>Status</th></tr></thead><tbody>{rows?.map(row => <tr key={row.id}><td><Link href={`/releases/application/${row.id}`}><b>ASR {row.version}</b></Link></td><td>{row.customer || '—'}</td><td>{row.project || '—'}</td><td>{row.base_id && row.base_version ? <Link href={`/releases/standard/${encodeURIComponent(row.base_id)}`}>SSR {row.base_version}</Link> : '—'}</td><td>{row.snapshot_no || '—'}</td><td><span className={'status ' + (row.status === 'READY' || row.status === 'RELEASED' ? 'pass' : 'warning')}>{row.status}</span></td></tr>)}</tbody></table>{rows?.length === 0 && <p className="muted">No application releases found.</p>}</section>
    {!rows && <p className="datasource">Release API unavailable · configure API_BASE_URL to load records.</p>}
  </>;
}
