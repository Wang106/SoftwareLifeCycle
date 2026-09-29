import Link from 'next/link';
import { apiGet } from '../../lib/api';

type Approval = { id: string; approval_no: string; target_type: string; target_id: string;
  snapshot_id: string | null; status: string; submitted_by: string | null };

export default async function Page() {
  const rows = await apiGet<Approval[]>('/api/v1/approvals');
  return <>
    <div className="top"><div><div className="eyebrow">GOVERNANCE</div><h1>Approvals</h1>
      <p className="muted">Recorded approval requests, frozen targets and decision history.</p></div></div>
    <div className="cards">
      <div className="card"><span className="muted">PENDING</span><div className="metric">{rows ? rows.filter(row => row.status === 'PENDING').length : '—'}</div></div>
      <div className="card"><span className="muted">APPROVED</span><div className="metric">{rows ? rows.filter(row => row.status === 'APPROVED').length : '—'}</div></div>
      <div className="card"><span className="muted">RETURNED</span><div className="metric">{rows ? rows.filter(row => row.status === 'RETURNED').length : '—'}</div></div>
      <div className="card"><span className="muted">TOTAL</span><div className="metric">{rows?.length ?? '—'}</div></div>
    </div>
    {rows ? <section className="panel tablewrap"><table><thead><tr><th>Approval</th><th>Type</th><th>Snapshot-bound</th><th>Status</th><th>Submitted By</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><td><Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}><b>{row.approval_no}</b></Link></td>
        <td>{row.target_type}</td><td>{row.snapshot_id ? 'YES' : 'NO'}</td>
        <td><span className={'status ' + (row.status === 'APPROVED' ? 'pass' : 'warning')}>{row.status}</span></td>
        <td>{row.submitted_by || '—'}</td>
      </tr>)}</tbody></table>{rows.length === 0 && <p className="muted">No approval requests recorded.</p>}</section>
      : <p className="datasource">Approval API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
