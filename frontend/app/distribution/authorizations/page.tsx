import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type Authorization = {
  id: string; authorization_no: string; distribution_id: string | null;
  site_code: string; line_code: string; purpose: string; status: string;
  batch_limit: number | null;
};

export default async function Page() {
  const rows = await apiGet<Authorization[]>('/api/v1/authorizations');
  return <>
    <div className="top"><div><div className="eyebrow">PRODUCTION GOVERNANCE</div><h1>Production Authorizations</h1>
      <p className="muted">Approved software scope by site and line, with a direct link to the underlying distribution.</p></div>
      <Link href="/distribution/distributions">Distribution records →</Link></div>
    <section className="panel tablewrap"><table><thead><tr><th>Authorization</th><th>Site / line</th><th>Purpose</th><th>Batch limit</th><th>Status</th></tr></thead>
      <tbody>{rows?.map(row => <tr key={row.id}>
        <td><Link href={`/distribution/authorizations/${encodeURIComponent(row.authorization_no)}`}><b>{row.authorization_no}</b></Link></td>
        <td>{row.site_code} / {row.line_code}</td><td>{row.purpose}</td>
        <td>{row.batch_limit ?? 'No limit recorded'}</td>
        <td><span className={'status ' + (row.status === 'APPROVED' ? 'pass' : 'warning')}>{row.status}</span></td>
      </tr>)}</tbody></table>
      {rows?.length === 0 && <p className="muted">No production authorizations recorded.</p>}
    </section>
    {!rows && <p className="datasource">Authorization API unavailable. Records will load when the backend is connected.</p>}
  </>;
}
