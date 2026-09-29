import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type ReleaseReference = { release_id: string | null; version: string | null; snapshot_id: string | null; snapshot_no: string | null };
type BatchDetail = {
  id: string; batch_no: string; status: string; started_at: string | null; ended_at: string | null; note: string | null;
  software: ReleaseReference;
  deployment: { deployment_no: string; status: string; actual: ReleaseReference | null } | null;
  authorization: { authorization_no: string; status: string; batch_limit: number | null } | null;
  changeover: { changeover_no: string; status: string } | null;
  matches: { authorized_release: boolean | null; authorized_snapshot: boolean | null;
    deployed_release: boolean | null; deployed_snapshot: boolean | null; changeover_deployment: boolean | null };
};

function matchLabel(value: boolean | null): string {
  return value === null ? 'Not recorded' : value ? 'Match' : 'Mismatch';
}

function timeLabel(value: string | null): string {
  return value ? `${new Date(value).toISOString().slice(0, 16).replace('T', ' ')} UTC` : '—';
}

export default async function Page({ params }: { params: Promise<{ batchNo: string }> }) {
  const { batchNo } = await params;
  const batch = await apiGet<BatchDetail>(`/api/v1/batches/${encodeURIComponent(batchNo)}`);
  if (!batch) return <section className="panel"><h1>Batch unavailable</h1>
    <p className="muted">This batch was not found or the API is unavailable.</p>
    <Link href="/production/batches">← All batches</Link></section>;

  return <>
    <div className="top"><div><div className="eyebrow">PRODUCTION BATCH</div><h1>{batch.batch_no}</h1>
      <p className="muted">Software and authorization references for this recorded batch.</p></div>
      <span className={'status ' + (batch.status === 'ACTIVE' ? 'pass' : 'warning')}>{batch.status}</span></div>
    <div className="grid2">
      <section className="panel"><h2>Batch record</h2><div className="kv">
        <span>Release</span><b>{batch.software.version || '—'}</b>
        <span>Snapshot</span><b>{batch.software.snapshot_no || '—'}</b>
        <span>Started</span><b>{timeLabel(batch.started_at)}</b>
        <span>Ended</span><b>{timeLabel(batch.ended_at)}</b>
        <span>Note</span><b>{batch.note || '—'}</b>
      </div></section>
      <section className="panel"><h2>Production context</h2><div className="kv">
        <span>Deployment</span><b>{batch.deployment ? <Link href={`/deployments/${encodeURIComponent(batch.deployment.deployment_no)}`}>{batch.deployment.deployment_no} · {batch.deployment.status}</Link> : 'Missing deployment'}</b>
        <span>Actual software</span><b>{batch.deployment?.actual ? `${batch.deployment.actual.version || '—'} · ${batch.deployment.actual.snapshot_no || '—'}` : 'Not reported'}</b>
        <span>Authorization</span><b>{batch.authorization ? <Link href={`/distribution/authorizations/${encodeURIComponent(batch.authorization.authorization_no)}`}>{batch.authorization.authorization_no} · {batch.authorization.status}</Link> : 'Missing authorization'}</b>
        <span>Authorization batch limit</span><b>{batch.authorization?.batch_limit ?? 'No limit recorded'}</b>
        <span>Changeover</span><b>{batch.changeover ? `${batch.changeover.changeover_no} · ${batch.changeover.status}` : 'None linked'}</b>
      </div></section>
    </div>
    <section className="panel"><h2>Reference consistency</h2>
      <p className="muted">These checks compare recorded identifiers; they do not independently verify what was flashed on a production line.</p>
      <div className="kv">
        <span>Authorization release</span><b>{matchLabel(batch.matches.authorized_release)}</b>
        <span>Authorization snapshot</span><b>{matchLabel(batch.matches.authorized_snapshot)}</b>
        <span>Reported deployment release</span><b>{matchLabel(batch.matches.deployed_release)}</b>
        <span>Reported deployment snapshot</span><b>{matchLabel(batch.matches.deployed_snapshot)}</b>
        <span>Changeover deployment</span><b>{batch.changeover ? matchLabel(batch.matches.changeover_deployment) : 'No changeover linked'}</b>
      </div>
    </section>
    <p className="datasource"><Link href="/production/batches">← All batches</Link></p>
  </>;
}
