import Link from 'next/link';
import { apiGet } from '../../../../lib/api';
import { DeploymentDetail } from '../../../../lib/production';

export const dynamic = 'force-dynamic';

type SiteDetail = {
  id: string;
  site_code: string;
  name: string;
  region: string | null;
  status: string;
  customer: { code: string; name: string } | null;
  project: { code: string; name: string } | null;
  lines: { id: string; line_code: string; name: string; status: string; deployment: DeploymentDetail | null }[];
};

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const site = await apiGet<SiteDetail>('/api/v1/manufacturing/sites/' + encodeURIComponent(id));
  if (!site) return <section className="panel"><h1>Manufacturing site unavailable</h1><p className="muted">This site was not found or the API is unavailable. No substitute production data is shown.</p><Link href="/manufacturing/sites">← All manufacturing sites</Link></section>;
  const activeAuthorizationCount = site.lines.filter(line => line.deployment?.authorization?.status === 'APPROVED').length;
  const currentBatch = site.lines.flatMap(line => line.deployment?.batches || [])[0];
  const allMatch = site.lines.length > 0 && site.lines.every(line => line.deployment?.status === 'MATCH');

  return <>
    <div className="top"><div><div className="eyebrow">MANUFACTURING SITE · {site.site_code}</div><h1>{site.name}</h1><p className="muted">Production software control · {site.customer?.name || 'Customer'} / {site.project?.name || 'Project'}</p></div><span className={'status ' + (site.status === 'ACTIVE' ? 'pass' : 'warning')}>{site.status}</span></div>
    <div className="cards"><div className="card"><span className="muted">PRODUCTION LINES</span><div className="metric">{site.lines.length}</div><small>{site.lines.map(line => line.name).join(', ') || 'None'}</small></div><div className="card"><span className="muted">ACTIVE AUTHORIZATION</span><div className="metric">{activeAuthorizationCount}</div><small>{site.lines[0]?.deployment?.authorization?.authorization_no || 'None'}</small></div><div className="card"><span className="muted">CURRENT BATCH</span><div className="metric">{currentBatch?.batch_no || '—'}</div><small>{currentBatch?.note || 'No active batch'}</small></div><div className="card"><span className="muted">SOFTWARE MATCH</span><div className="metric">{allMatch ? 'MATCH' : 'CHECK'}</div><small>{site.lines[0]?.deployment?.expected.version ? `ASR ${site.lines[0].deployment.expected.version}` : 'No deployment'}</small></div></div>
    <section className="panel tablewrap"><h2>Line software status</h2><table><thead><tr><th>Line</th><th>Expected</th><th>Actual</th><th>Authorization</th><th>Match</th></tr></thead><tbody>{site.lines.map(line => <tr key={line.id}><td><b>{line.name}</b><div className="muted">{line.line_code} · {line.status}</div></td><td>{line.deployment ? `ASR ${line.deployment.expected.version} · ${line.deployment.expected.snapshot_no}` : '—'}</td><td>{line.deployment?.actual ? `ASR ${line.deployment.actual.version} · ${line.deployment.actual.snapshot_no}` : 'Not reported'}</td><td>{line.deployment?.authorization?.authorization_no || '—'}</td><td><span className={'status ' + (line.deployment?.status === 'MATCH' ? 'pass' : 'warning')}>{line.deployment?.status || 'NOT DEPLOYED'}</span></td></tr>)}</tbody></table>{site.lines.length === 0 && <p className="muted">No production lines recorded for this site.</p>}</section>
    <section className="panel"><div className="sectiontitle"><h2>Production history</h2><Link href="/deployments">Open deployments →</Link></div><div className="timeline"><div><b>{site.lines[0]?.deployment?.authorization?.authorization_no || 'Authorization pending'}</b><span>Production scope approved</span></div><div><b>{site.lines[0]?.deployment?.changeovers[0]?.changeover_no || 'Changeover pending'}</b><span>Authorized software changeover</span></div><div><b>{currentBatch?.batch_no || 'Batch pending'}</b><span>{currentBatch?.status || 'No active batch'}</span></div></div></section>
    <p className="datasource"><Link href="/manufacturing/sites">← All manufacturing sites</Link></p>
  </>;
}
