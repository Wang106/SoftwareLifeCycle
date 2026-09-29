import Link from 'next/link';
import { apiGet } from '../../lib/api';

type IssueRow = { id: string; issue_no: string; title: string; scope: string; severity: string; status: string };

export default async function Page() {
  const rows = await apiGet<IssueRow[]>('/api/v1/issues');
  return <>
    <div className="top"><div><div className="eyebrow">QUALITY &amp; IMPACT</div><h1>Issues</h1>
      <p className="muted">Review an issue's linked changes and candidate software releases.</p></div></div>
    {rows ? <section className="panel tablewrap"><table><thead><tr><th>Issue</th><th>Title</th><th>Scope</th><th>Severity</th><th>Status</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><td><Link href={`/issues/${encodeURIComponent(row.issue_no)}`}><b>#{row.issue_no}</b></Link></td>
        <td>{row.title}</td><td>{row.scope}</td><td>{row.severity}</td>
        <td><span className={'status ' + (row.status.includes('VERIFIED') || row.status === 'CLOSED' ? 'pass' : 'warning')}>{row.status.replaceAll('_', ' ')}</span></td>
      </tr>)}</tbody></table>{rows.length === 0 && <p className="muted">No issues recorded.</p>}</section>
      : <p className="datasource">Issue API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
