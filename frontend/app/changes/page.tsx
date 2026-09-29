import Link from 'next/link';
import { apiGet } from '../../lib/api';

type ChangeRow = { id: string; request_no: string; title: string; source: string; scope: string; change_type: string; status: string };

export default async function Page() {
  const rows = await apiGet<ChangeRow[]>('/api/v1/changes');
  return <>
    <div className="top"><div><div className="eyebrow">CHANGE CONTROL</div><h1>Software Change Requests</h1>
      <p className="muted">From approved requirement to verified software change and release traceability.</p></div></div>
    <div className="summary"><div><b>{rows?.length ?? '—'}</b><span>Visible SCR</span></div>
      <div><b>{rows ? rows.filter(row => row.status.includes('TEST')).length : '—'}</b><span>In Verification</span></div>
      <div><b>{rows ? rows.filter(row => row.status.includes('READY')).length : '—'}</b><span>Ready for Release</span></div></div>
    {rows ? <section className="panel tablewrap"><table><thead><tr><th>SCR</th><th>Title</th><th>Source</th><th>Scope</th><th>Type</th><th>Status</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><td><Link href={`/changes/${encodeURIComponent(row.request_no)}`}><b>{row.request_no}</b></Link></td>
        <td>{row.title}</td><td>{row.source}</td><td>{row.scope}</td><td>{row.change_type}</td>
        <td><span className={'status ' + (row.status.includes('READY') || row.status === 'RELEASED' ? 'pass' : 'warning')}>{row.status.replaceAll('_', ' ')}</span></td>
      </tr>)}</tbody></table>{rows.length === 0 && <p className="muted">No change requests recorded.</p>}</section>
      : <p className="datasource">Change request API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
