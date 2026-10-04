import Link from 'next/link';
import { Localized } from './localized';
import { apiGet } from '../lib/api';
import { manufacturingQuery, type ManufacturingSearch, type ManufacturingPage, type SiteRow } from '../lib/manufacturing-views';
export default async function ManufacturingCatalog({search}: {search: ManufacturingSearch}) {
  const query = manufacturingQuery(search, ['q','status','region','customer_id','project_id','limit','offset']);
  const response = await apiGet<ManufacturingPage<SiteRow>>(`/api/v1/manufacturing-views/sites?${query}`);
  const data = response?.kind === 'manufacturing-sites' ? response : null;
  const first = new URLSearchParams(query); first.delete('offset');
  const next = new URLSearchParams(query); if (data?.next_offset != null) next.set('offset', String(data.next_offset));
  return <Localized>
    <div className="top"><div><div className="eyebrow"><Localized>{'MANUFACTURING'}</Localized></div><h1><Localized>{'Manufacturing Sites'}</Localized></h1><p className="muted"><Localized>{'Recorded production sites and latest expected-versus-actual software status by line.'}</Localized></p></div><Link href="/deployments"><Localized>{'Deployments →'}</Localized></Link></div>
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{'Search'}</Localized> <input name="q" maxLength={200} defaultValue={query.get('q') ?? ''}/></label>
      <label><Localized>{'Status'}</Localized> <input name="status" maxLength={30} defaultValue={query.get('status') ?? ''}/></label>
      <label><Localized>{'Region'}</Localized> <input name="region" maxLength={100} defaultValue={query.get('region') ?? ''}/></label>
      <label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      {['customer_id','project_id'].filter(key=>query.has(key)).map(key=><input type="hidden" key={key} name={key} value={query.get(key)!}/>)}
      <button type="submit"><Localized>{'Filter'}</Localized></button> <Link href="/manufacturing/sites"><Localized>{'Reset'}</Localized></Link>
    </form></section>
    <div className="summary"><div><b>{data?.total ?? '—'}</b><span><Localized>{'Matching manufacturing sites'}</Localized></span></div></div>
    {data ? <section className="panel tablewrap"><p className="muted"><Localized>{'Counts cover all filtered records.'}</Localized> <Localized>{'Records on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{'Site'}</Localized></th><th><Localized>{'Customer / Project'}</Localized></th><th><Localized>{'Region'}</Localized></th><th><Localized>{'Lines'}</Localized></th><th><Localized>{'Latest control'}</Localized></th><th><Localized>{'Status'}</Localized></th></tr></thead>
        <tbody>{data.items.map(site=><tr key={site.id}><td><Link href={`/manufacturing/sites/${site.id}`}><b><Localized>{site.name}</Localized></b></Link><div>{site.site_code}</div></td>
          <td>{site.customer_code ? <Link href={`/customers/${encodeURIComponent(site.customer_code)}`}><Localized>{site.customer_name}</Localized></Link> : site.customer_id}<div><Link href={`/projects/${site.project_id}`}><Localized>{site.project_name ?? site.project_id}</Localized></Link></div></td>
          <td><Localized>{site.region ?? '—'}</Localized></td><td>{site.deployed_line_count} / {site.line_count}</td><td>{site.matching_line_count} <Localized>{'match'}</Localized><div>{site.attention_line_count} <Localized>{'need attention'}</Localized></div></td><td><Localized>{site.status}</Localized></td></tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No matching records on this page.'}</Localized></p>}
      <p><Link href={`/manufacturing/sites?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`/manufacturing/sites?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
    </section> : <section className="panel"><h2><Localized>{'Manufacturing catalog unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or a filter is invalid.'}</Localized></p></section>}
    <p className="datasource"><Localized>{'Stored manufacturing states are observations, not production permission.'}</Localized></p>
  </Localized>;
}
