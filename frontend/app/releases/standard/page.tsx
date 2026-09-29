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
    <div className="top"><div><h1>Standard Releases</h1><p className="muted">Recorded supplier software baselines used by application releases.</p></div><Link href="/releases/application">Application Releases →</Link></div>
    <section className="panel tablewrap"><table><thead><tr><th>Version</th><th>Software</th><th>Supplier</th><th>Status</th></tr></thead><tbody>
      {rows?.map(row => <tr key={row.id}><td><Link href={`/releases/standard/${encodeURIComponent(row.id)}`}><b>SSR {row.version}</b></Link></td><td>{row.software ? `${row.software.name} · ${row.software.code}` : '—'}</td><td>{row.supplier ? <Link href={`/suppliers/${encodeURIComponent(row.supplier.code)}`}>{row.supplier.name}</Link> : '—'}</td><td><span className={'status ' + (row.status === 'READY' || row.status === 'RELEASED' ? 'pass' : 'warning')}>{row.status}</span></td></tr>)}
    </tbody></table>{rows?.length === 0 && <p className="muted">No standard releases recorded.</p>}</section>
    {!rows && <p className="datasource">Standard release API unavailable.</p>}
  </>;
}
