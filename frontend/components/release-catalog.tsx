import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Kind = 'application' | 'standard';
type Row = { id: string; version: string; status: string; customer?: string | null; project?: string | null;
  base_id?: string | null; base_version?: string | null; snapshot_no?: string | null;
  software?: { code: string; name: string } | null; supplier?: { code: string; name: string } | null };
type Catalog = { kind: Kind; total: number; limit: number; offset: number; next_offset: number | null; items: Row[] };
export type ReleaseSearch = Record<string, string | string[] | undefined>;

export default async function ReleaseCatalog({kind, search}: {kind: Kind; search: ReleaseSearch}) {
  const query = new URLSearchParams();
  for (const key of ['q', 'status', 'software_id', 'limit', 'offset']) {
    const value = search[key];
    if (value !== undefined) query.set(key, typeof value === 'string' ? value : 'invalid');
  }
  const response = await apiGet<Catalog>(`/api/v1/release-catalog/${kind}?${query}`);
  const data = response?.kind === kind ? response : null;
  const path = `/releases/${kind}`;
  const first = new URLSearchParams(query); first.delete('offset');
  const next = new URLSearchParams(query); if (data?.next_offset != null) next.set('offset', String(data.next_offset));
  return <Localized>
    <div className="top"><div><h1><Localized>{kind === 'application' ? 'Application Releases' : 'Standard Releases'}</Localized></h1>
      <p className="muted"><Localized>{kind === 'application' ? 'Customer-specific application software releases and their latest snapshots.' : 'Recorded supplier software baselines used by application releases.'}</Localized></p></div></div>
    <p><Link href={kind === 'application' ? '/releases/standard' : '/releases/application'}><Localized>{kind === 'application' ? 'Browse standard releases →' : 'Application Releases →'}</Localized></Link></p>
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{'Search'}</Localized> <input name="q" defaultValue={query.get('q') || ''} maxLength={200}/></label>
      <label><Localized>{'Status'}</Localized> <input name="status" defaultValue={query.get('status') || ''} maxLength={30}/></label>
      <label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      {query.has('software_id') && <input type="hidden" name="software_id" value={query.get('software_id')!}/>}
      <button type="submit"><Localized>{'Filter'}</Localized></button> <Link href={path}><Localized>{'Reset'}</Localized></Link>
    </form></section>
    {data ? <section className="panel tablewrap"><h2><Localized>{'Total releases'}</Localized>: {data.total}</h2>
      <p className="muted"><Localized>{'Counts cover all filtered records.'}</Localized> <Localized>{'Releases on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{'Version'}</Localized></th>
        {kind === 'application' ? <><th><Localized>{'Customer'}</Localized></th><th><Localized>{'Project'}</Localized></th><th><Localized>{'Base SSR'}</Localized></th><th><Localized>{'Latest Snapshot'}</Localized></th></> : <><th><Localized>{'Software'}</Localized></th><th><Localized>{'Supplier'}</Localized></th></>}
        <th><Localized>{'Status'}</Localized></th></tr></thead><tbody>{data.items.map(row => <tr key={row.id}>
          <td><Link href={`${path}/${encodeURIComponent(row.id)}`}><b>{kind === 'application' ? 'ASR' : 'SSR'} {row.version}</b></Link></td>
          {kind === 'application' ? <><td>{row.customer || '—'}</td><td>{row.project || '—'}</td><td>{row.base_id && row.base_version ? <Link href={`/releases/standard/${encodeURIComponent(row.base_id)}`}>SSR {row.base_version}</Link> : '—'}</td><td>{row.snapshot_no || '—'}</td></> : <><td>{row.software ? `${row.software.name} · ${row.software.code}` : '—'}</td><td>{row.supplier ? <Link href={`/suppliers/${encodeURIComponent(row.supplier.code)}`}>{row.supplier.name}</Link> : '—'}</td></>}
          <td><span className={'status ' + (row.status === 'READY' || row.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{row.status}</Localized></span></td>
        </tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No releases on this page.'}</Localized></p>}
      <p><Link href={`${path}?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
    </section> : <section className="panel"><h2><Localized>{'Release catalog unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or a filter is invalid.'}</Localized></p></section>}
  </Localized>;
}
