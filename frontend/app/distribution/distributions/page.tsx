import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Distribution = {
  id: string; distribution_no: string; delivery_package_id: string;
  recipient_type: string; recipient_code: string; status: string;
};

export default async function Page() {
  const rows = await apiGet<Distribution[]>('/api/v1/distributions');
  return <>
    <div className="top"><div><div className="eyebrow">DELIVERY & DISTRIBUTION</div><h1>Distribution Records</h1>
      <p className="muted">Track each package sent to a recipient and its acknowledgment status.</p></div>
      <Link href="/distribution/deliveries">Delivery packages →</Link></div>
    <section className="panel tablewrap"><table><thead><tr><th>Distribution</th><th>Recipient</th><th>Status</th></tr></thead>
      <tbody>{rows?.map(row => <tr key={row.id}>
        <td><Link href={`/distribution/distributions/${encodeURIComponent(row.distribution_no)}`}><b>{row.distribution_no}</b></Link></td>
        <td>{row.recipient_type} · {row.recipient_code}</td>
        <td><span className={'status ' + (row.status === 'ACKNOWLEDGED' ? 'pass' : 'warning')}>{row.status}</span></td>
      </tr>)}</tbody></table>
      {rows?.length === 0 && <p className="muted">No distribution records found.</p>}
    </section>
    {!rows && <p className="datasource">Distribution API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
