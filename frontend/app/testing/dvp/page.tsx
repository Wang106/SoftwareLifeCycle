import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type DvpRow = {
  id: string; item_no: string; title: string; scope: string; status: string;
  latest_result: string | null; latest_execution_no: number | null; snapshot_id: string | null;
};

export default async function Page() {
  const rows = await apiGet<DvpRow[]>('/api/v1/testing/dvp');
  const pass = rows?.filter(row => row.latest_result === 'PASS').length ?? 0;
  const executed = rows?.filter(row => row.latest_execution_no !== null).length ?? 0;
  const retested = rows?.filter(row => (row.latest_execution_no ?? 0) > 1).length ?? 0;
  return <>
    <div className="top"><div><div className="eyebrow">VERIFICATION</div><h1>DVP &amp; Test Execution</h1>
      <p className="muted">Open a test item to inspect its execution history and exact release snapshot.</p></div></div>
    <div className="cards">
      <div className="card"><span className="muted">TEST ITEMS</span><div className="metric">{rows?.length ?? '—'}</div></div>
      <div className="card"><span className="muted">LATEST RESULT PASS</span><div className="metric">{rows ? `${pass} / ${executed}` : '—'}</div><small>Across items with an execution</small></div>
      <div className="card"><span className="muted">RETESTED ITEMS</span><div className="metric">{rows ? retested : '—'}</div><small>More than one recorded execution</small></div>
    </div>
    {rows ? <section className="panel tablewrap"><table><thead><tr><th>DVP</th><th>Test Item</th><th>Scope</th><th>Status</th><th>Latest Result</th><th>Execution</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}>
        <td><Link href={`/testing/dvp/${encodeURIComponent(row.id)}`}><b>{row.item_no}</b></Link></td>
        <td>{row.title}</td><td>{row.scope}</td><td>{row.status}</td>
        <td>{row.latest_result ? <span className={'status ' + (row.latest_result === 'PASS' ? 'pass' : 'warning')}>{row.latest_result}</span> : '—'}</td>
        <td>{row.latest_execution_no !== null ? `#${row.latest_execution_no}` : '—'}</td>
      </tr>)}</tbody></table>
      {rows.length === 0 && <p className="muted">No DVP items recorded.</p>}
    </section> : <p className="datasource">DVP API unavailable. Test records will load when the backend is connected.</p>}
  </>;
}
