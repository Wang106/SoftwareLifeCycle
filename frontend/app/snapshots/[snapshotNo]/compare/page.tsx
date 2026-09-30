import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Identity = { snapshot_no: string; content_hash: string; created_at: string; status: string };
type Rule = { recipient_type: string; recipient_code: string | null; purpose: string; decision: string };
type Values = { artifact_type: string; component_version: string | null; sha256: string;
  classification: string; distribution_level: string; ai_access_policy: string; policy_rules: Rule[] };
type Comparison = {
  source: Identity; target: Identity; content_hash_matches: boolean;
  summary: { added: number; removed: number; modified: number; unchanged: number };
  metadata_changes: { field: string; before: string | null; after: string | null }[];
  files: { component_code: string; filename: string; change_type: string; changed_fields: string[];
    before: Values | null; after: Values | null }[];
};
type Snapshot = { snapshot_no: string; release: { id: string } | null };
type History = { total: number; items: { snapshot_no: string; is_current_snapshot: boolean }[] };

function FrozenValues({ value }: { value: Values | null }) {
  if (!value) return <span className="muted">File absent</span>;
  return <><div>{value.artifact_type} · version {value.component_version || '—'}</div>
    <code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 300}}>{value.sha256}</code>
    <div>{value.classification} · {value.distribution_level}</div><div>AI: {value.ai_access_policy}</div>
    {value.policy_rules.length ? value.policy_rules.map((rule, i) => <div key={i}>{rule.recipient_type} {rule.recipient_code || ''} · {rule.purpose} · {rule.decision}</div>) : <div className="muted">No frozen recipient rule</div>}
  </>;
}

export default async function Page({ params, searchParams }: {
  params: Promise<{ snapshotNo: string }>;
  searchParams: Promise<{ to?: string | string[]; show?: string | string[] }>;
}) {
  const { snapshotNo } = await params;
  const query = await searchParams;
  const sourcePath = `/snapshots/${encodeURIComponent(snapshotNo)}`;
  const source = await apiGet<Snapshot>(`/api/v1/snapshots/${encodeURIComponent(snapshotNo)}`);
  if (!source) return <section className="panel"><h1>Source snapshot unavailable</h1><Link href="/search">Search snapshots →</Link></section>;
  if (query.to !== undefined && (typeof query.to !== 'string' || !query.to.trim() || query.to.length > 80)) {
    return <section className="panel"><h1>Invalid target snapshot</h1><Link href={`${sourcePath}/compare`}>Choose a snapshot →</Link></section>;
  }
  const historyPath = source.release ? `/releases/${encodeURIComponent(source.release.id)}/snapshots` : null;
  const history = source.release ? await apiGet<History>(`/api/v1/releases/${encodeURIComponent(source.release.id)}/snapshots?limit=100`) : null;
  const targetNo = typeof query.to === 'string' ? query.to : history?.items.find(row => row.is_current_snapshot)?.snapshot_no || snapshotNo;
  const result = await apiGet<Comparison>(`/api/v1/snapshots/${encodeURIComponent(snapshotNo)}/compare/${encodeURIComponent(targetNo)}`);
  const showAll = query.show === 'all';
  const files = result?.files.filter(row => showAll || row.change_type !== 'unchanged') || [];
  return <>
    <div className="top"><div><div className="eyebrow">FROZEN SNAPSHOT COMPARISON</div><h1>{snapshotNo} → {targetNo}</h1><p className="muted">Source to target · same release only</p></div></div>
    <section className="panel"><form method="get">
      <label>Target snapshot <input name="to" list="snapshot-options" defaultValue={targetNo} maxLength={80} required /></label>
      <datalist id="snapshot-options">{history?.items.map(row => <option key={row.snapshot_no} value={row.snapshot_no}>{row.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</option>)}</datalist>
      <label> Files <select name="show" defaultValue={showAll ? 'all' : 'changes'}><option value="changes">Changed files only</option><option value="all">All files</option></select></label> <button type="submit">Compare</button>
    </form><p className="muted">Files match by component code and filename. Renames appear as removal and addition. Comparison uses frozen hashes and policies; it does not inspect file bytes or establish approval.</p>
      {history && history.total > history.items.length && <p className="muted">Suggestions show the latest 100 snapshots. Enter any older snapshot number from the history list.</p>}
      {!history && <p className="muted">Snapshot suggestions unavailable. Enter an exact snapshot number.</p>}
      {historyPath && <Link href={historyPath}>View release snapshot history →</Link>}
    </section>
    {result ? <>
      <div className="cards">{Object.entries(result.summary).map(([kind, count]) => <div className="card" key={kind}><span className="muted">{kind.toUpperCase()}</span><div className="metric">{count}</div></div>)}</div>
      <section className="panel"><h2>Frozen identities</h2><p>Content hashes {result.content_hash_matches ? 'match' : 'differ'}. File fields and policies below are compared independently.</p>
        <div className="grid2">{[result.source, result.target].map((snapshot, i) => <div key={i}><Link href={`/snapshots/${encodeURIComponent(snapshot.snapshot_no)}`}>{i === 0 ? 'Source' : 'Target'}: {snapshot.snapshot_no}</Link><p>{snapshot.status} · {snapshot.created_at.slice(0, 16).replace('T', ' ')} UTC</p><code style={{overflowWrap: 'anywhere'}}>{snapshot.content_hash}</code></div>)}</div>
        {result.metadata_changes.map(row => <p key={row.field}>Frozen {row.field}: {row.before || '—'} → {row.after || '—'}</p>)}
      </section>
      <section className="panel tablewrap"><h2>{showAll ? 'All frozen files' : 'Changed frozen files'} · {files.length}</h2><table><thead><tr><th>File / change</th><th>Source</th><th>Target</th></tr></thead><tbody>
        {files.map(row => <tr key={JSON.stringify([row.component_code, row.filename])}><td><b>{row.filename}</b><div>{row.component_code} · {row.change_type.toUpperCase()}</div><div className="muted">{row.changed_fields.join(', ')}</div></td><td><FrozenValues value={row.before} /></td><td><FrozenValues value={row.after} /></td></tr>)}
      </tbody></table>{files.length === 0 && <p className="muted">No {showAll ? 'files' : 'file differences'} recorded for this comparison.</p>}</section>
    </> : <section className="panel"><h2>Comparison unavailable</h2><p className="muted">A snapshot may be missing, belong to another release, contain duplicate file identities, or the API may be unavailable. No substitute comparison is shown.</p></section>}
    <p><Link href={sourcePath}>← Source snapshot</Link></p>
  </>;
}
