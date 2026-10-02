import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Search = Record<string, string | string[] | undefined>;
type Summary = { release_id: string; snapshot: { id: string; snapshot_no: string; is_current_snapshot: boolean } | null;
  artifact_count: number; latest_execution_count: number; other_snapshot_executions: number };
type Page<T> = { release_id: string; snapshot_id: string; total: number; next_offset: number | null; items: T[] };
type Artifact = { id: string; component_code: string; component_version: string | null; filename: string; artifact_type: string;
  sha256: string; classification: string; distribution_level: string; ai_access_policy: string };
type Execution = { id: string; dvp_item_id: string; item_no: string | null; title: string | null; execution_no: number;
  result: string; executed_at: string | null; item_metadata_available: boolean };

export async function AsrEvidence({ releaseId, search }: { releaseId: string; search: Search }) {
  const endpoint = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}`;
  const selection = new URLSearchParams();
  if (search.evidence_snapshot_id !== undefined) selection.set('snapshot_id', typeof search.evidence_snapshot_id === 'string' ? search.evidence_snapshot_id : 'invalid');
  const summary = await apiGet<Summary>(`${endpoint}/evidence-summary?${selection}`);
  if (!summary || summary.release_id !== releaseId) return <p className="datasource"><Localized>{"Evidence summary unavailable. Counts are unknown."}</Localized></p>;
  if (!summary.snapshot) return <section className="panel"><h2><Localized>{"Frozen evidence"}</Localized></h2><p><Localized>{"No snapshot is available for evidence."}</Localized></p></section>;
  const snapshot = summary.snapshot;
  const query = (offset: string) => {
    const q = new URLSearchParams({ snapshot_id: snapshot.id });
    for (const [ui, api] of [['evidence_limit', 'limit'], [offset, 'offset']]) {
      if (search[ui] !== undefined) q.set(api, typeof search[ui] === 'string' ? search[ui] as string : 'invalid');
    }
    return q;
  };
  const [artifactResponse, executionResponse] = await Promise.all([
    apiGet<Page<Artifact>>(`${endpoint}/evidence/artifacts?${query('artifact_offset')}`),
    apiGet<Page<Execution>>(`${endpoint}/evidence/executions?${query('execution_offset')}`),
  ]);
  const valid = <T,>(page: Page<T> | null) => page?.release_id === releaseId && page.snapshot_id === snapshot.id ? page : null;
  const artifacts = valid(artifactResponse), executions = valid(executionResponse);
  const path = `/releases/application/${encodeURIComponent(releaseId)}`;
  const pageLink = (offsetKey: string, offset: number) => {
    const q = new URLSearchParams({ evidence_snapshot_id: snapshot.id });
    for (const key of ['evidence_limit', 'artifact_offset', 'execution_offset']) if (search[key] !== undefined) q.set(key, typeof search[key] === 'string' ? search[key] as string : 'invalid');
    q.set(offsetKey, String(offset));
    return `${path}?${q}`;
  };
  const paging = (offsetKey: string, next: number | null) => <Localized><p>
    <Link href={pageLink(offsetKey, 0)}><Localized>{"First page"}</Localized></Link>
    {next !== null && <Link href={pageLink(offsetKey, next)}><Localized>{" Next page →"}</Localized></Link>}
  </p></Localized>;
  return <Localized><>
    <section className="panel"><h2><Localized>{"Evidence snapshot · "}</Localized><Localized>{snapshot.snapshot_no}</Localized></h2>
      <code>{snapshot.id}</code><p><Localized>{snapshot.is_current_snapshot ? 'Latest snapshot at summary read time.' : 'Viewing a pinned historical snapshot.'}</Localized></p>
      <p className="muted"><Localized>{"Evidence pages stay on this exact snapshot. Release overview may refer to a newer snapshot. Counts are read observations, not approval or a consistent write receipt."}</Localized></p>
      <p><Localized>{"Execution records on other snapshots: "}</Localized><Localized>{summary.other_snapshot_executions}</Localized></p>
      <Link href={path}><Localized>{"Read latest evidence →"}</Localized></Link>
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Frozen artifact manifest"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{summary.artifact_count}</Localized></p>
      {artifacts ? <><table><thead><tr>{['Component', 'Filename', 'Type', 'SHA-256', 'Classification', 'Distribution', 'AI Policy'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead>
        <tbody>{artifacts.items.map(row => <tr key={row.id}><td><Localized>{row.component_code}</Localized> <Localized>{row.component_version || '—'}</Localized></td><td><Localized>{row.filename}</Localized></td><td><Localized>{row.artifact_type}</Localized></td><td><code>{row.sha256}</code></td><td><Localized>{row.classification}</Localized></td><td><Localized>{row.distribution_level}</Localized></td><td><Localized>{row.ai_access_policy}</Localized></td></tr>)}</tbody></table>
        {artifacts.items.length === 0 && <p><Localized>{"No artifacts on this page."}</Localized></p>}{paging('artifact_offset', artifacts.next_offset)}</>
        : <p className="muted"><Localized>{"Artifact page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Latest DVP execution on selected snapshot"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{summary.latest_execution_count}</Localized></p>
      {executions ? <><table><thead><tr>{['DVP', 'Test Item', 'Execution', 'Result', 'Executed'].map(label => <th key={label}><Localized>{label}</Localized></th>)}</tr></thead>
        <tbody>{executions.items.map(row => <tr key={row.id}><td><Localized>{row.item_no || 'DVP metadata unavailable'}</Localized><div><code>{row.dvp_item_id}</code></div></td><td><Localized>{row.title || '—'}</Localized></td><td><Localized>{row.execution_no}</Localized></td><td><Localized>{row.result}</Localized></td><td><Localized>{row.executed_at?.slice(0, 16).replace('T', ' ') || '—'}</Localized></td></tr>)}</tbody></table>
        {executions.items.length === 0 && <p><Localized>{"No executions on this page."}</Localized></p>}{paging('execution_offset', executions.next_offset)}</>
        : <p className="muted"><Localized>{"Execution page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}
    </section>
  </></Localized>;
}
