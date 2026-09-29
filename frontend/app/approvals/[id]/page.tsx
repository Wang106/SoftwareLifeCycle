import Link from 'next/link';
import { apiGet } from '../../../lib/api';

type ApprovalDetail = {
  id: string; approval_no: string; target_type: string; target_id: string;
  status: string; submitted_by: string | null;
  target: { release_type: string | null; release_version: string | null;
    snapshot_no: string | null; content_hash: string | null };
  steps: { id: string; step_order: number; role_name: string; approver_name: string | null; status: string }[];
  actions: { id: string; step_id: string | null; actor_name: string; action: string; comment: string | null }[];
};

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const approval = await apiGet<ApprovalDetail>(`/api/v1/approvals/${encodeURIComponent(id)}`);
  if (!approval) return <section className="panel"><h1>Approval unavailable</h1>
    <p className="muted">The approval was not found or the API could not be reached.</p>
    <Link href="/approvals">← All approvals</Link></section>;
  const roles = new Map(approval.steps.map(step => [step.id, step.role_name]));
  return <>
    <div className="top"><div><div className="eyebrow">APPROVAL · {approval.approval_no}</div>
      <h1>{approval.target_type} Approval · {approval.target.release_version || approval.target_id}</h1>
      <p className="muted">{approval.target.snapshot_no ? `Bound to ${approval.target.snapshot_no}` : 'No snapshot recorded'}</p></div>
      <span className={'status ' + (approval.status === 'APPROVED' ? 'pass' : 'warning')}>{approval.status}</span></div>
    <div className="grid2"><section className="panel"><h2>Target</h2><div className="kv">
      <span>Target type</span><b>{approval.target_type}</b>
      <span>Release</span><b>{approval.target.release_type === 'APPLICATION' ? <Link href={`/releases/application/${encodeURIComponent(approval.target_id)}`}>ASR {approval.target.release_version || approval.target_id}</Link> : approval.target.release_version || '—'}</b>
      <span>Snapshot</span><b>{approval.target.snapshot_no || '—'}</b>
      <span>Submitted by</span><b>{approval.submitted_by || '—'}</b>
    </div></section><section className="panel"><h2>Recorded snapshot hash</h2>
      <p className="muted">This hash identifies the snapshot referenced by the approval. It does not independently recheck the stored files.</p>
      <code className="hash">{approval.target.content_hash || 'No snapshot hash recorded'}</code>
    </section></div>
    <section className="panel"><h2>Approval steps</h2>{approval.steps.length ? <div className="approvalsteps">
      {approval.steps.map(step => <div key={step.id} className={step.status === 'APPROVED' ? 'done' : step.status === 'PENDING' ? 'current' : ''}>
        <b>{step.step_order} · {step.role_name}</b><span>{step.status}{step.approver_name ? ` · ${step.approver_name}` : ''}</span>
      </div>)}</div> : <p className="muted">No approval steps recorded.</p>}</section>
    <section className="panel tablewrap"><h2>Decision history</h2><table><thead><tr><th>Step</th><th>Actor</th><th>Action</th><th>Comment</th></tr></thead>
      <tbody>{approval.actions.map(action => <tr key={action.id}>
        <td>{action.step_id ? roles.get(action.step_id) || 'Unknown step' : 'General'}</td><td>{action.actor_name}</td>
        <td><span className={'status ' + (action.action === 'APPROVED' ? 'pass' : 'warning')}>{action.action}</span></td>
        <td>{action.comment || '—'}</td>
      </tr>)}</tbody></table>{approval.actions.length === 0 && <p className="muted">No decision action recorded.</p>}</section>
    <p className="datasource"><Link href="/approvals">← All approvals</Link></p>
  </>;
}
