import Link from 'next/link';
import {apiGet} from '../../../lib/api';
import {Localized} from '../../../components/localized';

type Row = {source_ref: string; release_id: string; version: string; release_type: 'STANDARD' | 'APPLICATION';
  product: string; customer: string | null; project_code: string | null; record_status: string;
  approval_no: string | null; approval_status: string | null; source_release_date: string | null;
  supplied_artifacts: number; supplied_test_evidence: number};
type Receipt = {sample_only: boolean; initialized: boolean; import_event_no?: string; synthetic_approvals?: boolean; items: Row[]};

export default async function Page() {
  const response = await apiGet<Receipt>('/api/v1/demo/zfi-import');
  const data = response?.sample_only === true && Array.isArray(response.items) ? response : null;
  const items = data?.initialized ? data.items : [];
  const statuses = ['APPROVED', 'PENDING', 'RETURNED', 'REJECTED'];
  return <Localized>
    <div className="top"><div><h1><Localized>{'Excel demonstration overview'}</Localized></h1>
      <p className="muted"><Localized>{'Desensitized Excel records with synthetic approval history. Read-only; no real personnel approval or firmware delivery.'}</Localized></p></div></div>
    <p><Link href="/releases/standard"><Localized>{'Standard Releases'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/releases/application"><Localized>{'Application Releases'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/demo/releases"><Localized>{'Release evidence demonstration'}</Localized></Link></p>
    {!data ? <section className="panel"><h2><Localized>{'Excel import API unavailable'}</Localized></h2>
      <p><Localized>{'No sample evidence is fabricated when the API is unavailable.'}</Localized></p></section>
      : !data.initialized ? <section className="panel"><h2><Localized>{'Excel sample family incomplete or not installed'}</Localized></h2>
        <p><Localized>{'This overview requires the complete imported family. Partial records do not establish successful import.'}</Localized></p></section>
        : <>
          <section className="panel"><h2><Localized>{'Imported software records'}</Localized></h2>
            <p>SSR: {items.filter(r => r.release_type === 'STANDARD').length} <Localized>{' · '}</Localized>
              ASR: {items.filter(r => r.release_type === 'APPLICATION').length}</p>
            <p>{statuses.map(status => <span key={status}><Localized>{status}</Localized>: {items.filter(r => r.approval_status === status).length} <Localized>{' · '}</Localized></span>)}</p>
            <p className="muted"><Localized>{'All stages approved does not mean formally released'}</Localized></p>
            <p className="muted"><Localized>{'The import receipt is not current release readiness or a formal release decision. Open each release for current evidence.'}</Localized></p>
            <p className="muted"><Localized>{'Source dates are Excel metadata, not approval or deployment dates. Customer and project columns show the reviewed import mapping.'}</Localized></p>
            <p><Localized>{'Import event'}</Localized>: {data.import_event_no || '—'}</p>
          </section>
          {(['STANDARD', 'APPLICATION'] as const).map(type => <section className="panel tablewrap" key={type}>
            <h2><Localized>{type === 'STANDARD' ? 'Standard Releases' : 'Application Releases'}</Localized></h2>
            <table><thead><tr>{['Excel reference', 'Software', 'Version', 'Customer', 'Project code', 'Source release date', 'Record status', 'Approval', 'Supplied files / tests'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead>
              <tbody>{items.filter(r => r.release_type === type).map(row => {
                const path = `/releases/${type === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(row.release_id)}`;
                return <tr key={row.release_id}><td>{row.source_ref}</td><td>{row.product}</td>
                  <td><Link href={path}>{row.version}</Link></td><td>{row.customer || '—'}</td><td>{row.project_code || '—'}</td>
                  <td>{row.source_release_date || '—'}</td><td><Localized>{row.record_status}</Localized></td>
                  <td>{row.approval_no ? <><Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}>{row.approval_no}</Link><br/><Localized>{row.approval_status || 'Not recorded'}</Localized></> : <Localized>{'Not recorded'}</Localized>}</td>
                  <td>{row.supplied_artifacts} / {row.supplied_test_evidence}</td></tr>;
              })}</tbody></table>
          </section>)}
        </>}
  </Localized>;
}
