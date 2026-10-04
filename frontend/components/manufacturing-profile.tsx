import Link from 'next/link';
import { Localized } from './localized';
import { apiGet } from '../lib/api';
import { manufacturingQuery, siteMatches, type ManufacturingSearch, type ManufacturingPage, type SiteSummary, type LineRow } from '../lib/manufacturing-views';
export function ManufacturingSoftware({id, version, type, snapshot, snapshotNo}: {id: string | null; version: string | null; type: string | null; snapshot: string | null; snapshotNo: string | null}) {
  return <Localized>{id && (type === 'APPLICATION' || type === 'STANDARD') ? <Link href={`/releases/${type === 'APPLICATION' ? 'application' : 'standard'}/${id}`}><Localized>{type === 'APPLICATION' ? 'ASR' : 'SSR'}</Localized> <Localized>{version ?? id}</Localized></Link> : id ?? '—'}<div>{snapshotNo && snapshot ? <Link href={`/snapshots/${encodeURIComponent(snapshotNo)}?manifest_snapshot_id=${snapshot}`}><Localized>{snapshotNo}</Localized></Link> : snapshot ?? '—'}</div></Localized>;
}
export default async function ManufacturingProfile({identifier, search}: {identifier: string; search: ManufacturingSearch}) {
  const base = `/api/v1/manufacturing-views/sites/${encodeURIComponent(identifier)}`;
  const site = await apiGet<SiteSummary>(`${base}/summary`);
  if (!site || site.kind !== 'manufacturing-site' || !siteMatches(identifier,site)) return <section className="panel"><h1><Localized>{'Manufacturing site unavailable'}</Localized></h1><p className="muted"><Localized>{'The site was not found, is ambiguous or the API could not be reached.'}</Localized></p><Link href="/manufacturing/sites"><Localized>{'← All manufacturing sites'}</Localized></Link></section>;
  const query = manufacturingQuery(search,['limit','offset']); query.set('site_id',site.id);
  const response = await apiGet<ManufacturingPage<LineRow>>(`${base}/lines?${query}`);
  const data = response?.kind === 'manufacturing-lines' && response.site_id === site.id && response.site_code === site.site_code ? response : null;
  const first = new URLSearchParams(query); first.delete('site_id'); first.delete('offset');
  const next = new URLSearchParams(first); if (data?.next_offset != null) next.set('offset',String(data.next_offset));
  const path = `/manufacturing/sites/${site.id}`;
  return <Localized>
    <div className="top"><div><div className="eyebrow"><Localized>{'MANUFACTURING SITE · '}</Localized>{site.site_code}</div><h1><Localized>{site.name}</Localized></h1><p className="muted"><Localized>{site.customer_name ?? 'Customer'}</Localized> / <Localized>{site.project_name ?? 'Project'}</Localized></p></div><span className="status"><Localized>{site.status}</Localized></span></div>
    <div className="summary"><div><b>{site.line_count}</b><span><Localized>{'PRODUCTION LINES'}</Localized></span></div><div><b>{site.approved_authorization_line_count}</b><span><Localized>{'ACTIVE AUTHORIZATION'}</Localized></span></div><div><b>{site.line_count > 0 && site.matching_line_count === site.line_count ? <Localized>{'MATCH'}</Localized> : <Localized>{'CHECK'}</Localized>}</b><span><Localized>{'SOFTWARE MATCH'}</Localized></span></div></div>
    <section className="panel"><h2><Localized>{'Recorded production context'}</Localized></h2><div className="kv">
      <span><Localized>{'First line authorization'}</Localized></span><b>{site.first_authorization_no ? <Link href={`/distribution/authorizations/${encodeURIComponent(site.first_authorization_no)}`}><Localized>{site.first_authorization_no}</Localized></Link> : site.first_authorization_id ?? '—'} <Localized>{site.first_authorization_status ?? ''}</Localized></b>
      <span><Localized>{'Recorded batch context'}</Localized></span><b>{site.context_batch_batch_no ? <Link href={`/production/batches/${encodeURIComponent(site.context_batch_batch_no)}`}><Localized>{site.context_batch_batch_no}</Localized></Link> : '—'} <Localized>{site.context_batch_status ?? ''}</Localized><div><Localized>{site.context_batch_note ?? ''}</Localized></div></b>
      <span><Localized>{'First line changeover'}</Localized></span><b><Localized>{site.first_changeover_changeover_no ?? '—'}</Localized> <Localized>{site.first_changeover_status ?? ''}</Localized></b>
      <span><Localized>{'Expected'}</Localized></span><ManufacturingSoftware id={site.first_expected_release_id} version={site.first_expected_version} type={site.first_expected_type} snapshot={site.first_expected_snapshot_id} snapshotNo={site.first_expected_snapshot_no}/>
    </div>{site.first_deployment_no && <p><Link href={`/deployments/${encodeURIComponent(site.first_deployment_no)}`}><Localized>{'Open exact deployment history →'}</Localized></Link></p>}
      <p className="muted"><Localized>{'Batch context preserves recorded ordering; it does not assert that a batch is active.'}</Localized></p>
    </section>
    <section className="panel"><form method="get" className="filters"><label><Localized>{'Page size'}</Localized> <input name="limit" type="number" min={1} max={100} defaultValue={query.get('limit') ?? '50'}/></label><button type="submit"><Localized>{'Filter'}</Localized></button> <Link href={path}><Localized>{'Reset'}</Localized></Link></form></section>
    {data ? <section className="panel tablewrap"><h2><Localized>{'Line software status'}</Localized></h2><p className="muted"><Localized>{'Records on this page'}</Localized>: {data.items.length}</p>
      <table><thead><tr><th><Localized>{'Line'}</Localized></th><th><Localized>{'Expected'}</Localized></th><th><Localized>{'Actual'}</Localized></th><th><Localized>{'Authorization'}</Localized></th><th><Localized>{'Stored status'}</Localized></th></tr></thead>
        <tbody>{data.items.map(line=><tr key={line.id}><td><b><Localized>{line.name}</Localized></b><div>{line.line_code} · <Localized>{line.status}</Localized></div><div><Localized>{'Line UUID: '}</Localized>{line.id}</div>
          <Link href={`/commands?${new URLSearchParams({operation:'deployment',line:line.id})}`}><Localized>{'Prepare expectation for this line →'}</Localized></Link>
          {line.deployment_no && <p><Link href={`/deployments/${encodeURIComponent(line.deployment_no)}`}><Localized>{'Open exact deployment history →'}</Localized></Link></p>}</td>
          <td><ManufacturingSoftware id={line.expected_release_id} version={line.expected_version} type={line.expected_type} snapshot={line.expected_snapshot_id} snapshotNo={line.expected_snapshot_no}/></td>
          <td>{line.actual_release_id && line.actual_snapshot_id ? <ManufacturingSoftware id={line.actual_release_id} version={line.actual_release_version} type={line.actual_type} snapshot={line.actual_snapshot_id} snapshotNo={line.actual_snapshot_no}/> : <Localized>{'Not reported'}</Localized>}</td>
          <td>{line.authorization_no ? <Link href={`/distribution/authorizations/${encodeURIComponent(line.authorization_no)}`}><Localized>{line.authorization_no}</Localized></Link> : line.authorization_id ?? '—'}<div><Localized>{line.authorization_status ?? ''}</Localized></div></td>
          <td><Localized>{line.deployment_status ?? 'NOT DEPLOYED'}</Localized></td></tr>)}</tbody></table>
      {!data.items.length && <p className="muted"><Localized>{'No records on this page.'}</Localized></p>}
      <p><Link href={`${path}?${first}`}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={`${path}?${next}`}><Localized>{'Next page →'}</Localized></Link>}</p>
    </section> : <section className="panel"><h2><Localized>{'Manufacturing lines unavailable'}</Localized></h2><p className="muted"><Localized>{'The API is unavailable or the page selection is invalid.'}</Localized></p><Link href={path}><Localized>{'Reset'}</Localized></Link></section>}
    <p className="datasource"><Localized>{'Stored manufacturing states are observations, not production permission.'}</Localized></p><p><Link href="/manufacturing/sites"><Localized>{'← All manufacturing sites'}</Localized></Link></p>
  </Localized>;
}
