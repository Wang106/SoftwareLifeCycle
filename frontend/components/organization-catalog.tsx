import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
import { organizationQuery, type OrganizationKind, type OrganizationSearch, type OrganizationPage, type OrganizationRow } from '../lib/organization-views';
export function OrganizationRelease({row, standard = false}: {row: OrganizationRow; standard?: boolean}) {
  return <Localized>{row.release_id ? <><Link href={`/releases/${standard ? 'standard' : 'application'}/${row.release_id}`}>{standard ? 'SSR' : 'ASR'} {row.release_version}</Link> <Localized>{row.release_status ?? ''}</Localized></> : <>—</>}</Localized>;
}
export default async function OrganizationCatalog({kind, search}: {kind: OrganizationKind; search: OrganizationSearch}) {
  const supplier = kind === 'suppliers', customer = kind === 'customers';
  const title = supplier ? 'Suppliers' : customer ? 'Customers' : 'Projects';
  const special = supplier ? 'country' : customer ? 'region' : 'customer_id';
  const query = organizationQuery(search, ['q', 'status', special, 'limit', 'offset']);
  const response = await apiGet<OrganizationPage>(`/api/v1/organization-views/${kind}?${query}`);
  const data = response?.kind === kind ? response : null;
  const path = `/${kind}`;
  const first = new URLSearchParams(query); first.delete('offset');
  const next = new URLSearchParams(query); if (data?.next_offset != null) next.set('offset', String(data.next_offset));
  return <Localized>
    <div className="top"><div><div className="eyebrow"><Localized>{'ORGANIZATION'}</Localized></div><h1><Localized>{title}</Localized></h1>
      <p className="muted"><Localized>{supplier ? 'Upstream software ownership and standard release context.' : customer ? 'Customer-specific projects and application software.' : 'Customer programs connecting requirements, software and production.'}</Localized></p></div></div>
    {customer && <p><Link href="/releases/matrix"><Localized>{'View customer release matrix →'}</Localized></Link></p>}
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{'Search'}</Localized> <input name="q" maxLength={200} defaultValue={query.get('q') ?? ''}/></label>
      <label><Localized>{'Status'}</Localized> <input name="status" maxLength={30} defaultValue={query.get('status') ?? ''}/></label>
      {supplier && <label><Localized>{'Country'}</Localized> <input name="country" maxLength={100} defaultValue={query.get('country') ?? ''}/></label>}
      {customer && <label><Localized>{'Region'}</Localized> <select name="region" defaultValue={query.get('region') ?? ''}><option value=""><Localized>{'All regions'}</Localized></option>
        {['APAC','EUROPE','AMERICAS','OTHER','UNASSIGNED'].map(region => <option key={region} value={region}><Localized>{region === 'UNASSIGNED' ? 'Unassigned region' : region}</Localized></option>)}</select></label>}
      {!supplier && !customer && query.has('customer_id') && <input type="hidden" name="customer_id" value={query.get('customer_id')!}/>}
      <label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      <button type="submit"><Localized>{'Filter'}</Localized></button> <Link href={path}><Localized>{'Reset'}</Localized></Link>
    </form></section>
    <div className="summary"><div><b>{data?.total ?? '—'}</b><span><Localized>{'Matching organizations'}</Localized></span></div></div>
    {data ? <section className="panel tablewrap"><p className="muted"><Localized>{'Counts cover all filtered records.'}</Localized> <Localized>{'Records on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{supplier ? 'Supplier' : customer ? 'Customer' : 'Project'}</Localized></th><th><Localized>{'Code'}</Localized></th>
        <th><Localized>{supplier ? 'Country' : customer ? 'Region' : 'Customer'}</Localized></th>
        <th><Localized>{supplier ? 'Software products' : customer ? 'Projects' : 'Manufacturing Sites'}</Localized></th>
        {customer && <th><Localized>{'Projects with software release'}</Localized></th>}
        {!supplier && !customer && <><th><Localized>{'Vehicle Platform'}</Localized></th><th><Localized>{'Latest Application Release'}</Localized></th></>}
        <th><Localized>{'Status'}</Localized></th></tr></thead><tbody>{data.items.map(row => <tr key={row.id}>
          <td><Link href={`${path}/${encodeURIComponent(kind === 'projects' ? row.id : row.code)}`}><b><Localized>{row.name}</Localized></b></Link></td><td>{row.code}</td>
          <td>{supplier ? <Localized>{row.country ?? '—'}</Localized> : customer ? <Localized>{row.region ?? 'Unassigned region'}</Localized> : row.customer_code ?
            <Link href={`/customers/${encodeURIComponent(row.customer_code)}`}><Localized>{row.customer_name}</Localized></Link> : row.customer_id}</td>
          <td>{supplier ? row.software_count : customer ? row.project_count : row.site_count}</td>{customer && <td>{row.released_project_count}</td>}
          {!supplier && !customer && <><td><Localized>{row.vehicle_platform ?? '—'}</Localized></td><td><OrganizationRelease row={row}/></td></>}
          <td><Localized>{row.status}</Localized></td></tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No matching records on this page.'}</Localized></p>}
      <p><Link href={`${path}?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
      <p className="muted"><Localized>{'Open a profile to browse its related records.'}</Localized></p>
    </section> : <section className="panel"><h2><Localized>{'Organization catalog unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or a filter is invalid.'}</Localized></p></section>}
  </Localized>;
}
