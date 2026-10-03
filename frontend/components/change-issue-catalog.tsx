import Link from 'next/link';
import { Localized } from './localized';
import { apiGet } from '../lib/api';

type Kind = 'changes' | 'issues';
type Row = { id: string; title: string; scope: string; status: string; request_no?: string;
  source?: string; change_type?: string; issue_no?: string; severity?: string };
type Catalog = { kind: Kind; total: number; limit: number; offset: number;
  next_offset: number | null; items: Row[]; in_verification?: number; ready_for_release?: number };
export type CatalogSearch = Record<string, string | string[] | undefined>;

export default async function ChangeIssueCatalog({kind, search}: {kind: Kind; search: CatalogSearch}) {
  const changes = kind === 'changes';
  const keys = ['q', 'status', 'scope', 'limit', 'offset', ...(changes ?
    ['source', 'change_type', 'software_id', 'customer_id', 'project_id'] : ['severity'])];
  const query = new URLSearchParams();
  for (const key of keys) {
    const value = search[key];
    if (value !== undefined) query.set(key, typeof value === 'string' ? value : 'invalid');
  }
  const response = await apiGet<Catalog>(`/api/v1/change-catalog/${changes ? 'requests' : 'issues'}?${query}`);
  const data = response?.kind === kind ? response : null;
  const path = `/${kind}`;
  const first = new URLSearchParams(query); first.delete('offset');
  const next = new URLSearchParams(query); if (data?.next_offset != null) next.set('offset', String(data.next_offset));
  return <Localized>
    <div className="top"><div><div className="eyebrow"><Localized>{changes ? 'CHANGE CONTROL' : 'QUALITY & IMPACT'}</Localized></div>
      <h1><Localized>{changes ? 'Software Change Requests' : 'Issues'}</Localized></h1><p className="muted"><Localized>{changes ?
        'From approved requirement to verified software change and release traceability.' :
        "Review an issue's linked changes and candidate software releases."}</Localized></p></div></div>
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{'Search'}</Localized> <input name="q" maxLength={200} defaultValue={query.get('q') ?? ''}/></label>
      <label><Localized>{'Status'}</Localized> <input name="status" maxLength={40} defaultValue={query.get('status') ?? ''}/></label>
      <label><Localized>{'Scope'}</Localized> <input name="scope" maxLength={30} defaultValue={query.get('scope') ?? ''}/></label>
      {changes ? <><label><Localized>{'Source'}</Localized> <input name="source" maxLength={30} defaultValue={query.get('source') ?? ''}/></label>
        <label><Localized>{'Type'}</Localized> <input name="change_type" maxLength={40} defaultValue={query.get('change_type') ?? ''}/></label></> :
        <label><Localized>{'Severity'}</Localized> <input name="severity" maxLength={20} defaultValue={query.get('severity') ?? ''}/></label>}
      <label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      {changes && ['software_id', 'customer_id', 'project_id'].filter(key => query.has(key)).map(key =>
        <input type="hidden" key={key} name={key} value={query.get(key)!}/>)}
      <button type="submit"><Localized>{'Filter'}</Localized></button> <Link href={path}><Localized>{'Reset'}</Localized></Link>
    </form></section>
    <div className="summary"><div><b>{data?.total ?? '—'}</b><span><Localized>{changes ? 'Matching SCR' : 'Matching issues'}</Localized></span></div>
      {changes && <><div><b>{data?.in_verification ?? '—'}</b><span><Localized>{'In Verification'}</Localized></span></div>
        <div><b>{data?.ready_for_release ?? '—'}</b><span><Localized>{'Ready for Release'}</Localized></span></div></>}
    </div>
    {data ? <section className="panel tablewrap"><p className="muted"><Localized>{'Counts cover all filtered records.'}</Localized> <Localized>{'Records on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{changes ? 'SCR' : 'Issue'}</Localized></th><th><Localized>{'Title'}</Localized></th>
        {changes && <th><Localized>{'Source'}</Localized></th>}<th><Localized>{'Scope'}</Localized></th>
        <th><Localized>{changes ? 'Type' : 'Severity'}</Localized></th><th><Localized>{'Status'}</Localized></th></tr></thead>
        <tbody>{data.items.map(row => <tr key={row.id}><td><Link href={`${path}/${encodeURIComponent((changes ? row.request_no : row.issue_no)!)}`}><b>{changes ? row.request_no : `#${row.issue_no}`}</b></Link></td>
          <td><Localized>{row.title}</Localized></td>{changes && <td><Localized>{row.source}</Localized></td>}<td><Localized>{row.scope}</Localized></td><td><Localized>{changes ? row.change_type : row.severity}</Localized></td>
          <td><span className={'status ' + ((changes ? row.status.includes('READY') || row.status === 'RELEASED' : row.status.includes('VERIFIED') || row.status === 'CLOSED') ? 'pass' : 'warning')}><Localized>{row.status.replaceAll('_', ' ')}</Localized></span></td>
        </tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No matching records on this page.'}</Localized></p>}
      <p><Link href={`${path}?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
    </section> : <section className="panel"><h2><Localized>{changes ? 'Change catalog unavailable' : 'Issue catalog unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or a filter is invalid.'}</Localized></p></section>}
  </Localized>;
}
