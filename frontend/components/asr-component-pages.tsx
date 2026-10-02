import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Search = Record<string, string | string[] | undefined>;
type Page<T> = { release_id: string; base_release_id: string | null; total: number; limit: number; offset: number; next_offset: number | null; items: T[] };
type Component = { id: string; code: string | null; name: string | null; version: string | null };
type Declaration = Omit<Component, 'version'> & { asr_version: string | null; declared_delta_type: string; base_component_version: string | null; base_link_status: 'VALID' | 'INVALID' | 'NOT_RECORDED' };

export async function AsrComponentPages({ releaseId, baseReleaseId, search, componentCount, unlinkedCount }: {
  releaseId: string; baseReleaseId: string | null; search: Search; componentCount: number; unlinkedCount: number;
}) {
  const endpoint = `/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/components`;
  const query = (offset: string) => {
    const q = new URLSearchParams();
    for (const [ui, api] of [['component_limit', 'limit'], [offset, 'offset']]) {
      if (search[ui] !== undefined) q.set(api, typeof search[ui] === 'string' ? search[ui] as string : 'invalid');
    }
    return q;
  };
  const [declarationResponse, unlinkedResponse] = await Promise.all([
    apiGet<Page<Declaration>>(`${endpoint}/declarations?${query('declaration_offset')}`),
    apiGet<Page<Component>>(`${endpoint}/unlinked-base?${query('unlinked_offset')}`),
  ]);
  const valid = <T,>(page: Page<T> | null) => page?.release_id === releaseId && page.base_release_id === baseReleaseId ? page : null;
  const declarations = valid(declarationResponse), unlinked = valid(unlinkedResponse);
  const pageLink = (key: string, offset: number) => {
    const q = new URLSearchParams();
    for (const name of ['component_limit', 'declaration_offset', 'unlinked_offset']) {
      if (search[name] !== undefined) q.set(name, typeof search[name] === 'string' ? search[name] as string : 'invalid');
    }
    q.set(key, String(offset));
    return `/releases/application/${encodeURIComponent(releaseId)}/components?${q}`;
  };
  const paging = (key: string, next: number | null) => <Localized><p>
    <Link href={pageLink(key, 0)}><Localized>{"First page"}</Localized></Link>
    {next !== null && <Link href={pageLink(key, next)}><Localized>{" Next page →"}</Localized></Link>}
  </p></Localized>;
  return <Localized><>
    <p className="muted"><Localized>{"Recorded declarations and baseline links are read observations, not frozen evidence or approval. Counts and pages may change between reads."}</Localized></p>
    <section className="panel tablewrap"><h2><Localized>{"ASR component declarations"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{componentCount}</Localized></p>
      <p className="muted"><Localized>{"A delta label is a recorded declaration. The SSR component version appears only when a matching base component link is stored."}</Localized></p>
      {declarations ? <><table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"ASR Version"}</Localized></th><th><Localized>{"Declared Delta"}</Localized></th><th><Localized>{"Linked SSR Version"}</Localized></th><th><Localized>{"Baseline Link"}</Localized></th></tr></thead>
        <tbody>{declarations.items.map(row => <tr key={row.id}>
          <td><b><Localized>{row.name || row.code || row.id}</Localized></b>{row.code && <div className="muted"><Localized>{row.code}</Localized></div>}</td>
          <td><Localized>{row.asr_version || '—'}</Localized></td>
          <td><span className={'status ' + (row.declared_delta_type === 'UNCHANGED' ? 'pass' : 'warning')}><Localized>{row.declared_delta_type}</Localized></span></td>
          <td><Localized>{row.base_component_version || '—'}</Localized></td>
          <td><Localized>{row.base_link_status === 'VALID' ? 'Linked to base SSR' : row.base_link_status === 'INVALID' ? 'Invalid base link' : 'Not recorded'}</Localized></td>
        </tr>)}</tbody></table>
        {declarations.items.length === 0 && <p className="muted"><Localized>{"No ASR declarations on this page."}</Localized></p>}{paging('declaration_offset', declarations.next_offset)}</>
        : <p className="muted"><Localized>{"ASR declaration page unavailable. The API is unavailable, pagination is invalid or the baseline changed."}</Localized></p>}
    </section>
    <section className="panel tablewrap"><h2><Localized>{"SSR components without an ASR link"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{unlinkedCount}</Localized></p>
      <p className="muted"><Localized>{"Their presence in the SSR does not establish whether the ASR inherits, changes or omits them."}</Localized></p>
      {unlinked ? <><table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"SSR Version"}</Localized></th></tr></thead><tbody>
        {unlinked.items.map(row => <tr key={row.id}><td><Localized>{row.name || row.code || row.id}</Localized></td><td><Localized>{row.version || '—'}</Localized></td></tr>)}
      </tbody></table>{unlinked.items.length === 0 && <p className="muted"><Localized>{"No unlinked baseline components on this page."}</Localized></p>}{paging('unlinked_offset', unlinked.next_offset)}</>
        : <p className="muted"><Localized>{"Unlinked baseline page unavailable. The API is unavailable, pagination is invalid or the baseline changed."}</Localized></p>}
    </section>
  </></Localized>;
}
