import Link from 'next/link';
import { apiGet } from '../lib/api';

type Summary = {
  active_changes: number; open_issues: number; high_open_issues: number; ready_releases: number;
  current_release: { version: string; status: string; snapshot_no: string | null; coverage: number } | null;
  recent_activity: { event_no: string; summary: string; entity_ref: string; occurred_at: string }[];
};

export default async function Page() {
  const data = await apiGet<Summary>('/api/v1/dashboard/summary');
  return <>
    <div className="top"><div><div className="eyebrow">SOFTWARE GOVERNANCE</div><h1>Lifecycle Dashboard</h1><p className="muted">Trace software from requirement and verification to release, distribution and production.</p></div><span className="badge">V1 · LOCAL FIRST</span></div>
    <div className="cards">
      <Link className="card" href="/changes"><span className="muted">Active Change Requests</span><div className="metric">{data?.active_changes ?? '—'}</div><small>Excludes closed and released requests</small></Link>
      <Link className="card" href="/issues"><span className="muted">Open Issues</span><div className="metric">{data?.open_issues ?? '—'}</div><small>{data ? `${data.high_open_issues} high severity` : 'Connect API for live status'}</small></Link>
      <Link className="card" href="/releases/application"><span className="muted">Ready for Release</span><div className="metric">{data?.ready_releases ?? '—'}</div><small>Application releases marked READY</small></Link>
      <Link className="card" href="/testing/dvp"><span className="muted">Verification Progress</span><div className="metric">{data?.current_release ? `${data.current_release.coverage}%` : '—'}</div><small>{data?.current_release ? `${data.current_release.version} · ${data.current_release.snapshot_no || 'No snapshot'}` : 'No current application release'}</small></Link>
    </div>
    <div className="grid2"><section className="panel"><h2>Current release</h2>{data?.current_release ? <><p><b>ASR {data.current_release.version}</b> · {data.current_release.status}</p><p className="muted">{data.current_release.snapshot_no || 'No snapshot'} · {data.current_release.coverage}% current snapshot execution coverage</p><Link href="/releases/application">View releases →</Link></> : <p className="muted">No release data available.</p>}</section>
      <section className="panel"><h2>Recent activity</h2>{data?.recent_activity.length ? <div className="searchresults">{data.recent_activity.map(event => <Link href="/activity" key={event.event_no}><b>{event.summary}</b><span>{event.event_no} · {event.entity_ref}</span></Link>)}</div> : <p className="muted">No activity records available.</p>}</section></div>
    {!data && <p className="datasource">Live dashboard unavailable · configure API_BASE_URL to connect FastAPI.</p>}
  </>;
}
