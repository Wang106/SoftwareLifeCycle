import Link from 'next/link';
import {apiGet} from '../../../lib/api';
import {Localized} from '../../../components/localized';

type Row = {source_ref: string; release_id: string; version: string; release_type: 'STANDARD' | 'APPLICATION';
  product: string; customer: string | null; project_code: string | null; record_status: string;
  approval_no: string | null; approval_status: string | null; source_release_date: string | null;
  approval_progress?: {approved_steps: number; total_steps: number; current_step_order: number | null;
    current_role: string | null; closed: boolean} | null;
  supplied_artifacts: number; supplied_test_evidence: number};
type Receipt = {sample_only: boolean; initialized: boolean; import_event_no?: string; synthetic_approvals?: boolean;
  approval_routes?: unknown; items: Row[]};
type Query = Record<string, string | string[] | undefined>;
const pageSize = 10;
const roleLabels: Record<string, string> = {'电子工程师':'Electronics Engineer','电子经理':'Electronics Manager',
  '系统工程师':'Systems Engineer','研发总监':'R&D Director','应用工程师':'Application Engineer',
  '应用经理':'Application Manager','项目经理':'Project Manager'};
const roleLabel = (role: string) => roleLabels[role] || role;

// Interpret only the recorded sample projection, never current approval authority.
type RecordedStage = '1' | '2' | '3' | '4' | 'UNKNOWN';
const recordedRoutes = {
  STANDARD: ['电子工程师', '电子经理', '系统工程师', '研发总监'],
  APPLICATION: ['应用工程师', '应用经理', '系统工程师', '项目经理'],
} as const;
function recordedRoutesMatch(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return (['STANDARD', 'APPLICATION'] as const).every(type => {
    const roles = candidate[type];
    return Array.isArray(roles) && roles.length === recordedRoutes[type].length
      && roles.every((role, index) => role === recordedRoutes[type][index]);
  });
}
function parseRecordedStage(value: string | string[] | undefined): {stage: RecordedStage | ''; invalid: boolean} {
  if (value === undefined || value === '') return {stage: '', invalid: false};
  return typeof value === 'string' && ['1', '2', '3', '4', 'UNKNOWN'].includes(value)
    ? {stage: value as RecordedStage, invalid: false} : {stage: '', invalid: true};
}
function recordedApprovalStage(value: unknown, routesMatch = true): RecordedStage | 'CLOSED' {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return 'UNKNOWN';
  const row = value as Row;
  if ((row.release_type !== 'STANDARD' && row.release_type !== 'APPLICATION')
    || typeof row.approval_no !== 'string' || !row.approval_no.trim()) return 'UNKNOWN';
  const progress = row.approval_progress;
  if (!progress || typeof progress !== 'object' || Array.isArray(progress)
    || progress.total_steps !== 4 || !Number.isInteger(progress.approved_steps)
    || progress.approved_steps < 0 || progress.approved_steps > 4) return 'UNKNOWN';
  if (['APPROVED', 'RETURNED', 'REJECTED', 'CANCELLED'].includes(row.approval_status || '')) {
    return progress.closed === true && progress.current_step_order === null && progress.current_role === null
      ? 'CLOSED' : 'UNKNOWN';
  }
  if (!routesMatch) return 'UNKNOWN';
  const order = progress.current_step_order;
  if (row.approval_status !== 'PENDING' || progress.closed !== false
    || !Number.isInteger(order) || order === null || order < 1 || order > 4
    || progress.current_role !== recordedRoutes[row.release_type][order - 1]) return 'UNKNOWN';
  return String(order) as RecordedStage;
}

