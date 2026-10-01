
import { Localized, LocalizedAttributes } from "../../../components/localized";
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
    <div className="top"><div><div className="eyebrow"><Localized>{"MANUFACTURING"}</Localized></div><h1><Localized>{"Manufacturing Sites"}</Localized></h1><p className="muted"><Localized>{"Recorded production sites and latest expected-versus-actual software status by line."}</Localized></p></div><Link href="/deployments"><Localized>{"Deployments →"}</Localized></Link></div>
    <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Site"}</Localized></th><th><Localized>{"Customer / Project"}</Localized></th><th><Localized>{"Region"}</Localized></th><th><Localized>{"Lines"}</Localized></th><th><Localized>{"Latest control"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead><tbody><Localized>{apiRows?.map(site => <tr key={site.id}><td><Link href={'/manufacturing/sites/' + encodeURIComponent(site.site_code)}><b><Localized>{site.name}</Localized></b></Link><div className="muted"><Localized>{site.site_code}</Localized></div></td><td><Localized>{site.customer?.name || '—'}</Localized><div className="muted"><Localized>{site.project?.name || '—'}</Localized></div></td><td><Localized>{site.region || '—'}</Localized></td><td><Localized>{site.deployed_line_count}</Localized><Localized>{" deployed / "}</Localized><Localized>{site.line_count}</Localized><Localized>{" total"}</Localized></td><td><b><Localized>{site.matching_line_count}</Localized><Localized>{" match"}</Localized></b><Localized>{site.attention_line_count > 0 && <div className="muted"><Localized>{site.attention_line_count}</Localized><Localized>{" need attention"}</Localized></div>}</Localized></td><td><span className={'status ' + (site.status === 'ACTIVE' ? 'pass' : 'warning')}><Localized>{site.status}</Localized></span></td></tr>)}</Localized></tbody></table><Localized>{apiRows?.length === 0 && <p className="muted"><Localized>{"No manufacturing sites recorded."}</Localized></p>}</Localized></section>
    <Localized>{!apiRows && <p className="datasource"><Localized>{"Manufacturing API unavailable. No substitute records are shown."}</Localized></p>}</Localized>
  </>;
}
