
import { Localized, LocalizedAttributes } from "../../../../components/localized";
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
  if (!batch) return <section className="panel"><h1><Localized>{"Batch unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"This batch was not found or the API is unavailable."}</Localized></p>
    <Link href="/production/batches"><Localized>{"← All batches"}</Localized></Link></section>;

  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"PRODUCTION BATCH"}</Localized></div><h1><Localized>{batch.batch_no}</Localized></h1>
      <p className="muted"><Localized>{"Software and authorization references for this recorded batch."}</Localized></p></div>
      <span className={'status ' + (batch.status === 'ACTIVE' ? 'pass' : 'warning')}><Localized>{batch.status}</Localized></span></div>
    <div className="grid2">
      <section className="panel"><h2><Localized>{"Batch record"}</Localized></h2><div className="kv">
        <span><Localized>{"Release"}</Localized></span><b><Localized>{batch.software.version || '—'}</Localized></b>
        <span><Localized>{"Snapshot"}</Localized></span><b><Localized>{batch.software.snapshot_no || '—'}</Localized></b>
        <span><Localized>{"Started"}</Localized></span><b><Localized>{timeLabel(batch.started_at)}</Localized></b>
        <span><Localized>{"Ended"}</Localized></span><b><Localized>{timeLabel(batch.ended_at)}</Localized></b>
        <span><Localized>{"Note"}</Localized></span><b><Localized>{batch.note || '—'}</Localized></b>
      </div></section>
      <section className="panel"><h2><Localized>{"Production context"}</Localized></h2><div className="kv">
        <span><Localized>{"Deployment"}</Localized></span><b><Localized>{batch.deployment ? <Link href={`/deployments/${encodeURIComponent(batch.deployment.deployment_no)}`}><Localized>{batch.deployment.deployment_no}</Localized><Localized>{" · "}</Localized><Localized>{batch.deployment.status}</Localized></Link> : 'Missing deployment'}</Localized></b>
        <span><Localized>{"Actual software"}</Localized></span><b><Localized>{batch.deployment?.actual ? `${batch.deployment.actual.version || '—'} · ${batch.deployment.actual.snapshot_no || '—'}` : 'Not reported'}</Localized></b>
        <span><Localized>{"Authorization"}</Localized></span><b><Localized>{batch.authorization ? <Link href={`/distribution/authorizations/${encodeURIComponent(batch.authorization.authorization_no)}`}><Localized>{batch.authorization.authorization_no}</Localized><Localized>{" · "}</Localized><Localized>{batch.authorization.status}</Localized></Link> : 'Missing authorization'}</Localized></b>
        <span><Localized>{"Authorization batch limit"}</Localized></span><b><Localized>{batch.authorization?.batch_limit ?? 'No limit recorded'}</Localized></b>
        <span><Localized>{"Changeover"}</Localized></span><b><Localized>{batch.changeover ? `${batch.changeover.changeover_no} · ${batch.changeover.status}` : 'None linked'}</Localized></b>
      </div></section>
    </div>
    <section className="panel"><h2><Localized>{"Reference consistency"}</Localized></h2>
      <p className="muted"><Localized>{"These checks compare recorded identifiers; they do not independently verify what was flashed on a production line."}</Localized></p>
      <div className="kv">
        <span><Localized>{"Authorization release"}</Localized></span><b><Localized>{matchLabel(batch.matches.authorized_release)}</Localized></b>
        <span><Localized>{"Authorization snapshot"}</Localized></span><b><Localized>{matchLabel(batch.matches.authorized_snapshot)}</Localized></b>
        <span><Localized>{"Reported deployment release"}</Localized></span><b><Localized>{matchLabel(batch.matches.deployed_release)}</Localized></b>
        <span><Localized>{"Reported deployment snapshot"}</Localized></span><b><Localized>{matchLabel(batch.matches.deployed_snapshot)}</Localized></b>
        <span><Localized>{"Changeover deployment"}</Localized></span><b><Localized>{batch.changeover ? matchLabel(batch.matches.changeover_deployment) : 'No changeover linked'}</Localized></b>
      </div>
    </section>
    <p className="datasource"><Link href="/production/batches"><Localized>{"← All batches"}</Localized></Link></p>
  </>;
}