export default async function Page(props: {searchParams?: Promise<Query>}) {
  const query = await props?.searchParams || {};
  const single = (key: string) => typeof query[key] === 'string' ? query[key] as string : '';
  const {stage, invalid: invalidStage} = parseRecordedStage(query.stage);
  const search = single('q').trim();
  const words = search.toLowerCase().split(/\s+/u).filter(Boolean);
  const type = ['STANDARD', 'APPLICATION'].includes(single('type')) ? single('type') : '';
  const customer = single('customer');
  const statuses = ['APPROVED', 'PENDING', 'RETURNED', 'REJECTED', 'CANCELLED'];
  const status = [...statuses, 'UNRECORDED'].includes(single('status')) ? single('status') : '';
  const response = await apiGet<Receipt>('/api/v1/demo/zfi-import', {timeoutMs: 15000});
  const data = response?.sample_only === true && Array.isArray(response.items) ? response : null;
  const items = data?.initialized ? data.items : [];
  const routesMatch = recordedRoutesMatch(data?.approval_routes);
  const customers = [...new Set(items.map(row => row.customer).filter((value): value is string => value !== null && value !== ''))].sort();
  const matched = items.filter(row => (!stage || recordedApprovalStage(row, routesMatch) === stage) && (!type || row.release_type === type) && (!customer || row.customer === customer)
    && (!status || (status === 'UNRECORDED' ? row.approval_status === null : row.approval_status === status))
    && words.every(word => [row.version, row.source_ref, row.product, row.customer, row.project_code, row.release_id, row.approval_no]
      .some(value => typeof value === 'string' && value.toLowerCase().includes(word))));
  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize));
  const requestedPage = /^[1-9]\d{0,8}$/.test(single('page')) ? Number(single('page')) : 1;
  const page = Math.min(requestedPage, pageCount);
  const visible = matched.slice((page - 1) * pageSize, page * pageSize);
  function href(overrides: Partial<Record<'type' | 'customer' | 'status' | 'stage' | 'page', string>> = {}) {
    const values = {type, customer, status, stage, q: search, page: '1', ...overrides};
    const params = new URLSearchParams();
    for (const key of ['type', 'customer', 'status', 'stage', 'q', 'page'] as const) {
      if (values[key] && !(key === 'page' && values[key] === '1')) params.set(key, values[key]);
    }
    return '/demo/zfi' + (params.size ? '?' + params.toString() : '');
  }
  return <Localized>
    <div className="top"><div><h1><Localized>{'Excel demonstration overview'}</Localized></h1>
      <p className="muted"><Localized>{'Desensitized Excel records with synthetic approval history. Read-only; no real personnel approval or firmware delivery.'}</Localized></p></div></div>
    <p><Link href="/releases/standard"><Localized>{'Standard Releases'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/releases/application"><Localized>{'Application Releases'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/demo/releases"><Localized>{'Release evidence demonstration'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/demo/status" prefetch={false}><Localized>{'Demonstration status'}</Localized></Link></p>
    {!data ? <section className="panel"><h2><Localized>{'Excel import API unavailable'}</Localized></h2>
      <p><Localized>{'No sample evidence is fabricated when the API is unavailable.'}</Localized></p>
      <p className="muted"><Localized>{'The read is bounded and stops waiting when the API does not settle in time.'}</Localized></p>
      <p><a href="/demo/zfi"><Localized>{'Read again'}</Localized></a></p></section>
      : !data.initialized ? <section className="panel"><h2><Localized>{'Excel sample family incomplete or not installed'}</Localized></h2>
        <p><Localized>{'This overview requires the complete imported family. Partial records do not establish successful import.'}</Localized></p></section>
        : <>
          <section className="panel"><h2><Localized>{'Imported software records'}</Localized></h2>
            <p>SSR: {items.filter(r => r.release_type === 'STANDARD').length} <Localized>{' · '}</Localized>
              ASR: {items.filter(r => r.release_type === 'APPLICATION').length}</p>
            <p>{statuses.map(value => <span key={value}><Localized>{value}</Localized>: {items.filter(r => r.approval_status === value).length} <Localized>{' · '}</Localized></span>)}</p>
            <p className="muted"><Localized>{'All stages approved does not mean formally released'}</Localized></p>
            <p className="muted"><Localized>{'The import receipt is not current release readiness or a formal release decision. Open each release for current evidence.'}</Localized></p>
            <p className="muted"><Localized>{'Source dates are Excel metadata, not approval or deployment dates. Customer and project columns show the reviewed import mapping.'}</Localized></p>
            <p><Localized>{'Import event'}</Localized>: {data.import_event_no || '—'}</p>
          </section>
          {routesMatch ? <section className="panel"><h2><Localized>{'Approval progress'}</Localized></h2>
            <p><b><Localized>{'Standard Releases'}</Localized>:</b> {recordedRoutes.STANDARD.map((role, index) => <span key={role}><Localized>{roleLabel(role)}</Localized>{index < recordedRoutes.STANDARD.length - 1 ? ' → ' : ''}</span>)}</p>
            <p><b><Localized>{'Application Releases'}</Localized>:</b> {recordedRoutes.APPLICATION.map((role, index) => <span key={role}><Localized>{roleLabel(role)}</Localized>{index < recordedRoutes.APPLICATION.length - 1 ? ' → ' : ''}</span>)}</p>
            <p className="muted"><Localized>{'Workflow roles describe review stages; they do not prove configured job-role permissions.'}</Localized></p>
          </section> : <section className="panel"><h2><Localized>{'Recorded approval routes cannot be confirmed'}</Localized></h2>
            <p><Localized>{'Pending records are shown with an unconfirmed stage until both SSR and ASR routes match the recorded sample contract.'}</Localized></p>
          </section>}
          <section className="panel">
            <h2 id="zfi-filters"><Localized>{'Filter imported records'}</Localized></h2>
            <form className="zfi-search" action="/demo/zfi" method="get" role="search">
              <label htmlFor="zfi-search"><Localized>{'Search imported records'}</Localized>
                <input id="zfi-search" aria-describedby="zfi-search-help" name="q" type="search" defaultValue={search}/>
              </label>
              {type && <input type="hidden" name="type" value={type}/>}
              {customer && <input type="hidden" name="customer" value={customer}/>}
              {status && <input type="hidden" name="status" value={status}/>}
              {stage && <input type="hidden" name="stage" value={stage}/>}
              <button type="submit"><Localized>{'Search'}</Localized></button>
              <p id="zfi-search-help" className="muted"><Localized>{'Matches all words across version, Excel reference, software, customer, project, release UUID and approval number.'}</Localized></p>
            </form>
            <nav aria-labelledby="zfi-filters">
              <h3 id="zfi-type"><Localized>{'Release type'}</Localized></h3>
              <div className="actions zfi-filter-links" role="group" aria-labelledby="zfi-type">
                <Link href={href({type: ''})} aria-current={!type ? 'true' : undefined}><Localized>{'All release types'}</Localized></Link>
                {(['STANDARD', 'APPLICATION'] as const).map(value => <Link key={value} href={href({type: value})} aria-current={type === value ? 'true' : undefined}><Localized>{value === 'STANDARD' ? 'Standard Releases' : 'Application Releases'}</Localized></Link>)}
              </div>
              <h3 id="zfi-customer"><Localized>{'Customer'}</Localized></h3>
              <div className="actions zfi-filter-links" role="group" aria-labelledby="zfi-customer">
                <Link href={href({customer: ''})} aria-current={!customer ? 'true' : undefined}><Localized>{'All customers'}</Localized></Link>
                {customers.map(value => <Link key={value} href={href({customer: value})} aria-current={customer === value ? 'true' : undefined}>{value}</Link>)}
              </div>
              <h3 id="zfi-status"><Localized>{'Approval status'}</Localized></h3>
              <div className="actions zfi-filter-links" role="group" aria-labelledby="zfi-status">
                <Link href={href({status: ''})} aria-current={!status ? 'true' : undefined}><Localized>{'All approval statuses'}</Localized></Link>
                {[...statuses, 'UNRECORDED'].map(value => <Link key={value} href={href({status: value})} aria-current={status === value ? 'true' : undefined}><Localized>{value === 'UNRECORDED' ? 'Not recorded' : value}</Localized></Link>)}
              </div>
              <h3 id="zfi-stage"><Localized>{'Recorded pending stage'}</Localized></h3>
              <p id="zfi-stage-help" className="muted"><Localized>{'Recorded sample stages do not establish current frozen Snapshot binding, authorized tasks or formal release.'}</Localized></p>
              <p><b>SSR:</b> {recordedRoutes.STANDARD.map((role, index) => <span key={role}>{index + 1}. <Localized>{roleLabel(role)}</Localized>{index < 3 ? ' → ' : ''}</span>)}</p>
              <p><b>ASR:</b> {recordedRoutes.APPLICATION.map((role, index) => <span key={role}>{index + 1}. <Localized>{roleLabel(role)}</Localized>{index < 3 ? ' → ' : ''}</span>)}</p>
              <div className="actions zfi-filter-links" role="group" aria-labelledby="zfi-stage" aria-describedby="zfi-stage-help">
                <Link href={href({stage: ''})} aria-current={!stage ? 'true' : undefined}><Localized>{'All recorded stages'}</Localized></Link>
                {(['1', '2', '3', '4', 'UNKNOWN'] as const).map(value => <Link key={value} href={href({stage: value})} aria-current={stage === value ? 'true' : undefined}><Localized>{value === 'UNKNOWN' ? 'Stage cannot be confirmed' : 'Recorded pending stage'}</Localized>{value !== 'UNKNOWN' ? ` ${value}` : ''}</Link>)}
              </div>
              {invalidStage && <p role="status"><Localized>{'Invalid or repeated stage parameter. The stage filter was not applied; other filters remain in effect.'}</Localized></p>}
              <p><Link href="/demo/zfi"><Localized>{'Clear filters'}</Localized></Link></p>
            </nav>
            <p><Localized>{'Matched records'}</Localized>: {matched.length} <Localized>{' · '}</Localized> <Localized>{'Page'}</Localized>: {page} / {pageCount}</p>
            <p className="muted"><Localized>{'Summary counts describe the complete imported family; filters apply only to the records below.'}</Localized></p>
          </section>
          {visible.length === 0 ? <section className="panel"><h2><Localized>{'No imported records match these filters.'}</Localized></h2></section>
            : (['STANDARD', 'APPLICATION', 'UNKNOWN'] as const).filter(value => visible.some(row => value === 'UNKNOWN' ? !['STANDARD', 'APPLICATION'].includes(row.release_type) : row.release_type === value)).map(value => <section className="panel tablewrap zfi-table" key={value}>
            <h2><Localized>{value === 'UNKNOWN' ? 'Unrecognized release type' : value === 'STANDARD' ? 'Standard Releases' : 'Application Releases'}</Localized></h2>
            <table><thead><tr>{['Excel reference', 'Software', 'Version', 'Customer', 'Project code', 'Source release date', 'Record status', 'Approval', 'Approval progress', 'Supplied files / tests'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead>
              <tbody>{visible.filter(r => value === 'UNKNOWN' ? !['STANDARD', 'APPLICATION'].includes(r.release_type) : r.release_type === value).map(row => {
                const path = value === 'UNKNOWN' ? null : `/releases/${value === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(row.release_id)}`;
                return <tr key={row.release_id}><td>{row.source_ref}</td><td>{row.product}</td>
                  <td>{path ? <Link href={path}>{row.version}</Link> : row.version}</td><td>{row.customer || '—'}</td><td>{row.project_code || '—'}</td>
                  <td>{row.source_release_date || '—'}</td><td><Localized>{row.record_status}</Localized></td>
                  <td>{typeof row.approval_no === 'string' && row.approval_no ? <><Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}>{row.approval_no}</Link><br/><Localized>{typeof row.approval_status === 'string' ? row.approval_status : 'Not recorded'}</Localized></> : <Localized>{'Not recorded'}</Localized>}</td>
                  <td>{row.approval_progress && recordedApprovalStage(row, routesMatch) !== 'UNKNOWN' ? <><Localized>{'Approved stages'}</Localized>: {row.approval_progress.approved_steps} / {row.approval_progress.total_steps}
                    {row.approval_progress.current_role && <><br/><Localized>{'Current stage'}</Localized>: {row.approval_progress.current_step_order} · <Localized>{roleLabel(row.approval_progress.current_role)}</Localized></>}
                    {row.approval_progress.closed && row.approval_status && row.approval_status !== 'APPROVED' && <><br/><Localized>{'This approval request is closed.'}</Localized> <Localized>{row.approval_status}</Localized></>}</>
                    : <Localized>{row.approval_progress ? 'Stage cannot be confirmed' : 'Approval unavailable'}</Localized>}</td>
                  <td>{row.supplied_artifacts} / {row.supplied_test_evidence}</td></tr>;
              })}</tbody></table>
          </section>)}
          <section className="panel">
            <h2 id="zfi-pages"><Localized>{'Record pages'}</Localized></h2>
            <nav className="actions zfi-filter-links" aria-labelledby="zfi-pages">
              {page > 1 && <Link href={href({page: String(page - 1)})}><Localized>{'Previous page'}</Localized></Link>}
              {page < pageCount && <Link href={href({page: String(page + 1)})}><Localized>{'Next page'}</Localized></Link>}
            </nav>
          </section>
        </>}
  </Localized>;
}
