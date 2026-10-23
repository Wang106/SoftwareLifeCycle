import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
import type { ReleaseSearch } from './release-catalog';
type Release = {
    id: string;
    version: string;
    status: string;
    software: {
        name: string;
        code: string;
    } | null;
    supplier: {
        name: string;
        code: string;
    } | null;
};
type Catalog = {
    kind: string;
    total: number;
    next_offset: number | null;
    items: Release[];
};
type Applications = {
    release_id: string;
    total: number;
    next_offset: number | null;
    items: {
        id: string;
        version: string;
        status: string;
    }[];
};
const value = (search: ReleaseSearch, key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
export default async function SupplierReleaseCatalog({ search }: {
    search: ReleaseSearch;
}) {
    const query = new URLSearchParams();
    for (const key of ['q', 'status', 'software_id', 'limit', 'offset'])
        if (search[key] !== undefined)
            query.set(key, value(search, key));
    const response = await apiGet<Catalog>(`/api/v1/release-catalog/standard?${query}`);
    const catalog = response?.kind === 'standard' ? response : null;
    const applications = new Map<string, Applications | null>();
    // Bound both the number of child reads and concurrent API load to this catalog page.
    const rows = catalog?.items ?? [];
    for (let start = 0; start < rows.length; start += 4) {
        await Promise.all(rows.slice(start, start + 4).map(async (row) => {
            const q = new URLSearchParams({ limit: '10' });
            if (search.applications_for === row.id && search.application_offset !== undefined)
                q.set('offset', value(search, 'application_offset'));
            const page = await apiGet<Applications>(`/api/v1/releases/standard/id/${encodeURIComponent(row.id)}/applications?${q}`);
            applications.set(row.id, page?.release_id === row.id ? page : null);
        }));
    }
    const groups = new Map<string | null, {
        supplier: Release['supplier'];
        releases: Release[];
    }>();
    for (const row of rows) {
        const key = row.supplier?.code ?? null;
        if (!groups.has(key))
            groups.set(key, { supplier: row.supplier, releases: [] });
        groups.get(key)!.releases.push(row);
    }
    const link = (updates: Record<string, string | null>, anchor = '') => {
        const q = new URLSearchParams(query);
        for (const key of ['applications_for', 'application_offset'])
            if (search[key] !== undefined)
                q.set(key, value(search, key));
        for (const [key, val] of Object.entries(updates))
            val === null ? q.delete(key) : q.set(key, val);
        return `/releases/standard?${q}${anchor}`;
    };
    return <Localized>
    <div className="top"><div><h1><Localized>{"Standard Releases"}</Localized></h1><p className="muted"><Localized>{"Recorded supplier software baselines used by application releases."}</Localized></p></div></div>
    <p><Link href="/releases/application"><Localized>{"Application Releases →"}</Localized></Link></p>
    <p><Link href="/demo/releases"><Localized>{"Release evidence demonstration"}</Localized></Link><Localized>{" · "}</Localized><Link href="/demo/zfi"><Localized>{"Excel demonstration overview"}</Localized></Link></p>
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{"Search "}</Localized><input name="q" maxLength={200} defaultValue={query.get('q') ?? ''}/></label>
      <label><Localized>{"Record status "}</Localized><input name="status" list="standard-release-statuses" maxLength={30} defaultValue={query.get('status') ?? ''}/></label>
      <datalist id="standard-release-statuses">{['DRAFT', 'READY', 'RELEASED', 'SUPERSEDED'].map(status => <option key={status} value={status}><Localized>{status}</Localized></option>)}</datalist>
      <label><Localized>{"Page size "}</Localized><input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      {query.has('software_id') && <input type="hidden" name="software_id" value={query.get('software_id')!}/>}
      <button type="submit"><Localized>{"Filter"}</Localized></button> <Link href="/releases/standard"><Localized>{"Reset"}</Localized></Link>
    </form></section>
    <p className="muted"><Localized>{'Status suggestions are recorded labels, not approval or release evidence. Other exact status labels can still be entered.'}</Localized></p>
    {(query.get('q')?.trim() || query.get('status') || query.get('software_id')) && <section className="panel" style={{overflowWrap: 'anywhere'}}>
      <h2><Localized>{'Current filters'}</Localized></h2>
      {query.get('q')?.trim() && <p><Localized>{'Search'}</Localized>: <code>{query.get('q')}</code></p>}
      {query.get('status') && <p><Localized>{'Record status'}</Localized>: <code>{query.get('status')}</code></p>}
      {query.get('software_id') && <p><Localized>{'Software ID'}</Localized>: <code>{query.get('software_id')}</code></p>}
      <Link href="/releases/standard"><Localized>{'Clear filters'}</Localized></Link>
    </section>}
    {catalog ? <>
      <p><b><Localized>{"Total releases: "}</Localized>{catalog.total}</b><Localized>{"· Releases on this page: "}</Localized>{rows.length}</p>
      <p className="muted"><Localized>{"Supplier groups cover this filtered page. Application versions are listed newest to oldest by creation time."}</Localized></p>
      {[...groups].map(([key, group]) => <details open key={key ?? 'unknown'} className="supplier-release-card">
        <summary><b>{group.supplier?.name ?? <Localized>{"Unknown supplier"}</Localized>}</b><span className="muted">{group.supplier?.code ?? '—'}</span><span className="disclosure-closed"><Localized>{"Expand"}</Localized></span><span className="disclosure-open"><Localized>{"Collapse"}</Localized></span></summary>
        <div className="supplier-release-content">{group.releases.map(row => {
                    const page = applications.get(row.id);
                    const anchor = `#standard-software-${encodeURIComponent(row.id)}`;
                    return <details key={row.id} id={`standard-software-${row.id}`} open={search.applications_for === row.id} className="standard-software-card">
            <summary><Link href={`/releases/standard/${encodeURIComponent(row.id)}`}><b>{row.software?.name ?? <Localized>{"No software"}</Localized>}</b><Localized>{"· SSR "}</Localized>{row.version}</Link><span className="muted">{row.software?.code ?? '—'}</span><span className="status"><Localized>{row.status}</Localized></span><span className="disclosure-closed"><Localized>{"Expand"}</Localized></span><span className="disclosure-open"><Localized>{"Collapse"}</Localized></span></summary>
            <div className="standard-software-content"><h3><Localized>{"Application releases using this baseline"}</Localized></h3>
              {page ? <><p><Localized>{"Recorded count: "}</Localized>{page.total}</p><ul className="application-version-list">{page.items.map(application => <li key={application.id}><Link href={`/releases/application/${encodeURIComponent(application.id)}`}><Localized>{"ASR "}</Localized>{application.version}</Link><span className="status"><Localized>{application.status}</Localized></span></li>)}</ul>
                {!page.items.length && <p className="muted"><Localized>{"No application releases on this page."}</Localized></p>}
                <p><Link href={link({ applications_for: row.id, application_offset: '0' }, anchor)}><Localized>{"First page"}</Localized></Link> {page.next_offset !== null && <Link href={link({ applications_for: row.id, application_offset: String(page.next_offset) }, anchor)}><Localized>{"Next page →"}</Localized></Link>}</p></>
                            : <p className="muted"><Localized>{"Application release page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}
            </div>
          </details>;
                })}</div>
      </details>)}
      {!rows.length && <p className="panel"><Localized>{"No releases on this page."}</Localized></p>}
      <p><Link href={link({ offset: null, applications_for: null, application_offset: null })}><Localized>{"First page"}</Localized></Link> {catalog.next_offset !== null && <Link href={link({ offset: String(catalog.next_offset), applications_for: null, application_offset: null })}><Localized>{"Next page →"}</Localized></Link>}</p>
    </> : <section className="panel"><h2><Localized>{"Release catalog unavailable"}</Localized></h2><p className="muted"><Localized>{"The API is unavailable or a filter is invalid."}</Localized></p></section>}
  </Localized>;
}
