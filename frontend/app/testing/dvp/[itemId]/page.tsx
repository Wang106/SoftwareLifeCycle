import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Detail = {
  id: string; item_no: string; title: string; scope: string; status: string;
  plan: { plan_no: string; title: string; change_request_no: string | null } | null;
  executions: {
    execution_no: number; result: string; actual_result: string | null; executed_at: string;
    release_id: string; release_version: string | null; release_type: string | null; snapshot_id: string;
    snapshot_no: string | null; test_release_no: string | null;
  }[];
};

export default async function Page({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  const item = await apiGet<Detail>(`/api/v1/testing/dvp/id/${encodeURIComponent(itemId)}`);
  if (!item) return <section className="panel"><h1>DVP item unavailable</h1>
    <p className="muted">The item was not found or the API could not be reached.</p>
    <Link href="/testing/dvp">← All DVP items</Link></section>;
  return <>
    <div className="top"><div><div className="eyebrow">DVP TEST ITEM · {item.item_no}</div><h1>{item.title}</h1>
      <p className="muted">Recorded execution history, including earlier release snapshots.</p></div>
      <span className="status">{item.status}</span></div>
    <section className="panel"><h2>Verification scope</h2><div className="kv">
      <span>Item</span><b>{item.item_no}</b><span>Scope</span><b>{item.scope}</b>
      <span>Plan</span><b>{item.plan ? `${item.plan.plan_no} · ${item.plan.title}` : 'No plan found'}</b>
      <span>Change request</span><b>{item.plan?.change_request_no ? <Link href={`/changes/${encodeURIComponent(item.plan.change_request_no)}`}>{item.plan.change_request_no}</Link> : '—'}</b>
    </div></section>
    <section className="panel tablewrap"><h2>Execution history</h2>
      <p className="muted">Each row belongs to its own recorded release and snapshot. An earlier PASS does not verify a later snapshot.</p>
      <table><thead><tr><th>Execution</th><th>Result</th><th>Release</th><th>Snapshot</th><th>Test Release</th><th>Executed</th><th>Recorded Result</th></tr></thead>
        <tbody>{item.executions.map(row => <tr key={row.execution_no}>
          <td>#{row.execution_no}</td>
          <td><span className={'status ' + (row.result === 'PASS' ? 'pass' : 'warning')}>{row.result}</span></td>
          <td>{row.release_type === 'APPLICATION' ? <Link href={`/releases/application/${encodeURIComponent(row.release_id)}`}>ASR {row.release_version || row.release_id}</Link> : `${row.release_type || 'Release'} ${row.release_version || row.release_id}`}</td>
          <td>{row.snapshot_no || row.snapshot_id}</td><td>{row.test_release_no || '—'}</td>
          <td>{row.executed_at ? new Date(row.executed_at).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : '—'}</td>
          <td>{row.actual_result || '—'}</td>
        </tr>)}</tbody></table>
      {item.executions.length === 0 && <p className="muted">No executions recorded for this item.</p>}
    </section>
    <p className="datasource"><Link href="/testing/dvp">← All DVP items</Link></p>
  </>;
}
