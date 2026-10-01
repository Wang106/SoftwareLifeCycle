
import { Localized, LocalizedAttributes } from "../components/localized";
import Link from 'next/link';
import { apiGet } from '../lib/api';

type Summary = {
  active_changes: number; open_issues: number; high_open_issues: number; ready_releases: number;
  current_release: { id: string; version: string; status: string; snapshot_no: string | null; coverage: number | null } | null;
  recent_activity: { event_no: string; summary: string; entity_ref: string; occurred_at: string }[];
};

export default async function Page() {
  const data = await apiGet<Summary>('/api/v1/dashboard/summary');
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"SOFTWARE GOVERNANCE"}</Localized></div><h1><Localized>{"Lifecycle Dashboard"}</Localized></h1><p className="muted"><Localized>{"Trace software from requirement and verification to release, distribution and production."}</Localized></p></div><span className="badge"><Localized>{"V1 · LOCAL FIRST"}</Localized></span></div>
    <div className="cards">
      <Link className="card" href="/changes"><span className="muted"><Localized>{"Active Change Requests"}</Localized></span><div className="metric"><Localized>{data?.active_changes ?? '—'}</Localized></div><small><Localized>{"Excludes closed and released requests"}</Localized></small></Link>
      <Link className="card" href="/issues"><span className="muted"><Localized>{"Open Issues"}</Localized></span><div className="metric"><Localized>{data?.open_issues ?? '—'}</Localized></div><small><Localized>{data ? `${data.high_open_issues} high severity` : 'Connect API for live status'}</Localized></small></Link>
      <Link className="card" href="/releases/application"><span className="muted"><Localized>{"Ready for Release"}</Localized></span><div className="metric"><Localized>{data?.ready_releases ?? '—'}</Localized></div><small><Localized>{"Application releases marked READY"}</Localized></small></Link>
      <Link className="card" href="/testing/dvp"><span className="muted"><Localized>{"Verification Progress"}</Localized></span><div className="metric"><Localized>{data?.current_release?.coverage != null ? `${data.current_release.coverage}%` : '—'}</Localized></div><small><Localized>{data?.current_release ? `${data.current_release.version} · ${data.current_release.snapshot_no || 'No snapshot'}` : 'No current application release'}</Localized></small></Link>
    </div>
    <div className="grid2"><section className="panel"><h2><Localized>{"Current release"}</Localized></h2><Localized>{data?.current_release ? <><p><b><Localized>{"ASR "}</Localized><Localized>{data.current_release.version}</Localized></b><Localized>{" · "}</Localized><Localized>{data.current_release.status}</Localized></p><p className="muted"><Localized>{data.current_release.snapshot_no || 'No snapshot'}</Localized><Localized>{" · "}</Localized><Localized>{data.current_release.coverage != null ? `${data.current_release.coverage}% current snapshot execution coverage` : 'No snapshot coverage'}</Localized></p><Link href={`/releases/application/${data.current_release.id}`}><Localized>{"View release →"}</Localized></Link></> : <p className="muted"><Localized>{"No release data available."}</Localized></p>}</Localized></section>
      <section className="panel"><h2><Localized>{"Recent activity"}</Localized></h2><Localized>{data?.recent_activity.length ? <div className="searchresults"><Localized>{data.recent_activity.map(event => <Link href={`/activity/${encodeURIComponent(event.event_no)}`} key={event.event_no}><b><Localized>{event.summary}</Localized></b><span><Localized>{event.event_no}</Localized><Localized>{" · "}</Localized><Localized>{event.entity_ref}</Localized></span></Link>)}</Localized></div> : <p className="muted"><Localized>{"No activity records available."}</Localized></p>}</Localized></section></div>
    <Localized>{!data && <p className="datasource"><Localized>{"Live dashboard unavailable · configure API_BASE_URL to connect FastAPI."}</Localized></p>}</Localized>
  </>;
}
