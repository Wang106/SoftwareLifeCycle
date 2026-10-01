
import { Localized, LocalizedAttributes } from "../../../../components/localized";
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
  if (!site) return <section className="panel"><h1><Localized>{"Manufacturing site unavailable"}</Localized></h1><p className="muted"><Localized>{"This site was not found or the API is unavailable. No substitute production data is shown."}</Localized></p><Link href="/manufacturing/sites"><Localized>{"← All manufacturing sites"}</Localized></Link></section>;
  const activeAuthorizationCount = site.lines.filter(line => line.deployment?.authorization?.status === 'APPROVED').length;
  const currentBatch = site.lines.flatMap(line => line.deployment?.batches || [])[0];
  const allMatch = site.lines.length > 0 && site.lines.every(line => line.deployment?.status === 'MATCH');

  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"MANUFACTURING SITE · "}</Localized><Localized>{site.site_code}</Localized></div><h1><Localized>{site.name}</Localized></h1><p className="muted"><Localized>{"Production software control · "}</Localized><Localized>{site.customer?.name || 'Customer'}</Localized><Localized>{" / "}</Localized><Localized>{site.project?.name || 'Project'}</Localized></p></div><span className={'status ' + (site.status === 'ACTIVE' ? 'pass' : 'warning')}><Localized>{site.status}</Localized></span></div>
    <div className="cards"><div className="card"><span className="muted"><Localized>{"PRODUCTION LINES"}</Localized></span><div className="metric"><Localized>{site.lines.length}</Localized></div><small><Localized>{site.lines.map(line => line.name).join(', ') || 'None'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"ACTIVE AUTHORIZATION"}</Localized></span><div className="metric"><Localized>{activeAuthorizationCount}</Localized></div><small><Localized>{site.lines[0]?.deployment?.authorization?.authorization_no || 'None'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"CURRENT BATCH"}</Localized></span><div className="metric"><Localized>{currentBatch?.batch_no || '—'}</Localized></div><small><Localized>{currentBatch?.note || 'No active batch'}</Localized></small></div><div className="card"><span className="muted"><Localized>{"SOFTWARE MATCH"}</Localized></span><div className="metric"><Localized>{allMatch ? 'MATCH' : 'CHECK'}</Localized></div><small><Localized>{site.lines[0]?.deployment?.expected.version ? `ASR ${site.lines[0].deployment.expected.version}` : 'No deployment'}</Localized></small></div></div>
    <section className="panel tablewrap"><h2><Localized>{"Line software status"}</Localized></h2><table><thead><tr><th><Localized>{"Line"}</Localized></th><th><Localized>{"Expected"}</Localized></th><th><Localized>{"Actual"}</Localized></th><th><Localized>{"Authorization"}</Localized></th><th><Localized>{"Match"}</Localized></th></tr></thead><tbody><Localized>{site.lines.map(line => <tr key={line.id}><td><b><Localized>{line.name}</Localized></b><div className="muted"><Localized>{line.line_code}</Localized><Localized>{" · "}</Localized><Localized>{line.status}</Localized></div><div className="muted"><Localized>{"Line UUID: "}</Localized><Localized>{line.id}</Localized></div><Link href={`/commands?${new URLSearchParams({operation: 'deployment', line: line.id})}`}><Localized>{"Prepare expectation for this line →"}</Localized></Link></td><td><Localized>{line.deployment ? `ASR ${line.deployment.expected.version} · ${line.deployment.expected.snapshot_no}` : '—'}</Localized></td><td><Localized>{line.deployment?.actual ? `ASR ${line.deployment.actual.version} · ${line.deployment.actual.snapshot_no}` : 'Not reported'}</Localized></td><td><Localized>{line.deployment?.authorization?.authorization_no || '—'}</Localized></td><td><span className={'status ' + (line.deployment?.status === 'MATCH' ? 'pass' : 'warning')}><Localized>{line.deployment?.status || 'NOT DEPLOYED'}</Localized></span></td></tr>)}</Localized></tbody></table><Localized>{site.lines.length === 0 && <p className="muted"><Localized>{"No production lines recorded for this site."}</Localized></p>}</Localized></section>
    <section className="panel"><div className="sectiontitle"><h2><Localized>{"Production history"}</Localized></h2><Link href="/deployments"><Localized>{"Open deployments →"}</Localized></Link></div><div className="timeline"><div><b><Localized>{site.lines[0]?.deployment?.authorization?.authorization_no || 'Authorization pending'}</Localized></b><span><Localized>{"Production scope approved"}</Localized></span></div><div><b><Localized>{site.lines[0]?.deployment?.changeovers[0]?.changeover_no || 'Changeover pending'}</Localized></b><span><Localized>{"Authorized software changeover"}</Localized></span></div><div><b><Localized>{currentBatch?.batch_no || 'Batch pending'}</Localized></b><span><Localized>{currentBatch?.status || 'No active batch'}</Localized></span></div></div></section>
    <p className="datasource"><Link href="/manufacturing/sites"><Localized>{"← All manufacturing sites"}</Localized></Link></p>
  </>;
}
