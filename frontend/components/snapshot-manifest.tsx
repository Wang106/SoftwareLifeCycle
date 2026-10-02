import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
type Search = Record<string, string | string[] | undefined>;
type Page<T> = { snapshot_no: string; release_id: string; snapshot_id: string; snapshot_artifact_id?: string | null; total: number; next_offset: number | null; items: T[] };
type Artifact = { id: string; component_code: string; component_version: string | null; filename: string; artifact_type: string; sha256: string;
  classification: string; distribution_level: string; ai_access_policy: string; rule_count: number };
type Rule = { id: string; snapshot_artifact_id: string; filename: string; component_code: string; distribution_level: string;
  recipient_type: string; purpose: string; recipient_code: string | null; decision: string };

type Summary = { id: string; release_id: string; snapshot_no: string; artifact_count: number; rule_count: number };
export async function SnapshotManifest({ snapshot, search }: { snapshot: Summary; search: Search }) {
  const endpoint = `/api/v1/snapshots/${encodeURIComponent(snapshot.snapshot_no)}`;
  const path = `/snapshots/${encodeURIComponent(snapshot.snapshot_no)}`;
  const releaseId = snapshot.release_id;
  const raw = (key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
  const query = (offset: string) => {
    const q = new URLSearchParams({ snapshot_id: snapshot.id });
    for (const [ui, api] of [['manifest_limit', 'limit'], [offset, 'offset']]) if (search[ui] !== undefined) q.set(api, raw(ui));
    if (search.manifest_artifact_id !== undefined) q.set('snapshot_artifact_id', raw('manifest_artifact_id'));
    return q;
  };
  const ruleQuery = query('manifest_rule_offset');
  const [artifactResponse, ruleResponse] = await Promise.all([
    apiGet<Page<Artifact>>(`${endpoint}/artifacts?${query('manifest_artifact_offset')}`),
    apiGet<Page<Rule>>(`${endpoint}/rules?${ruleQuery}`),
  ]);
  const valid = <T,>(page: Page<T> | null) => page?.release_id === releaseId && page.snapshot_id === snapshot.id && page.snapshot_no === snapshot.snapshot_no && page.snapshot_artifact_id === (search.manifest_artifact_id !== undefined ? raw('manifest_artifact_id') : null) ? page : null;
  const artifacts = valid(artifactResponse), rules = valid(ruleResponse);
  const pageLink = (key: string, value: string | number | null) => {
    const q = new URLSearchParams({ manifest_snapshot_id: snapshot.id });
    for (const name of ['manifest_limit', 'manifest_artifact_offset', 'manifest_rule_offset', 'manifest_artifact_id']) if (search[name] !== undefined) q.set(name, raw(name));
    if (value === null) q.delete(key); else q.set(key, String(value));
    if (key === 'manifest_artifact_id') { q.set('manifest_rule_offset', '0'); q.set('manifest_artifact_offset', '0'); }
    return `${path}?${q}`;
  };
  const paging = (key: string, next: number | null) => <Localized><p>
    <Link href={pageLink(key, 0)}><Localized>{"First page"}</Localized></Link>
    {next !== null && <Link href={pageLink(key, next)}><Localized>{" Next page →"}</Localized></Link>}
  </p></Localized>;
  return <Localized><>
    <p className="muted"><Localized>{"Frozen totals"}</Localized><Localized>{": "}</Localized><Localized>{snapshot.artifact_count}</Localized><Localized>{" files · "}</Localized><Localized>{snapshot.rule_count}</Localized><Localized>{" rules"}</Localized></p>
    <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest"}</Localized></h2>
      <p className="muted"><Localized>{"An internal-only file cannot be distributed externally. A recorded ALLOW or APPROVAL_REQUIRED rule applies only to its named recipient and purpose; it is not a general permission."}</Localized></p>
      {artifacts ? <><table><thead><tr>{['File', 'Component', 'Full SHA-256', 'Classification', 'Distribution', 'AI Policy', 'Recipient Rules'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead><tbody>
        {artifacts.items.map(row => <tr key={row.id} id={`artifact-${row.id}`}><td><b><Localized>{row.filename}</Localized></b><br /><code>{row.id}</code><br /><Localized>{row.artifact_type}</Localized></td>
          <td><Localized>{row.component_code}</Localized> <Localized>{row.component_version || '—'}</Localized></td><td><code style={{overflowWrap: 'anywhere', display: 'block', maxWidth: 240}}>{row.sha256}</code></td>
          <td><Localized>{row.classification}</Localized></td><td><Localized>{row.distribution_level}</Localized></td><td><Localized>{row.ai_access_policy}</Localized></td>
          <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.rule_count === 0 ? 'No rule recorded' : 'Recorded rules'}</Localized><br />
            <Link href={pageLink('manifest_artifact_id', row.id)}><Localized>{"View recorded rules →"}</Localized></Link><Localized>{": "}</Localized><Localized>{row.rule_count}</Localized></td></tr>)}
      </tbody></table>{artifacts.items.length === 0 && <p className="muted"><Localized>{"No frozen artifacts on this page."}</Localized></p>}{paging('manifest_artifact_offset', artifacts.next_offset)}</>
        : <p className="muted"><Localized>{"Manifest artifact page unavailable. Check pagination and exact selection."}</Localized></p>}
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Recorded recipient rules"}</Localized></h2>
      <p className="muted"><Localized>{"Rules are stored declarations. Internal-only files remain denied for external distribution regardless of a recorded rule."}</Localized></p>
      {search.manifest_artifact_id !== undefined && <p><Localized>{"Selected artifact: "}</Localized><code>{raw('manifest_artifact_id')}</code></p>}
      <Link href={pageLink('manifest_artifact_id', null)}><Localized>{"All snapshot files and rules →"}</Localized></Link>
      {rules ? <><p><Localized>{"Matching rule count"}</Localized><Localized>{": "}</Localized><Localized>{rules.total}</Localized></p>
        <table><thead><tr>{['File', 'Component', 'Recipient', 'Purpose', 'Decision', 'Distribution'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead><tbody>
          {rules.items.map(row => <tr key={row.id}><td><Localized>{row.filename}</Localized><br /><code>{row.snapshot_artifact_id}</code></td><td><Localized>{row.component_code}</Localized></td>
            <td><Localized>{row.recipient_type}</Localized> <Localized>{row.recipient_code || '—'}</Localized></td><td><Localized>{row.purpose}</Localized></td><td><Localized>{row.decision}</Localized></td>
            <td><Localized>{row.distribution_level === 'INTERNAL_ONLY' ? 'External distribution denied' : row.distribution_level}</Localized></td></tr>)}
        </tbody></table>{rules.items.length === 0 && <p className="muted"><Localized>{"No recipient rules on this page."}</Localized></p>}{paging('manifest_rule_offset', rules.next_offset)}</>
        : <p className="muted"><Localized>{"Manifest rule page unavailable. Check pagination and exact selection."}</Localized></p>}
    </section>
  </></Localized>;
}
