
import { Localized, LocalizedAttributes } from "../../../../components/localized";
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
  if (!value) return <span className="muted"><Localized>{"File absent"}</Localized></span>;
  return <><div><Localized>{value.artifact_type}</Localized><Localized>{" · version "}</Localized><Localized>{value.component_version || '—'}</Localized></div>
    <code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 300}}>{value.sha256}</code>
    <div><Localized>{value.classification}</Localized><Localized>{" · "}</Localized><Localized>{value.distribution_level}</Localized></div><div><Localized>{"AI: "}</Localized><Localized>{value.ai_access_policy}</Localized></div>
    <Localized>{value.policy_rules.length ? value.policy_rules.map((rule, i) => <div key={i}><Localized>{rule.recipient_type}</Localized> <Localized>{rule.recipient_code || ''}</Localized><Localized>{" · "}</Localized><Localized>{rule.purpose}</Localized><Localized>{" · "}</Localized><Localized>{rule.decision}</Localized></div>) : <div className="muted"><Localized>{"No frozen recipient rule"}</Localized></div>}</Localized>
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
  if (!source) return <section className="panel"><h1><Localized>{"Source snapshot unavailable"}</Localized></h1><Link href="/search"><Localized>{"Search snapshots →"}</Localized></Link></section>;
  if (query.to !== undefined && (typeof query.to !== 'string' || !query.to.trim() || query.to.length > 80)) {
    return <section className="panel"><h1><Localized>{"Invalid target snapshot"}</Localized></h1><Link href={`${sourcePath}/compare`}><Localized>{"Choose a snapshot →"}</Localized></Link></section>;
  }
  const historyPath = source.release ? `/releases/${encodeURIComponent(source.release.id)}/snapshots` : null;
  const history = source.release ? await apiGet<History>(`/api/v1/releases/${encodeURIComponent(source.release.id)}/snapshots?limit=100`) : null;
  const targetNo = typeof query.to === 'string' ? query.to : history?.items.find(row => row.is_current_snapshot)?.snapshot_no || snapshotNo;
  const result = await apiGet<Comparison>(`/api/v1/snapshots/${encodeURIComponent(snapshotNo)}/compare/${encodeURIComponent(targetNo)}`);
  const showAll = query.show === 'all';
  const files = result?.files.filter(row => showAll || row.change_type !== 'unchanged') || [];
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"FROZEN SNAPSHOT COMPARISON"}</Localized></div><h1><Localized>{snapshotNo}</Localized><Localized>{" → "}</Localized><Localized>{targetNo}</Localized></h1><p className="muted"><Localized>{"Source to target · same release only"}</Localized></p></div></div>
    <section className="panel"><form method="get">
      <label><Localized>{"Target snapshot "}</Localized><input name="to" list="snapshot-options" defaultValue={targetNo} maxLength={80} required /></label>
      <datalist id="snapshot-options"><Localized>{history?.items.map(row => <option key={row.snapshot_no} value={row.snapshot_no}><Localized>{row.is_current_snapshot ? 'CURRENT' : 'HISTORICAL'}</Localized></option>)}</Localized></datalist>
      <label><Localized>{" Files "}</Localized><select name="show" defaultValue={showAll ? 'all' : 'changes'}><option value="changes"><Localized>{"Changed files only"}</Localized></option><option value="all"><Localized>{"All files"}</Localized></option></select></label> <button type="submit"><Localized>{"Compare"}</Localized></button>
    </form><p className="muted"><Localized>{"Files match by component code and filename. Renames appear as removal and addition. Comparison uses frozen hashes and policies; it does not inspect file bytes or establish approval."}</Localized></p>
      <Localized>{history && history.total > history.items.length && <p className="muted"><Localized>{"Suggestions show the latest 100 snapshots. Enter any older snapshot number from the history list."}</Localized></p>}</Localized>
      <Localized>{!history && <p className="muted"><Localized>{"Snapshot suggestions unavailable. Enter an exact snapshot number."}</Localized></p>}</Localized>
      <Localized>{historyPath && <Link href={historyPath}><Localized>{"View release snapshot history →"}</Localized></Link>}</Localized>
    </section>
    <Localized>{result ? <>
      <div className="cards"><Localized>{Object.entries(result.summary).map(([kind, count]) => <div className="card" key={kind}><span className="muted"><Localized>{kind.toUpperCase()}</Localized></span><div className="metric"><Localized>{count}</Localized></div></div>)}</Localized></div>
      <section className="panel"><h2><Localized>{"Frozen identities"}</Localized></h2><p><Localized>{"Content hashes "}</Localized><Localized>{result.content_hash_matches ? 'match' : 'differ'}</Localized><Localized>{". File fields and policies below are compared independently."}</Localized></p>
        <div className="grid2"><Localized>{[result.source, result.target].map((snapshot, i) => <div key={i}><Link href={`/snapshots/${encodeURIComponent(snapshot.snapshot_no)}`}><Localized>{i === 0 ? 'Source' : 'Target'}</Localized><Localized>{": "}</Localized><Localized>{snapshot.snapshot_no}</Localized></Link><p><Localized>{snapshot.status}</Localized><Localized>{" · "}</Localized><Localized>{snapshot.created_at.slice(0, 16).replace('T', ' ')}</Localized><Localized>{" UTC"}</Localized></p><code style={{overflowWrap: 'anywhere'}}>{snapshot.content_hash}</code></div>)}</Localized></div>
        <Localized>{result.metadata_changes.map(row => <p key={row.field}><Localized>{"Frozen "}</Localized><Localized>{row.field}</Localized><Localized>{": "}</Localized><Localized>{row.before || '—'}</Localized><Localized>{" → "}</Localized><Localized>{row.after || '—'}</Localized></p>)}</Localized>
      </section>
      <section className="panel tablewrap"><h2><Localized>{showAll ? 'All frozen files' : 'Changed frozen files'}</Localized><Localized>{" · "}</Localized><Localized>{files.length}</Localized></h2><table><thead><tr><th><Localized>{"File / change"}</Localized></th><th><Localized>{"Source"}</Localized></th><th><Localized>{"Target"}</Localized></th></tr></thead><tbody>
        <Localized>{files.map(row => <tr key={JSON.stringify([row.component_code, row.filename])}><td><b><Localized>{row.filename}</Localized></b><div><Localized>{row.component_code}</Localized><Localized>{" · "}</Localized><Localized>{row.change_type.toUpperCase()}</Localized></div><div className="muted"><Localized>{row.changed_fields.join(', ')}</Localized></div></td><td><FrozenValues value={row.before} /></td><td><FrozenValues value={row.after} /></td></tr>)}</Localized>
      </tbody></table><Localized>{files.length === 0 && <p className="muted"><Localized>{"No "}</Localized><Localized>{showAll ? 'files' : 'file differences'}</Localized><Localized>{" recorded for this comparison."}</Localized></p>}</Localized></section>
    </> : <section className="panel"><h2><Localized>{"Comparison unavailable"}</Localized></h2><p className="muted"><Localized>{"A snapshot may be missing, belong to another release, contain duplicate file identities, or the API may be unavailable. No substitute comparison is shown."}</Localized></p></section>}</Localized>
    <p><Link href={sourcePath}><Localized>{"← Source snapshot"}</Localized></Link></p>
  </>;
}
