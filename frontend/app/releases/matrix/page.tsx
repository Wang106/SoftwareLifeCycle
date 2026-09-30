import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Ref = { id: string; version: string; status: string; created_at: string } | null;
type Matrix = { total: number; next_offset: number | null;
  summary: { customers: number; projects: number; application_releases: number };
  items: { customer: { code: string; name: string; region: string; status: string };
    project: { id: string; code: string; name: string; status: string } | null;
    software: { code: string; name: string } | null;
    application_release: Ref; standard_release: Ref;
    snapshot: { snapshot_no: string; status: string } | null }[] };
const regions = ['APAC', 'EUROPE', 'AMERICAS', 'OTHER', 'UNASSIGNED'];

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const filters = new URLSearchParams();
  for (const key of ['region', 'customer', 'project_id', 'status', 'q']) {
    const value = query[key];
    if (typeof value === 'string' && value.trim()) filters.set(key, value.trim());
  }
  const offset = typeof query.offset === 'string' && /^\d+$/.test(query.offset) ? Number(query.offset) : 0;
  if ((query.offset !== undefined && (typeof query.offset !== 'string' || !/^\d+$/.test(query.offset)))
    || !Number.isSafeInteger(offset) || offset > 100000
    || (filters.has('region') && !regions.includes(filters.get('region')!))) {
    return <section className="panel"><h1>Invalid matrix filter</h1><Link href="/releases/matrix">Reset filters →</Link></section>;
  }
  const request = new URLSearchParams(filters); request.set('limit', '50'); request.set('offset', String(offset));
  const data = await apiGet<Matrix>(`/api/v1/organizations/release-matrix?${request}`);
  function pageLink(value: number) {
    const params = new URLSearchParams(filters); params.set('offset', String(value));
    return `/releases/matrix?${params}`;
  }
  return <>
    <div className="top"><div><div className="eyebrow">CUSTOMER / PROJECT / SOFTWARE</div><h1>Release matrix</h1><p className="muted">Recorded ASR history and its SSR baseline. Release status does not establish which software is deployed in production.</p></div></div>
    <section className="panel"><form method="get">
      <label>Region <select name="region" defaultValue={filters.get('region') || ''}><option value="">All regions</option>{regions.map(region => <option key={region} value={region}>{region === 'UNASSIGNED' ? 'Unassigned region' : region}</option>)}</select></label>{' '}
      <label>Customer code <input name="customer" defaultValue={filters.get('customer') || ''} maxLength={50} placeholder="CUS-001" /></label>{' '}
      <label>ASR status <input name="status" defaultValue={filters.get('status') || ''} maxLength={30} placeholder="RELEASED" /></label>{' '}
      <label>Search <input name="q" defaultValue={filters.get('q') || ''} maxLength={100} placeholder="Customer, project, software or version" /></label>{' '}
      {filters.get('project_id') && <input type="hidden" name="project_id" value={filters.get('project_id')!} />}
      <button type="submit">Filter</button> <Link href="/releases/matrix">Reset</Link>
    </form><p className="muted">Unknown regions remain unassigned. Without an ASR filter, customers without projects and projects without software are included.</p>
      {filters.get('project_id') && <p className="muted">Filtered to one project · <Link href="/releases/matrix">Show all projects</Link></p>}
    </section>
    {data ? <>
      <div className="cards"><div className="card"><span className="muted">CUSTOMERS</span><div className="metric">{data.summary.customers}</div></div><div className="card"><span className="muted">PROJECTS</span><div className="metric">{data.summary.projects}</div></div><div className="card"><span className="muted">RECORDED ASR</span><div className="metric">{data.summary.application_releases}</div></div></div>
      <section className="panel tablewrap"><h2>{data.total} matching records</h2><table><thead><tr><th>Region / customer</th><th>Project</th><th>Software / ASR</th><th>SSR baseline</th><th>Snapshot / history</th></tr></thead><tbody>
        {data.items.map((row, index) => <tr key={`${row.customer.code}-${row.project?.id}-${row.application_release?.id}-${index}`}>
          <td><div className="muted">{row.customer.region === 'UNASSIGNED' ? 'Unassigned' : row.customer.region}</div><Link href={`/customers/${encodeURIComponent(row.customer.code)}`}><b>{row.customer.name}</b></Link><div>{row.customer.code} · {row.customer.status}</div></td>
          <td>{row.project ? <><Link href={`/projects/${row.project.id}`}>{row.project.name}</Link><div>{row.project.code} · {row.project.status}</div></> : 'No project recorded'}</td>
          <td>{row.software && <div>{row.software.name} · {row.software.code}</div>}{row.application_release ? <><Link href={`/releases/application/${row.application_release.id}`}><b>ASR {row.application_release.version}</b></Link><div>{row.application_release.status}</div><small>{row.application_release.created_at.slice(0, 16).replace('T', ' ')} UTC</small></> : 'No ASR recorded'}</td>
          <td>{row.standard_release ? <><Link href={`/releases/standard/${row.standard_release.id}`}>SSR {row.standard_release.version}</Link><div>{row.standard_release.status}</div></> : '—'}</td>
          <td>{row.snapshot ? <Link href={`/snapshots/${encodeURIComponent(row.snapshot.snapshot_no)}`}>{row.snapshot.snapshot_no}</Link> : 'No snapshot'}{row.application_release && <div><Link href={`/releases/${row.application_release.id}/snapshots`}>Freeze history →</Link></div>}</td>
        </tr>)}
      </tbody></table>{data.items.length === 0 && <p className="muted">No records match these filters or page.</p>}
      <p>{offset > 0 && <Link href={pageLink(Math.max(0, offset - 50))}>← Previous page</Link>}{data.next_offset !== null && <> · <Link href={pageLink(data.next_offset)}>Next page →</Link></>}</p>
      </section>
    </> : <section className="panel"><h2>Matrix unavailable</h2><p className="muted">The API could not be reached or a filter was rejected. No demo results are substituted.</p></section>}
  </>;
}
