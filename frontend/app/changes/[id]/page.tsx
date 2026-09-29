import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type ChangeDetail = {
  id: string; request_no: string; title: string; source: string; scope: string; change_type: string;
  status: string; background: string | null; requirement: string | null; created_at: string;
  software: { code: string; name: string } | null;
  customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  acceptance_criteria: { criterion_no: string; description: string }[];
  issues: { issue_no: string; title: string; relation_type: string; status: string }[];
  change_points: { change_no: string; title: string; description: string | null; status: string; dvp_items: { id: string; item_no: string }[] }[];
  dvp_plans: { plan_no: string; title: string; status: string; items: { id: string; item_no: string; title: string; status: string }[] }[];
};

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const change = await apiGet<ChangeDetail>(`/api/v1/changes/${encodeURIComponent(id)}`);
  if (!change) return <section className="panel"><h1>Change request unavailable</h1>
    <p className="muted">The request was not found or the API could not be reached.</p>
    <Link href="/changes">← All change requests</Link></section>;
  return <>
    <div className="top"><div><div className="eyebrow">SOFTWARE CHANGE REQUEST · {change.request_no}</div><h1>{change.title}</h1>
      <p className="muted">{change.scope} · {change.change_type} · Source: {change.source}</p></div>
      <span className={'status ' + (change.status.includes('READY') || change.status === 'RELEASED' ? 'pass' : 'warning')}>{change.status.replaceAll('_', ' ')}</span></div>
    <div className="grid2"><section className="panel"><h2>Requirement</h2><p>{change.requirement || 'No requirement recorded.'}</p>
      <div className="kv"><span>Background</span><b>{change.background || '—'}</b>
        <span>Software</span><b>{change.software ? `${change.software.name} · ${change.software.code}` : '—'}</b>
        <span>Customer</span><b>{change.customer ? <Link href={`/customers/${encodeURIComponent(change.customer.code)}`}>{change.customer.name}</Link> : '—'}</b>
        <span>Project</span><b>{change.project ? <Link href={`/projects/${encodeURIComponent(change.project.id)}`}>{change.project.name}</Link> : '—'}</b>
      </div></section><section className="panel"><h2>Acceptance criteria</h2>
      {change.acceptance_criteria.length ? <div className="timeline">{change.acceptance_criteria.map(row => <div key={row.criterion_no}><b>{row.criterion_no}</b><span>{row.description}</span></div>)}</div> : <p className="muted">No acceptance criteria recorded.</p>}
    </section></div>
    <section className="panel tablewrap"><h2>Linked issues</h2><table><thead><tr><th>Issue</th><th>Title</th><th>Relation</th><th>Status</th></tr></thead>
      <tbody>{change.issues.map(row => <tr key={`${row.issue_no}-${row.relation_type}`}><td><Link href={`/issues/${encodeURIComponent(row.issue_no)}`}><b>#{row.issue_no}</b></Link></td>
        <td>{row.title}</td><td>{row.relation_type}</td><td>{row.status}</td></tr>)}</tbody></table>
      {change.issues.length === 0 && <p className="muted">No issue linked to this request.</p>}
    </section>
    <section className="panel tablewrap"><h2>Change points &amp; linked DVP items</h2>
      <p className="muted">A link to a DVP item is a verification assignment; its execution history is shown on the item page.</p>
      <table><thead><tr><th>Change Point</th><th>Description</th><th>Status</th><th>Linked DVP</th></tr></thead>
        <tbody>{change.change_points.map(point => <tr key={point.change_no}><td><b>{point.change_no} · {point.title}</b></td>
          <td>{point.description || '—'}</td><td>{point.status}</td>
          <td>{point.dvp_items.length ? point.dvp_items.map((item, index) => <span key={item.id}>{index > 0 ? ', ' : ''}<Link href={`/testing/dvp/${encodeURIComponent(item.id)}`}>{item.item_no}</Link></span>) : '—'}</td>
        </tr>)}</tbody></table>{change.change_points.length === 0 && <p className="muted">No change points recorded.</p>}
    </section>
    <section className="panel tablewrap"><h2>DVP plans</h2><table><thead><tr><th>Plan</th><th>Status</th><th>Test items</th></tr></thead>
      <tbody>{change.dvp_plans.map(plan => <tr key={plan.plan_no}><td><b>{plan.plan_no}</b> · {plan.title}</td><td>{plan.status}</td>
        <td>{plan.items.length ? plan.items.map((item, index) => <span key={item.id}>{index > 0 ? ', ' : ''}<Link href={`/testing/dvp/${encodeURIComponent(item.id)}`}>{item.item_no}</Link></span>) : 'No items'}</td></tr>)}</tbody></table>
      {change.dvp_plans.length === 0 && <p className="muted">No DVP plan recorded.</p>}
    </section><p className="datasource"><Link href="/changes">← All change requests</Link></p>
  </>;
}
