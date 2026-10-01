
import { Localized, LocalizedAttributes } from "../../../components/localized";
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
  if (!change) return <section className="panel"><h1><Localized>{"Change request unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The request was not found or the API could not be reached."}</Localized></p>
    <Link href="/changes"><Localized>{"← All change requests"}</Localized></Link></section>;
  return <>
    <p><Link href={`/resources?entity_type=SCR&entity_id=${change.id}`}><Localized>{"Materials & evidence references →"}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{"SOFTWARE CHANGE REQUEST · "}</Localized><Localized>{change.request_no}</Localized></div><h1><Localized>{change.title}</Localized></h1>
      <p className="muted"><Localized>{change.scope}</Localized><Localized>{" · "}</Localized><Localized>{change.change_type}</Localized><Localized>{" · Source: "}</Localized><Localized>{change.source}</Localized></p></div>
      <span className={'status ' + (change.status.includes('READY') || change.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{change.status.replaceAll('_', ' ')}</Localized></span></div>
    <div className="grid2"><section className="panel"><h2><Localized>{"Requirement"}</Localized></h2><p><Localized>{change.requirement || 'No requirement recorded.'}</Localized></p>
      <div className="kv"><span><Localized>{"Background"}</Localized></span><b><Localized>{change.background || '—'}</Localized></b>
        <span><Localized>{"Software"}</Localized></span><b><Localized>{change.software ? `${change.software.name} · ${change.software.code}` : '—'}</Localized></b>
        <span><Localized>{"Customer"}</Localized></span><b><Localized>{change.customer ? <Link href={`/customers/${encodeURIComponent(change.customer.code)}`}><Localized>{change.customer.name}</Localized></Link> : '—'}</Localized></b>
        <span><Localized>{"Project"}</Localized></span><b><Localized>{change.project ? <Link href={`/projects/${encodeURIComponent(change.project.id)}`}><Localized>{change.project.name}</Localized></Link> : '—'}</Localized></b>
      </div></section><section className="panel"><h2><Localized>{"Acceptance criteria"}</Localized></h2>
      <Localized>{change.acceptance_criteria.length ? <div className="timeline"><Localized>{change.acceptance_criteria.map(row => <div key={row.criterion_no}><b><Localized>{row.criterion_no}</Localized></b><span><Localized>{row.description}</Localized></span></div>)}</Localized></div> : <p className="muted"><Localized>{"No acceptance criteria recorded."}</Localized></p>}</Localized>
    </section></div>
    <section className="panel"><h2><Localized>{"Coverage review"}</Localized></h2><p><Localized>{"Review acceptance assignments, missing verification links, and execution evidence for a selected release and frozen snapshot."}</Localized></p><Link href={`/changes/${encodeURIComponent(id)}/coverage`}><Localized>{"Open completeness and coverage report →"}</Localized></Link></section>
    <section className="panel tablewrap"><h2><Localized>{"Linked issues"}</Localized></h2><table><thead><tr><th><Localized>{"Issue"}</Localized></th><th><Localized>{"Title"}</Localized></th><th><Localized>{"Relation"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead>
      <tbody><Localized>{change.issues.map(row => <tr key={`${row.issue_no}-${row.relation_type}`}><td><Link href={`/issues/${encodeURIComponent(row.issue_no)}`}><b><Localized>{"#"}</Localized><Localized>{row.issue_no}</Localized></b></Link></td>
        <td><Localized>{row.title}</Localized></td><td><Localized>{row.relation_type}</Localized></td><td><Localized>{row.status}</Localized></td></tr>)}</Localized></tbody></table>
      <Localized>{change.issues.length === 0 && <p className="muted"><Localized>{"No issue linked to this request."}</Localized></p>}</Localized>
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Change points & linked DVP items"}</Localized></h2>
      <p className="muted"><Localized>{"A link to a DVP item is a verification assignment; its execution history is shown on the item page."}</Localized></p>
      <table><thead><tr><th><Localized>{"Change Point"}</Localized></th><th><Localized>{"Description"}</Localized></th><th><Localized>{"Status"}</Localized></th><th><Localized>{"Linked DVP"}</Localized></th></tr></thead>
        <tbody><Localized>{change.change_points.map(point => <tr key={point.change_no}><td><b><Localized>{point.change_no}</Localized><Localized>{" · "}</Localized><Localized>{point.title}</Localized></b></td>
          <td><Localized>{point.description || '—'}</Localized></td><td><Localized>{point.status}</Localized></td>
          <td><Localized>{point.dvp_items.length ? point.dvp_items.map((item, index) => <span key={item.id}><Localized>{index > 0 ? ', ' : ''}</Localized><Link href={`/testing/dvp/${encodeURIComponent(item.id)}`}><Localized>{item.item_no}</Localized></Link></span>) : '—'}</Localized></td>
        </tr>)}</Localized></tbody></table><Localized>{change.change_points.length === 0 && <p className="muted"><Localized>{"No change points recorded."}</Localized></p>}</Localized>
    </section>
    <section className="panel tablewrap"><h2><Localized>{"DVP plans"}</Localized></h2><table><thead><tr><th><Localized>{"Plan"}</Localized></th><th><Localized>{"Status"}</Localized></th><th><Localized>{"Test items"}</Localized></th></tr></thead>
      <tbody><Localized>{change.dvp_plans.map(plan => <tr key={plan.plan_no}><td><b><Localized>{plan.plan_no}</Localized></b><Localized>{" · "}</Localized><Localized>{plan.title}</Localized></td><td><Localized>{plan.status}</Localized></td>
        <td><Localized>{plan.items.length ? plan.items.map((item, index) => <span key={item.id}><Localized>{index > 0 ? ', ' : ''}</Localized><Link href={`/testing/dvp/${encodeURIComponent(item.id)}`}><Localized>{item.item_no}</Localized></Link></span>) : 'No items'}</Localized></td></tr>)}</Localized></tbody></table>
      <Localized>{change.dvp_plans.length === 0 && <p className="muted"><Localized>{"No DVP plan recorded."}</Localized></p>}</Localized>
    </section><p className="datasource"><Link href="/changes"><Localized>{"← All change requests"}</Localized></Link></p>
  </>;
}
