import Link from 'next/link';
import { Suspense } from 'react';
import { PageLoading } from './page-loading';
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
    limit: number;
    offset: number;
    total: number;
    next_offset: number | null;
    items: Release[];
};
type Applications = {
    release_id: string;
    limit: number;
    offset: number;
    total: number;
    next_offset: number | null;
    items: {
        id: string;
        version: string;
        status: string;
    }[];
};
type ApplicationBatch = { limit: number; offset: number; items: Applications[] };
const nonnegativeInteger = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0;
// Mirror Pydantic's integer query syntax, including integral decimals and digit
// separators, so one invalid child offset does not hide the other visible rows.
function applicationOffset(raw: ReleaseSearch[string]): number | null {
    if (raw === undefined) return 0;
    if (typeof raw !== 'string') return null;
    const text = raw.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '');
    if (!/^[+-]?\d(?:_?\d)*(?:\.0+)?$/.test(text)) return null;
    const parsed = Number(text.replaceAll('_', ''));
    return nonnegativeInteger(parsed) && parsed <= 100000 ? parsed : null;
}
// Reject an incomplete or stale batch as a whole; never associate child data by position.
function validBatch(batch: ApplicationBatch | null, catalog: Catalog, selected: string | undefined, offset: number) {
    if (!batch || !nonnegativeInteger(batch.limit) || batch.limit < 1 || batch.limit > 100 ||
        !nonnegativeInteger(batch.offset) || batch.offset > 100000 ||
        batch.limit !== catalog.limit || batch.offset !== catalog.offset ||
        !Array.isArray(batch.items) || batch.items.length !== catalog.items.length || batch.items.length > batch.limit)
        return false;
    const parents = new Set(catalog.items.map(row => row.id));
    if (parents.size !== catalog.items.length) return false;
    const seen = new Set<string>();
    for (const page of batch.items) {
        if (!page || !parents.has(page.release_id) || seen.has(page.release_id) || page.limit !== 10 ||
            !nonnegativeInteger(page.total) || !nonnegativeInteger(page.offset) || page.offset > 100000 ||
            page.offset !== (page.release_id === selected ? offset : 0) ||
            page.next_offset !== (page.offset + 10 < page.total ? page.offset + 10 : null) ||
            !Array.isArray(page.items) || page.items.length !== Math.min(10, Math.max(0, page.total - page.offset)))
            return false;
        const children = new Set<string>();
        for (const child of page.items) {
            if (!child || typeof child.id !== 'string' || !child.id || children.has(child.id) ||
                typeof child.version !== 'string' || typeof child.status !== 'string') return false;
            children.add(child.id);
        }
        seen.add(page.release_id);
    }
    return true;
}
const value = (search: ReleaseSearch, key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
const READ_ALLOWANCE_MS = 15000;
function linkFor(query: URLSearchParams, search: ReleaseSearch, updates: Record<string, string | null> = {}, anchor = '') {
    const q = new URLSearchParams(query);
    for (const key of ['applications_for', 'application_offset'])
        if (search[key] !== undefined) q.set(key, value(search, key));
    for (const [key, val] of Object.entries(updates))
        val === null ? q.delete(key) : q.set(key, val);
    return `/releases/standard?${q}${anchor}`;
}
function CatalogCounts({ catalog }: { catalog: Catalog | null }) {
    return <Localized><p><b><Localized>{"Total releases: "}</Localized>{catalog?.total ?? '—'}</b><Localized>{"· Releases on this page: "}</Localized>{catalog ? (catalog.items ?? []).length : '—'}</p></Localized>;
}
function CatalogLoading() {
    return <Localized><div data-standard-catalog-state="pending" aria-busy="true"><CatalogCounts catalog={null}/><PageLoading/></div></Localized>;
}
function ApplicationLoading() {
    return <Localized><div data-standard-application-state="pending" role="status" aria-busy="true">
      <p><Localized>{'Reading application releases'}</Localized></p><p><Localized>{"Recorded count: "}</Localized>—</p>
    </div></Localized>;
}
async function readApplications(catalog: Catalog, query: URLSearchParams, search: ReleaseSearch, deadline: number): Promise<Map<string, Applications | null>> {
    const applications = new Map<string, Applications | null>();
    const rows = catalog.items ?? [];
    if (!rows.length) return applications;
    const batchQuery = new URLSearchParams(query);
    const selected = rows.find(row => row.id === search.applications_for)?.id;
    const offset = selected ? applicationOffset(search.application_offset) : 0;
    if (selected && offset !== null) {
        batchQuery.set('applications_for', selected);
        if (search.application_offset !== undefined)
            batchQuery.set('application_offset', value(search, 'application_offset'));
    }
    // Deduct elapsed parent work instead of granting a second full allowance.
    // apiGet starts its header/body timer after Next's connection(); this is not
    // a strict deadline covering framework connection, SSR scheduling or transfer.
    const timeoutMs = Math.min(READ_ALLOWANCE_MS, deadline - performance.now());
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return applications;
    const batch = await apiGet<ApplicationBatch>(`/api/v1/release-catalog/standard/applications?${batchQuery}`, { timeoutMs });
    if (validBatch(batch, catalog, offset === null ? undefined : selected, offset ?? 0))
        for (const page of batch!.items)
            if (offset !== null || page.release_id !== selected) applications.set(page.release_id, page);
    return applications;
}
async function ApplicationData({ applications, rowId, queryString, search }: {
    applications: Promise<Map<string, Applications | null>>; rowId: string; queryString: string; search: ReleaseSearch;
}) {
    const page = (await applications).get(rowId);
    const query = new URLSearchParams(queryString);
    const anchor = `#standard-software-${encodeURIComponent(rowId)}`;
    // Pagination keeps the row anchor; retry omits it to avoid hash-only navigation.
    return <Localized><div data-standard-application-state={page ? 'ready' : 'unavailable'}>
      {page ? <><p><Localized>{"Recorded count: "}</Localized>{page.total}</p><ul className="application-version-list">{page.items.map(application => <li key={application.id}><Link prefetch={false} href={`/releases/application/${encodeURIComponent(application.id)}`}><Localized>{"ASR "}</Localized>{application.version}</Link><span className="status"><Localized>{application.status}</Localized></span></li>)}</ul>
        {!page.items.length && <p className="muted"><Localized>{"No application releases on this page."}</Localized></p>}
        <p><Link prefetch={false} href={linkFor(query, search, { applications_for: rowId, application_offset: '0' }, anchor)}><Localized>{"First page"}</Localized></Link> {page.next_offset !== null && <Link prefetch={false} href={linkFor(query, search, { applications_for: rowId, application_offset: String(page.next_offset) }, anchor)}><Localized>{"Next page →"}</Localized></Link>}</p></>
        : <><p className="muted"><Localized>{"Application release page unavailable. The API is unavailable or pagination is invalid."}</Localized></p><p><a href={linkFor(query, search)}><Localized>{'Read application releases again'}</Localized></a></p></>}
    </div></Localized>;
}
async function CatalogData({ queryString, search, dataKey }: { queryString: string; search: ReleaseSearch; dataKey: string }) {
    const query = new URLSearchParams(queryString);
    const deadline = performance.now() + READ_ALLOWANCE_MS;
    const response = await apiGet<Catalog>(`/api/v1/release-catalog/standard?${query}`, { timeoutMs: READ_ALLOWANCE_MS });
    const catalog = response?.kind === 'standard' ? response : null;
    if (!catalog) return <Localized><div data-standard-catalog-state="unavailable"><CatalogCounts catalog={null}/>
      <section className="panel"><h2><Localized>{"Release catalog unavailable"}</Localized></h2><p className="muted"><Localized>{"The API is unavailable or a filter is invalid."}</Localized></p></section>
      <p><a href={linkFor(query, search)}><Localized>{'Read standard releases again'}</Localized></a></p>
    </div></Localized>;
    const rows = catalog.items ?? [];
    // One shared batch read and one validation pass, independent of row count.
    const applications = readApplications(catalog, query, search, deadline);
    const groups = new Map<string | null, { supplier: Release['supplier']; releases: Release[] }>();
    for (const row of rows) {
        const key = row.supplier?.code ?? null;
        if (!groups.has(key)) groups.set(key, { supplier: row.supplier, releases: [] });
        groups.get(key)!.releases.push(row);
    }
    return <Localized><div data-standard-catalog-state="ready"><CatalogCounts catalog={catalog}/>
      <p className="muted"><Localized>{"Supplier groups cover this filtered page. Application versions are listed newest to oldest by creation time."}</Localized></p>
      {[...groups].map(([key, group]) => <details open key={key ?? 'unknown'} className="supplier-release-card">
        <summary><b>{group.supplier?.name ?? <Localized>{"Unknown supplier"}</Localized>}</b><span className="muted">{group.supplier?.code ?? '—'}</span><span className="disclosure-closed"><Localized>{"Expand"}</Localized></span><span className="disclosure-open"><Localized>{"Collapse"}</Localized></span></summary>
        <div className="supplier-release-content">{group.releases.map(row => <details key={row.id} id={`standard-software-${row.id}`} open={search.applications_for === row.id} className="standard-software-card">
          <summary><Link prefetch={false} href={`/releases/standard/${encodeURIComponent(row.id)}`}><b>{row.software?.name ?? <Localized>{"No software"}</Localized>}</b><Localized>{"· SSR "}</Localized>{row.version}</Link><span className="muted">{row.software?.code ?? '—'}</span><span className="status"><Localized>{row.status}</Localized></span><span className="disclosure-closed"><Localized>{"Expand"}</Localized></span><span className="disclosure-open"><Localized>{"Collapse"}</Localized></span></summary>
          <div className="standard-software-content"><h3><Localized>{"Application releases using this baseline"}</Localized></h3>
            <Suspense key={`${dataKey}:${row.id}`} fallback={<ApplicationLoading/>}><ApplicationData applications={applications} rowId={row.id} queryString={queryString} search={search}/></Suspense>
          </div>
        </details>)}</div>
      </details>)}
      {!rows.length && <p className="panel"><Localized>{"No releases on this page."}</Localized></p>}
      <p><Link prefetch={false} href={linkFor(query, search, { offset: null, applications_for: null, application_offset: null })}><Localized>{"First page"}</Localized></Link> {catalog.next_offset !== null && <Link prefetch={false} href={linkFor(query, search, { offset: String(catalog.next_offset), applications_for: null, application_offset: null })}><Localized>{"Next page →"}</Localized></Link>}</p>
    </div></Localized>;
}
export default function SupplierReleaseCatalog({ search }: { search: ReleaseSearch }) {
    const query = new URLSearchParams();
    for (const key of ['q', 'status', 'software_id', 'limit', 'offset'])
        if (search[key] !== undefined) query.set(key, value(search, key));
    const dataKey = linkFor(query, search);
    return <Localized>
    <div className="top"><div><h1><Localized>{"Standard Releases"}</Localized></h1><p className="muted"><Localized>{"Recorded supplier software baselines used by application releases."}</Localized></p></div></div>
    <p><Link prefetch={false} href="/releases/application"><Localized>{"Application Releases →"}</Localized></Link></p>
    <p><Link prefetch={false} href="/demo/releases"><Localized>{"Release evidence demonstration"}</Localized></Link><Localized>{" · "}</Localized><Link prefetch={false} href="/demo/zfi"><Localized>{"Excel demonstration overview"}</Localized></Link></p>
    <section className="panel"><form method="get" className="filters">
      <label><Localized>{"Search "}</Localized><input name="q" maxLength={200} defaultValue={query.get('q') ?? ''}/></label>
      <label><Localized>{"Record status "}</Localized><input name="status" list="standard-release-statuses" maxLength={30} defaultValue={query.get('status') ?? ''}/></label>
      <datalist id="standard-release-statuses">{['DRAFT', 'READY', 'RELEASED', 'SUPERSEDED'].map(status => <option key={status} value={status}><Localized>{status}</Localized></option>)}</datalist>
      <label><Localized>{"Page size "}</Localized><input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label>
      {query.has('software_id') && <input type="hidden" name="software_id" value={query.get('software_id')!}/>}
      <button type="submit"><Localized>{"Filter"}</Localized></button> <Link prefetch={false} href="/releases/standard"><Localized>{"Reset"}</Localized></Link>
    </form></section>
    <p className="muted"><Localized>{'Status suggestions are recorded labels, not approval or release evidence. Other exact status labels can still be entered.'}</Localized></p>
    {(query.get('q')?.trim() || query.get('status') || query.get('software_id')) && <section className="panel" style={{overflowWrap: 'anywhere'}}>
      <h2><Localized>{'Current filters'}</Localized></h2>
      {query.get('q')?.trim() && <p><Localized>{'Search'}</Localized>: <code>{query.get('q')}</code></p>}
      {query.get('status') && <p><Localized>{'Record status'}</Localized>: <code>{query.get('status')}</code></p>}
      {query.get('software_id') && <p><Localized>{'Software ID'}</Localized>: <code>{query.get('software_id')}</code></p>}
      <Link prefetch={false} href="/releases/standard"><Localized>{'Clear filters'}</Localized></Link>
    </section>}
    <Suspense key={dataKey} fallback={<CatalogLoading/>}><CatalogData queryString={query.toString()} search={search} dataKey={dataKey}/></Suspense>
  </Localized>;
}
