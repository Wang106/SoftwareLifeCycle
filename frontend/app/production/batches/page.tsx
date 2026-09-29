import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Batch = { id: string; batch_no: string; status: string; started_at: string | null };

export default async function Page() {
  const rows = await apiGet<Batch[]>('/api/v1/batches');
  return <>
    <div className="top"><div><div className="eyebrow">PRODUCTION TRACEABILITY</div><h1>Production Batches</h1>
      <p className="muted">Recorded batches linked to deployment and production authorization.</p></div>
      <Link href="/deployments">Deployments →</Link></div>
    <section className="panel tablewrap"><table><thead><tr><th>Batch</th><th>Started</th><th>Status</th></tr></thead>
      <tbody>{rows?.map(row => <tr key={row.id}>
        <td><Link href={`/production/batches/${encodeURIComponent(row.batch_no)}`}><b>{row.batch_no}</b></Link></td>
        <td>{row.started_at ? new Date(row.started_at).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : '—'}</td>
        <td><span className={'status ' + (row.status === 'ACTIVE' ? 'pass' : 'warning')}>{row.status}</span></td>
      </tr>)}</tbody></table>
      {rows?.length === 0 && <p className="muted">No production batches recorded.</p>}
    </section>
    {!rows && <p className="datasource">Batch API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
