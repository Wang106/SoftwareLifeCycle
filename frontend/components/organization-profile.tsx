import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
import { OrganizationRelease } from './organization-catalog';
import { organizationMatches, organizationQuery, type OrganizationKind, type OrganizationSearch, type OrganizationSummary, type OrganizationPage } from '../lib/organization-views';
export default async function OrganizationProfile({kind, identifier, search}: {kind: OrganizationKind; identifier: string; search: OrganizationSearch}) {
  const supplier = kind === 'suppliers', customer = kind === 'customers';
  const base = `/api/v1/organization-views/${kind}/${encodeURIComponent(identifier)}`;
  const row = await apiGet<OrganizationSummary>(`${base}/summary`);
  if (!row || !organizationMatches(kind, identifier, row))
    return <section className="panel"><h1><Localized>{supplier ? 'Supplier unavailable' : customer ? 'Customer unavailable' : 'Project unavailable'}</Localized></h1>
      <p className="muted"><Localized>{'The organization was not found, is ambiguous or the API could not be reached.'}</Localized></p><Link href={`/${kind}`}><Localized>{'Back to directory →'}</Localized></Link></section>;
  const query = organizationQuery(search, ['limit', 'offset']); query.set('organization_id', row.id);
  const response = await apiGet<OrganizationPage>(`${base}/items?${query}`);
  const data = response?.kind === kind && response.organization_id === row.id ? response : null;
  const first = new URLSearchParams(query); first.delete('organization_id'); first.delete('offset');
  const next = new URLSearchParams(first); if (data?.next_offset != null) next.set('offset', String(data.next_offset));
  const path = `/${kind}/${encodeURIComponent(kind === 'projects' ? row.id : row.code)}`;
  const count = supplier ? row.software_count : customer ? row.project_count : row.site_count;
  const heading = supplier ? 'Software portfolio' : customer ? 'Projects and current software' : 'Manufacturing Sites';
  return <Localized>
    <p><Link href={`/resources?entity_type=${supplier ? 'SUPPLIER' : customer ? 'CUSTOMER' : 'PROJECT'}&entity_id=${row.id}`}><Localized>{'Materials & evidence references →'}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow">{row.code}</div><h1><Localized>{row.name}</Localized></h1></div><span className="status"><Localized>{row.status}</Localized></span></div>
    <section className="panel"><h2><Localized>{'Profile'}</Localized></h2><div className="kv"><span><Localized>{'Code'}</Localized></span><b>{row.code}</b>
      {supplier ? <><span><Localized>{'Country'}</Localized></span><b><Localized>{row.country ?? '—'}</Localized></b><span><Localized>{'Website'}</Localized></span><b>{row.website ?? '—'}</b><span><Localized>{'Description'}</Localized></span><b><Localized>{row.description ?? '—'}</Localized></b></> :
        customer ? <><span><Localized>{'Region'}</Localized></span><b><Localized>{row.region ?? 'Unassigned region'}</Localized></b></> :
          <><span><Localized>{'Customer'}</Localized></span>{row.customer_code ? <Link href={`/customers/${encodeURIComponent(row.customer_code)}`}><Localized>{row.customer_name}</Localized></Link> : <b>{row.customer_id}</b>}
          <span><Localized>{'Vehicle Platform'}</Localized></span><b><Localized>{row.vehicle_platform ?? '—'}</Localized></b><span><Localized>{'Latest Application Release'}</Localized></span><b><OrganizationRelease row={row}/></b></>}
    </div></section>
    {!supplier && <p><Link href={`/releases/matrix?${customer ? 'customer='+encodeURIComponent(row.code) : 'project_id='+row.id}`}><Localized>{'View complete release history →'}</Localized></Link></p>}
    <div className="summary"><div><b>{count}</b><span><Localized>{heading}</Localized></span></div>{customer && <div><b>{row.released_project_count}</b><span><Localized>{'Projects with software release'}</Localized></span></div>}</div>
    <section className="panel"><form method="get" className="filters"><label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label><button type="submit"><Localized>{'Filter'}</Localized></button> <Link href={path}><Localized>{'Reset'}</Localized></Link></form></section>
    {data ? <section className="panel tablewrap"><h2><Localized>{heading}</Localized></h2><p className="muted"><Localized>{'Records on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{supplier ? 'Software' : customer ? 'Project' : 'Manufacturing Site'}</Localized></th><th><Localized>{'Code'}</Localized></th><th><Localized>{'Status'}</Localized></th>
        {supplier && <th><Localized>{'Type'}</Localized></th>}{(supplier || customer) && <th><Localized>{supplier ? 'Standard Release' : 'Latest Application Release'}</Localized></th>}</tr></thead>
        <tbody>{data.items.map(item => <tr key={item.id}><td>{supplier ? <Link href={`/releases/standard?software_id=${item.id}`}><Localized>{item.name}</Localized></Link> :
          <Link href={`${customer ? '/projects/' : '/manufacturing/sites/'}${item.id}`}><Localized>{item.name}</Localized></Link>}</td><td>{item.code}</td><td><Localized>{item.status}</Localized></td>
          {supplier && <td><Localized>{item.type ?? 'Software'}</Localized></td>}{(supplier || customer) && <td><OrganizationRelease row={item} standard={supplier}/></td>}</tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No records on this page.'}</Localized></p>}
      <p><Link href={`${path}?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
    </section> : <section className="panel"><h2><Localized>{'Organization collection unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or the page selection is invalid.'}</Localized></p><Link href={path}><Localized>{'Reset'}</Localized></Link></section>}
  </Localized>;
}
