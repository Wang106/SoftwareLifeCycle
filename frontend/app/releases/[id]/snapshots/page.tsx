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
    return <section className="panel"><h1>Invalid history cursor</h1><Link href={historyPath}>View newest snapshots →</Link></section>;
  }
  const history = await apiGet<History>(`/api/v1/releases/${encodeURIComponent(id)}/snapshots?limit=20${before ? `&before_number=${encodeURIComponent(before)}` : ''}`);
  if (!history) return <section className="panel"><h1>Snapshot history unavailable</h1><p className="muted">The release was not found or the API could not be reached.</p><Link href="/search">Search releases →</Link></section>;
  const releasePath = `/releases/${history.release.type === 'STANDARD' ? 'standard' : 'application'}/${encodeURIComponent(history.release.id)}`;
  return <>
    <div className="top"><div><div className="eyebrow">FROZEN SNAPSHOT HISTORY</div><h1>{history.release.type === 'STANDARD' ? 'SSR' : 'ASR'} {history.release.version}</h1><p className="muted">{history.total} recorded snapshots · newest first</p></div></div>
    <section className="panel tablewrap"><h2>Freeze records</h2><p className="muted">Each link opens that exact frozen manifest. CURRENT identifies the newest snapshot; it does not establish release approval.</p>
      <table><thead><tr><th>Snapshot</th><th>Frozen at (UTC)</th><th>Status</th><th>Full content hash</th><th>Compare</th></tr></thead><tbody>
        {history.items.map(row => <tr key={row.id}>
          <td><Link href={`/snapshots/${encodeURIComponent(row.snapshot_no)}`}><b>{row.snapshot_no}</b></Link><div className="muted">#{row.snapshot_number} · {row.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</div></td>
          <td>{row.created_at.slice(0, 16).replace('T', ' ')}</td><td>{row.status}</td>
          <td><code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 360}}>{row.content_hash}</code></td>
          <td><Link href={`/snapshots/${encodeURIComponent(row.snapshot_no)}/compare`}>Compare →</Link></td>
        </tr>)}
      </tbody></table>
      {history.items.length === 0 && <p className="muted">{before ? 'No older snapshots recorded before this cursor.' : 'No snapshots recorded for this release.'}</p>}
      <p>{before && <Link href={historyPath}>Newest snapshots →</Link>}{history.next_before_number !== null && <> · <Link href={`${historyPath}?before=${history.next_before_number}`}>Older snapshots →</Link></>}</p>
    </section>
    <p><Link href={releasePath}>← Release profile</Link></p>
  </>;
}
