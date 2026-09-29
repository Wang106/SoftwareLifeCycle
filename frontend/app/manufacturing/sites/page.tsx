import Link from 'next/link';
import { apiGet } from '../../../lib/api';

export const dynamic = 'force-dynamic';

type SiteSummary = {
  id: string; site_code: string; name: string; region: string | null; status: string;
  customer: { code: string; name: string } | null; project: { code: string; name: string } | null;
  line_count: number; deployed_line_count: number; matching_line_count: number; attention_line_count: number;
};

export default async function Page() {
  const apiRows = await apiGet<SiteSummary[]>('/api/v1/manufacturing/sites');
  return <>
    <div className="top"><div><div className="eyebrow">MANUFACTURING</div><h1>Manufacturing Sites</h1><p className="muted">Recorded production sites and latest expected-versus-actual software status by line.</p></div><Link href="/deployments">Deployments →</Link></div>
    <section className="panel tablewrap"><table><thead><tr><th>Site</th><th>Customer / Project</th><th>Region</th><th>Lines</th><th>Latest control</th><th>Status</th></tr></thead><tbody>{apiRows?.map(site => <tr key={site.id}><td><Link href={'/manufacturing/sites/' + encodeURIComponent(site.site_code)}><b>{site.name}</b></Link><div className="muted">{site.site_code}</div></td><td>{site.customer?.name || '—'}<div className="muted">{site.project?.name || '—'}</div></td><td>{site.region || '—'}</td><td>{site.deployed_line_count} deployed / {site.line_count} total</td><td><b>{site.matching_line_count} match</b>{site.attention_line_count > 0 && <div className="muted">{site.attention_line_count} need attention</div>}</td><td><span className={'status ' + (site.status === 'ACTIVE' ? 'pass' : 'warning')}>{site.status}</span></td></tr>)}</tbody></table>{apiRows?.length === 0 && <p className="muted">No manufacturing sites recorded.</p>}</section>
    {!apiRows && <p className="datasource">Manufacturing API unavailable. No substitute records are shown.</p>}
  </>;
}
