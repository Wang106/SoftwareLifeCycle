
import { Localized, LocalizedAttributes } from "../../../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type History = {
  release: { id: string; type: string; version: string };
  total: number; next_before_number: number | null;
  items: { id: string; snapshot_no: string; snapshot_number: number; status: string;
    created_at: string; content_hash: string; is_current_snapshot: boolean }[];
};

export default async function Page({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ before?: string | string[] }>;
}) {
  const { id } = await params;
  const { before } = await searchParams;
  const historyPath = `/releases/${encodeURIComponent(id)}/snapshots`;
  if (before !== undefined && (typeof before !== 'string' || !/^\d+$/.test(before)
    || !Number.isSafeInteger(Number(before)) || Number(before) < 1)) {
    return <section className="panel"><h1><Localized>{"Invalid history cursor"}</Localized></h1><Link href={historyPath}><Localized>{"View newest snapshots →"}</Localized></Link></section>;
  }
  const history = await apiGet<History>(`/api/v1/releases/${encodeURIComponent(id)}/snapshots?limit=20${before ? `&before_number=${encodeURIComponent(before)}` : ''}`);
  if (!history) return <section className="panel"><h1><Localized>{"Snapshot history unavailable"}</Localized></h1><p className="muted"><Localized>{"The release was not found or the API could not be reached."}</Localized></p><Link href="/search"><Localized>{"Search releases →"}</Localized></Link></section>;
  const releasePath = `/releases/${history.release.type === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(history.release.id)}`;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"FROZEN SNAPSHOT HISTORY"}</Localized></div><h1><Localized>{history.release.type === 'STANDARD' ? 'SSR' : 'ASR'}</Localized> <Localized>{history.release.version}</Localized></h1><p className="muted"><Localized>{history.total}</Localized><Localized>{" recorded snapshots · newest first"}</Localized></p></div></div>
    <section className="panel tablewrap"><h2><Localized>{"Freeze records"}</Localized></h2><p className="muted"><Localized>{"Each link opens that exact frozen manifest. CURRENT identifies the newest snapshot; it does not establish release approval."}</Localized></p>
      <table><thead><tr><th><Localized>{"Snapshot"}</Localized></th><th><Localized>{"Frozen at (UTC)"}</Localized></th><th><Localized>{"Status"}</Localized></th><th><Localized>{"Full content hash"}</Localized></th><th><Localized>{"Compare"}</Localized></th></tr></thead><tbody>
        <Localized>{history.items.map(row => <tr key={row.id}>
          <td><Link href={`/snapshots/${encodeURIComponent(row.snapshot_no)}`}><b><Localized>{row.snapshot_no}</Localized></b></Link><div className="muted"><Localized>{"#"}</Localized><Localized>{row.snapshot_number}</Localized><Localized>{" · "}</Localized><Localized>{row.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</Localized></div></td>
          <td><Localized>{row.created_at.slice(0, 16).replace('T', ' ')}</Localized></td><td><Localized>{row.status}</Localized></td>
          <td><code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 360}}>{row.content_hash}</code></td>
          <td><Link href={`/snapshots/${encodeURIComponent(row.snapshot_no)}/compare`}><Localized>{"Compare →"}</Localized></Link></td>
        </tr>)}</Localized>
      </tbody></table>
      <Localized>{history.items.length === 0 && <p className="muted"><Localized>{before ? 'No older snapshots recorded before this cursor.' : 'No snapshots recorded for this release.'}</Localized></p>}</Localized>
      <p><Localized>{before && <Link href={historyPath}><Localized>{"Newest snapshots →"}</Localized></Link>}</Localized><Localized>{history.next_before_number !== null && <><Localized>{" · "}</Localized><Link href={`${historyPath}?before=${history.next_before_number}`}><Localized>{"Older snapshots →"}</Localized></Link></>}</Localized></p>
    </section>
    <p><Link href={releasePath}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
