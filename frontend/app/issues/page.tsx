
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';

type IssueRow = { id: string; issue_no: string; title: string; scope: string; severity: string; status: string };

export default async function Page() {
  const rows = await apiGet<IssueRow[]>('/api/v1/issues');
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"QUALITY & IMPACT"}</Localized></div><h1><Localized>{"Issues"}</Localized></h1>
      <p className="muted"><Localized>{"Review an issue's linked changes and candidate software releases."}</Localized></p></div></div>
    <Localized>{rows ? <section className="panel tablewrap"><table><thead><tr><th><Localized>{"Issue"}</Localized></th><th><Localized>{"Title"}</Localized></th><th><Localized>{"Scope"}</Localized></th><th><Localized>{"Severity"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead>
      <tbody><Localized>{rows.map(row => <tr key={row.id}><td><Link href={`/issues/${encodeURIComponent(row.issue_no)}`}><b><Localized>{"#"}</Localized><Localized>{row.issue_no}</Localized></b></Link></td>
        <td><Localized>{row.title}</Localized></td><td><Localized>{row.scope}</Localized></td><td><Localized>{row.severity}</Localized></td>
        <td><span className={'status ' + (row.status.includes('VERIFIED') || row.status === 'CLOSED' ? 'pass' : 'warning')}><Localized>{row.status.replaceAll('_', ' ')}</Localized></span></td>
      </tr>)}</Localized></tbody></table><Localized>{rows.length === 0 && <p className="muted"><Localized>{"No issues recorded."}</Localized></p>}</Localized></section>
      : <p className="datasource"><Localized>{"Issue API unavailable. Records will load when the backend is connected."}</Localized></p>}</Localized>
  </>;
}
