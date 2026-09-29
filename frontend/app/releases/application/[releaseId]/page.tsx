import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Coverage = {
  change_points_total: number; change_points_covered: number; change_coverage: number;
  issues_total: number; issues_covered: number; issue_verification_coverage: number;
  required_dvp_total: number; current_snapshot_executed: number; dvp_execution_coverage: number;
  snapshot_match: boolean;
};
type Profile = {
  id: string; version: string; status: string; release_notes: string | null;
  software: { code: string; name: string } | null;
  customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  base_release: { version: string; status: string } | null;
  snapshot: { snapshot_no: string; status: string; content_hash: string } | null;
  coverage: Coverage | null;
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const profile = await apiGet<Profile>(`/api/v1/releases/application/id/${encodeURIComponent(releaseId)}`);
  if (!profile) return <section className="panel"><h1>Release unavailable</h1><p className="muted">The release was not found or the API could not be reached.</p><Link href="/releases/application">Back to releases →</Link></section>;
  const c = profile.coverage;
  return <>
    <div className="top"><div><div className="eyebrow">APPLICATION SOFTWARE RELEASE</div><h1>ASR {profile.version}</h1><p className="muted">{profile.customer?.name || 'No customer'} · {profile.project?.name || 'No project'} · {profile.software?.name || 'No software'}</p></div><span className={'status ' + (profile.status === 'READY' || profile.status === 'RELEASED' ? 'pass' : 'warning')}>{profile.status}</span></div>
    <div className="cards"><div className="card"><span className="muted">SNAPSHOT</span><div className="metric">{profile.snapshot?.snapshot_no || '—'}</div><small>{profile.snapshot?.status || 'No snapshot'}</small></div><div className="card"><span className="muted">CHANGE COVERAGE</span><div className="metric">{c ? `${c.change_coverage}%` : '—'}</div><small>{c ? `${c.change_points_covered} / ${c.change_points_total} change points` : 'No snapshot'}</small></div><div className="card"><span className="muted">ISSUE COVERAGE</span><div className="metric">{c ? `${c.issue_verification_coverage}%` : '—'}</div><small>{c ? `${c.issues_covered} / ${c.issues_total} issues` : 'No snapshot'}</small></div><div className="card"><span className="muted">DVP EXECUTION</span><div className="metric">{c ? `${c.dvp_execution_coverage}%` : '—'}</div><small>{c ? `${c.current_snapshot_executed} / ${c.required_dvp_total} on current snapshot` : 'No snapshot'}</small></div></div>
    <div className="grid2"><section className="panel"><h2>Release identity</h2><div className="kv"><span>Software</span><b>{profile.software ? `${profile.software.name} · ${profile.software.code}` : '—'}</b><span>Customer</span><b>{profile.customer ? <Link href={`/customers/${encodeURIComponent(profile.customer.code)}`}>{profile.customer.name}</Link> : '—'}</b><span>Project</span><b>{profile.project ? <Link href={`/projects/${profile.project.id}`}>{profile.project.name}</Link> : '—'}</b><span>Standard Base</span><b>{profile.base_release ? `SSR ${profile.base_release.version}` : '—'}</b><span>Content Hash</span><code>{profile.snapshot?.content_hash || '—'}</code></div></section><section className="panel"><h2>Verification context</h2><p className="muted">{c ? (c.snapshot_match ? 'Execution records match the latest snapshot.' : 'Some execution records are from a different snapshot.') : 'A frozen snapshot is required for verification coverage.'}</p><p>{profile.release_notes || 'No release notes recorded.'}</p>{profile.version === '2.3.4' && <Link href="/releases/demo">Open detailed demo workspace →</Link>}</section></div>
    <p className="datasource"><Link href="/releases/application">← All application releases</Link></p>
  </>;
}
