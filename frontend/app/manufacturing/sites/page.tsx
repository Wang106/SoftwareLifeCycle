import Link from 'next/link';
import { apiGet } from '../../../lib/api';

export const dynamic = 'force-dynamic';

type SiteSummary = { id: string; site_code: string; name: string; region: string | null; status: string; line_count: number };
const fallback: SiteSummary[] = [{ id: 'demo-site', site_code: 'FACTORY-A', name: 'Factory A', region: 'APAC', status: 'ACTIVE', line_count: 1 }];

export default async function Page() {
  const apiRows = await apiGet<SiteSummary[]>('/api/v1/manufacturing/sites');
  const rows = apiRows && apiRows.length ? apiRows : fallback;
  return <>
    <div className="top"><div><div className="eyebrow">MANUFACTURING</div><h1>Manufacturing Sites</h1><p className="muted">Production sites and lines with expected-versus-actual software control.</p></div><button>+ Site</button></div>
    <section className="panel tablewrap"><table><thead><tr><th>Site</th><th>Region</th><th>Lines</th><th>Software control</th><th>Status</th></tr></thead><tbody>{rows.map(site => <tr key={site.id}><td><Link href={'/manufacturing/sites/' + site.site_code}><b>{site.name}</b></Link><div className="muted">{site.site_code}</div></td><td>{site.region || '—'}</td><td>{site.line_count}</td><td>Authorization-bound deployments</td><td><span className={'status ' + (site.status === 'ACTIVE' ? 'pass' : 'warning')}>{site.status}</span></td></tr>)}</tbody></table></section>
    {!apiRows && <p className="datasource">Demo fallback active · manufacturing API will load automatically when backend is configured.</p>}
  </>;
}
