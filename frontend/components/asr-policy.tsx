import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Search = Record<string, string | string[] | undefined>;
type Summary = { release_id: string; snapshot: { id: string; snapshot_no: string; status: string; content_hash: string; is_current_snapshot: boolean } | null;
  artifact_count: number; sha_recorded_count: number; policy_recorded_count: number; rule_count: number };
type Page<T> = { release_id: string; snapshot_id: string; snapshot_artifact_id?: string | null; total: number; next_offset: number | null; items: T[] };
type Artifact = { id: string; component_code: string; component_version: string | null; filename: string; artifact_type: string; sha256: string;
  classification: string; distribution_level: string; ai_access_policy: string; rule_count: number };
type Rule = { id: string; snapshot_artifact_id: string; filename: string; component_code: string; distribution_level: string;
  recipient_type: string; purpose: string; recipient_code: string | null; decision: string };

export async function AsrPolicy({ releaseId, search }: { releaseId: string; search: Search }) {
  const endpoint = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/snapshot-policy`;
  const path = `/releases/application/${encodeURIComponent(releaseId)}/artifacts`;
  const raw = (key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
  const selection = new URLSearchParams();
  if (search.policy_snapshot_id !== undefined) selection.set('snapshot_id', raw('policy_snapshot_id'));
  const summary = await apiGet<Summary>(`${endpoint}/summary?${selection}`);
  if (!summary || summary.release_id !== releaseId || (search.policy_snapshot_id !== undefined && summary.snapshot?.id !== raw('policy_snapshot_id'))) return <section className="panel"><h1><Localized>{"Snapshot policy unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p>
    <Link href={path}><Localized>{"Read latest policy →"}</Localized></Link></section>;
  if (!summary.snapshot) return <section className="panel"><h1><Localized>{"No snapshot"}</Localized></h1>
    <p className="muted"><Localized>{"No snapshot has been recorded for this application release."}</Localized></p>
    <Link href={`/releases/application/${encodeURIComponent(releaseId)}`}><Localized>{"← Release profile"}</Localized></Link></section>;
  const snapshot = summary.snapshot;
  const query = (offset: string) => {
    const q = new URLSearchParams({ snapshot_id: snapshot.id });
    for (const [ui, api] of [['policy_limit', 'limit'], [offset, 'offset']]) if (search[ui] !== undefined) q.set(api, raw(ui));
    return q;
  };
  const ruleQuery = query('policy_rule_offset');
  if (search.policy_artifact_id !== undefined) ruleQuery.set('snapshot_artifact_id', raw('policy_artifact_id'));
  const [artifactResponse, ruleResponse] = await Promise.all([
    apiGet<Page<Artifact>>(`${endpoint}/artifacts?${query('policy_artifact_offset')}`),
    apiGet<Page<Rule>>(`${endpoint}/rules?${ruleQuery}`),
  ]);
  const valid = <T,>(page: Page<T> | null) => page?.release_id === releaseId && page.snapshot_id === snapshot.id ? page : null;
  const artifacts = valid(artifactResponse), rulePage = valid(ruleResponse);
  const rules = rulePage && rulePage.snapshot_artifact_id === (search.policy_artifact_id !== undefined ? raw('policy_artifact_id') : null) ? rulePage : null;
  const pageLink = (key: string, value: string | number | null) => {
    const q = new URLSearchParams({ policy_snapshot_id: snapshot.id });
    for (const name of ['policy_limit', 'policy_artifact_offset', 'policy_rule_offset', 'policy_artifact_id']) if (search[name] !== undefined) q.set(name, raw(name));
    if (value === null) q.delete(key); else q.set(key, String(value));
    if (key === 'policy_artifact_id') q.set('policy_rule_offset', '0');
    return `${path}?${q}`;
  };
  const paging = (key: string, next: number | null) => <Localized><p>
    <Link href={pageLink(key, 0)}><Localized>{"First page"}</Localized></Link>
    {next !== null && <Link href={pageLink(key, next)}><Localized>{" Next page →"}</Localized></Link>}
  </p></Localized>;
  return <Localized><>
    <div className="top"><div><div className="eyebrow"><Localized>{"FROZEN ARTIFACT POLICY"}</Localized></div><h1><Localized>{snapshot.snapshot_no}</Localized></h1>
      <p className="muted"><Localized>{"Files and recipient rules captured with this application release snapshot."}</Localized></p></div><span className="status"><Localized>{snapshot.status}</Localized></span></div>
    <section className="panel"><code>{snapshot.id}</code><p><Localized>{snapshot.is_current_snapshot ? 'Latest snapshot at summary read time.' : 'Viewing a pinned historical snapshot.'}</Localized></p>
      <p className="muted"><Localized>{"Policy pages stay on this exact snapshot. Recorded counts do not verify file hashes, grant distribution permission or prove approval."}</Localized></p>
      <Link href={path}><Localized>{"Read latest policy →"}</Localized></Link></section>
    <div className="cards">
      <div className="card"><span className="muted"><Localized>{"FROZEN FILES"}</Localized></span><div className="metric"><Localized>{summary.artifact_count}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"SHA RECORDED"}</Localized></span><div className="metric"><Localized>{summary.sha_recorded_count}</Localized><Localized>{" / "}</Localized><Localized>{summary.artifact_count}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"POLICY RECORDED"}</Localized></span><div className="metric"><Localized>{summary.policy_recorded_count}</Localized><Localized>{" / "}</Localized><Localized>{summary.artifact_count}</Localized></div></div>
      <div className="card"><span className="muted"><Localized>{"RECIPIENT RULES"}</Localized></span><div className="metric"><Localized>{summary.rule_count}</Localized></div></div>
    </div>
    <section className="panel"><h2><Localized>{"Snapshot content hash"}</Localized></h2><code className="hash">{snapshot.content_hash}</code></section>
    <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest"}</Localized></h2>
      <p className="muted"><Localized>{"An internal-only file cannot be distributed externally. A recorded ALLOW or APPROVAL_REQUIRED rule applies only to its named recipient and purpose; it is not a general permission."}</Localized></p>
      {artifacts ? <><table><thead><tr>{['File', 'Component', 'SHA-256', 'Classification', 'Distribution', 'AI Policy', 'Recipient Rules'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead><tbody>
        {artifacts.items.map(row => <tr key={row.id}><td><b><Localized>{row.filename}</Localized></b><br /><Localized>{row.artifact_type}</Localized></td>
          <td><Localized>{row.component_code}</Localized> <Localized>{row.component_version || '—'}</Localized></td><td><code><Localized>{row.sha256 ? `${row.sha256.slice(0, 12)}…` : 'Missing'}</Localized></code></td>
          <td><Localized>{row.classification}</Localized></td><td><Localized>{row.distribution_level}</Localized></td><td><Localized>{row.ai_access_policy}</Localized></td>
          <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.rule_count === 0 ? 'No rule recorded' : 'Recorded rules'}</Localized><br />
            <Link href={pageLink('policy_artifact_id', row.id)}><Localized>{"View recorded rules →"}</Localized></Link><Localized>{": "}</Localized><Localized>{row.rule_count}</Localized></td></tr>)}
      </tbody></table>{artifacts.items.length === 0 && <p className="muted"><Localized>{"No frozen artifacts on this page."}</Localized></p>}{paging('policy_artifact_offset', artifacts.next_offset)}</>
        : <p className="muted"><Localized>{"Policy artifact page unavailable. Check pagination and snapshot selection."}</Localized></p>}
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Recorded recipient rules"}</Localized></h2>
      <p className="muted"><Localized>{"Rules are stored declarations. Internal-only files remain denied for external distribution regardless of a recorded rule."}</Localized></p>
      {search.policy_artifact_id !== undefined && <p><Localized>{"Selected artifact: "}</Localized><code>{raw('policy_artifact_id')}</code></p>}
      <Link href={pageLink('policy_artifact_id', null)}><Localized>{"All snapshot rules →"}</Localized></Link>
      {rules ? <><p><Localized>{"Matching rule count"}</Localized><Localized>{": "}</Localized><Localized>{rules.total}</Localized></p>
        <table><thead><tr>{['File', 'Component', 'Recipient', 'Purpose', 'Decision', 'Distribution'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead><tbody>
          {rules.items.map(row => <tr key={row.id}><td><Localized>{row.filename}</Localized><br /><code>{row.snapshot_artifact_id}</code></td><td><Localized>{row.component_code}</Localized></td>
            <td><Localized>{row.recipient_type}</Localized> <Localized>{row.recipient_code || '—'}</Localized></td><td><Localized>{row.purpose}</Localized></td><td><Localized>{row.decision}</Localized></td>
            <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.distribution_level}</Localized></td></tr>)}
        </tbody></table>{rules.items.length === 0 && <p className="muted"><Localized>{"No recipient rules on this page."}</Localized></p>}{paging('policy_rule_offset', rules.next_offset)}</>
        : <p className="muted"><Localized>{"Policy rule page unavailable. Check pagination, snapshot and artifact selection."}</Localized></p>}
    </section>
    <p className="datasource"><Link href={`/releases/application/${encodeURIComponent(releaseId)}`}><Localized>{"← Release profile"}</Localized></Link></p>
  </></Localized>;
}
