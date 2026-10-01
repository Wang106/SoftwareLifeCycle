
import { Localized, LocalizedAttributes } from "../../../components/localized";
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
    return <section className="panel"><h1><Localized>{"Invalid matrix filter"}</Localized></h1><Link href="/releases/matrix"><Localized>{"Reset filters →"}</Localized></Link></section>;
  }
  const request = new URLSearchParams(filters); request.set('limit', '50'); request.set('offset', String(offset));
  const data = await apiGet<Matrix>(`/api/v1/organizations/release-matrix?${request}`);
  function pageLink(value: number) {
    const params = new URLSearchParams(filters); params.set('offset', String(value));
    return `/releases/matrix?${params}`;
  }
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"CUSTOMER / PROJECT / SOFTWARE"}</Localized></div><h1><Localized>{"Release matrix"}</Localized></h1><p className="muted"><Localized>{"Recorded ASR history and its SSR baseline. Release status does not establish which software is deployed in production."}</Localized></p></div></div>
    <section className="panel"><form method="get">
      <label><Localized>{"Region "}</Localized><select name="region" defaultValue={filters.get('region') || ''}><option value=""><Localized>{"All regions"}</Localized></option><Localized>{regions.map(region => <option key={region} value={region}><Localized>{region === 'UNASSIGNED' ? 'Unassigned region' : region}</Localized></option>)}</Localized></select></label><Localized>{' '}</Localized>
      <label><Localized>{"Customer code "}</Localized><LocalizedAttributes><input name="customer" defaultValue={filters.get('customer') || ''} maxLength={50} placeholder="CUS-001" /></LocalizedAttributes></label><Localized>{' '}</Localized>
      <label><Localized>{"ASR status "}</Localized><LocalizedAttributes><input name="status" defaultValue={filters.get('status') || ''} maxLength={30} placeholder="RELEASED" /></LocalizedAttributes></label><Localized>{' '}</Localized>
      <label><Localized>{"Search "}</Localized><LocalizedAttributes><input name="q" defaultValue={filters.get('q') || ''} maxLength={100} placeholder="Customer, project, software or version" /></LocalizedAttributes></label><Localized>{' '}</Localized>
      <Localized>{filters.get('project_id') && <input type="hidden" name="project_id" value={filters.get('project_id')!} />}</Localized>
      <button type="submit"><Localized>{"Filter"}</Localized></button> <Link href="/releases/matrix"><Localized>{"Reset"}</Localized></Link>
    </form><p className="muted"><Localized>{"Unknown regions remain unassigned. Without an ASR filter, customers without projects and projects without software are included."}</Localized></p>
      <Localized>{filters.get('project_id') && <p className="muted"><Localized>{"Filtered to one project · "}</Localized><Link href="/releases/matrix"><Localized>{"Show all projects"}</Localized></Link></p>}</Localized>
    </section>
    <Localized>{data ? <>
      <div className="cards"><div className="card"><span className="muted"><Localized>{"CUSTOMERS"}</Localized></span><div className="metric"><Localized>{data.summary.customers}</Localized></div></div><div className="card"><span className="muted"><Localized>{"PROJECTS"}</Localized></span><div className="metric"><Localized>{data.summary.projects}</Localized></div></div><div className="card"><span className="muted"><Localized>{"RECORDED ASR"}</Localized></span><div className="metric"><Localized>{data.summary.application_releases}</Localized></div></div></div>
      <section className="panel tablewrap"><h2><Localized>{data.total}</Localized><Localized>{" matching records"}</Localized></h2><table><thead><tr><th><Localized>{"Region / customer"}</Localized></th><th><Localized>{"Project"}</Localized></th><th><Localized>{"Software / ASR"}</Localized></th><th><Localized>{"SSR baseline"}</Localized></th><th><Localized>{"Snapshot / history"}</Localized></th></tr></thead><tbody>
        <Localized>{data.items.map((row, index) => <tr key={`${row.customer.code}-${row.project?.id}-${row.application_release?.id}-${index}`}>
          <td><div className="muted"><Localized>{row.customer.region === 'UNASSIGNED' ? 'Unassigned' : row.customer.region}</Localized></div><Link href={`/customers/${encodeURIComponent(row.customer.code)}`}><b><Localized>{row.customer.name}</Localized></b></Link><div><Localized>{row.customer.code}</Localized><Localized>{" · "}</Localized><Localized>{row.customer.status}</Localized></div></td>
          <td><Localized>{row.project ? <><Link href={`/projects/${row.project.id}`}><Localized>{row.project.name}</Localized></Link><div><Localized>{row.project.code}</Localized><Localized>{" · "}</Localized><Localized>{row.project.status}</Localized></div></> : 'No project recorded'}</Localized></td>
          <td><Localized>{row.software && <div><Localized>{row.software.name}</Localized><Localized>{" · "}</Localized><Localized>{row.software.code}</Localized></div>}</Localized><Localized>{row.application_release ? <><Link href={`/releases/application/${row.application_release.id}`}><b><Localized>{"ASR "}</Localized><Localized>{row.application_release.version}</Localized></b></Link><div><Localized>{row.application_release.status}</Localized></div><small><Localized>{row.application_release.created_at.slice(0, 16).replace('T', ' ')}</Localized><Localized>{" UTC"}</Localized></small></> : 'No ASR recorded'}</Localized></td>
          <td><Localized>{row.standard_release ? <><Link href={`/releases/standard/${row.standard_release.id}`}><Localized>{"SSR "}</Localized><Localized>{row.standard_release.version}</Localized></Link><div><Localized>{row.standard_release.status}</Localized></div></> : '—'}</Localized></td>
          <td><Localized>{row.snapshot ? <Link href={`/snapshots/${encodeURIComponent(row.snapshot.snapshot_no)}`}><Localized>{row.snapshot.snapshot_no}</Localized></Link> : 'No snapshot'}</Localized><Localized>{row.application_release && <div><Link href={`/releases/${row.application_release.id}/snapshots`}><Localized>{"Freeze history →"}</Localized></Link></div>}</Localized></td>
        </tr>)}</Localized>
      </tbody></table><Localized>{data.items.length === 0 && <p className="muted"><Localized>{"No records match these filters or page."}</Localized></p>}</Localized>
      <p><Localized>{offset > 0 && <Link href={pageLink(Math.max(0, offset - 50))}><Localized>{"← Previous page"}</Localized></Link>}</Localized><Localized>{data.next_offset !== null && <><Localized>{" · "}</Localized><Link href={pageLink(data.next_offset)}><Localized>{"Next page →"}</Localized></Link></>}</Localized></p>
      </section>
    </> : <section className="panel"><h2><Localized>{"Matrix unavailable"}</Localized></h2><p className="muted"><Localized>{"The API could not be reached or a filter was rejected. No demo results are substituted."}</Localized></p></section>}</Localized>
  </>;
}
