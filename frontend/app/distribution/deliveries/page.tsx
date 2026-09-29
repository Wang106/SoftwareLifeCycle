import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Delivery = {
  id: string; package_no: string; revision: number; release_id: string; snapshot_id: string;
  recipient_type: string; recipient_code: string; purpose: string; status: string;
};

export default async function Page() {
  const deliveries = await apiGet<Delivery[]>('/api/v1/deliveries');
  return <>
    <div className="top"><div><div className="eyebrow">DELIVERY & DISTRIBUTION</div><h1>Delivery Packages</h1>
      <p className="muted">Recipient-specific packages. Each revision is a separate record tied to a frozen snapshot.</p></div></div>
    <section className="panel tablewrap"><table><thead><tr><th>Package</th><th>Recipient</th><th>Purpose</th><th>Status</th></tr></thead>
      <tbody>{deliveries?.map(row => <tr key={row.id}>
        <td><Link href={`/distribution/deliveries/${encodeURIComponent(row.package_no)}/${row.revision}`}><b>{row.package_no} Rev{row.revision}</b></Link></td>
        <td>{row.recipient_type} · {row.recipient_code}</td><td>{row.purpose}</td>
        <td><span className={'status ' + (row.status === 'DISTRIBUTED' ? 'pass' : 'warning')}>{row.status}</span></td>
      </tr>)}</tbody></table>
      {deliveries?.length === 0 && <p className="muted">No delivery packages recorded.</p>}
    </section>
    {!deliveries && <p className="datasource">Delivery API unavailable. The list will load when the backend is connected.</p>}
  </>;
}
