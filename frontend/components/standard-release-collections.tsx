import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';

type Search = Record<string, string | string[] | undefined>;
type Page<T> = { release_id: string; total: number; limit: number; offset: number; next_offset: number | null; items: T[] };
type Component = { id: string; code: string | null; name: string | null; version: string | null };
type Application = { id: string; version: string; status: string };

export async function StandardReleaseCollections({ releaseId, search, componentCount, applicationCount }: {
  releaseId: string; search: Search; componentCount: number; applicationCount: number;
}) {
  const endpoint = `/api/v1/releases/standard/id/${encodeURIComponent(releaseId)}`;
  const query = (offset: string) => {
    const q = new URLSearchParams();
    for (const [ui, api] of [['release_limit', 'limit'], [offset, 'offset']]) {
      if (search[ui] !== undefined) q.set(api, typeof search[ui] === 'string' ? search[ui] as string : 'invalid');
    }
    return q;
  };
  const [componentResponse, applicationResponse] = await Promise.all([
    apiGet<Page<Component>>(`${endpoint}/components?${query('component_offset')}`),
    apiGet<Page<Application>>(`${endpoint}/applications?${query('application_offset')}`),
  ]);
  const valid = <T,>(page: Page<T> | null) => page?.release_id === releaseId ? page : null;
  const components = valid(componentResponse), applications = valid(applicationResponse);
  const pageLink = (offsetKey: string, offset: number) => {
    const q = new URLSearchParams();
    for (const key of ['release_limit', 'component_offset', 'application_offset']) {
      if (search[key] !== undefined) q.set(key, typeof search[key] === 'string' ? search[key] as string : 'invalid');
    }
    q.set(offsetKey, String(offset));
    return `/releases/standard/${encodeURIComponent(releaseId)}?${q}`;
  };
  const paging = (offsetKey: string, next: number | null) => <Localized><p>
    <Link href={pageLink(offsetKey, 0)}><Localized>{"First page"}</Localized></Link>
    {next !== null && <Link href={pageLink(offsetKey, next)}><Localized>{" Next page →"}</Localized></Link>}
  </p></Localized>;
  return <Localized><>
    <p className="muted"><Localized>{"Recorded declarations and baseline links are read observations, not frozen evidence or approval. Counts and pages may change between reads."}</Localized></p>
    <section className="panel tablewrap"><h2><Localized>{"Recorded components"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{componentCount}</Localized></p>
      {components ? <><table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"Version"}</Localized></th></tr></thead>
        <tbody>{components.items.map(row => <tr key={row.id}><td><b><Localized>{row.name || row.code || 'Unknown component'}</Localized></b><div className="muted"><Localized>{row.code || 'No code'}</Localized></div></td><td><Localized>{row.version || '—'}</Localized></td></tr>)}</tbody></table>
        {components.items.length === 0 && <p className="muted"><Localized>{"No components on this page."}</Localized></p>}{paging('component_offset', components.next_offset)}</>
        : <p className="muted"><Localized>{"Component page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}
    </section>
    <section className="panel tablewrap"><h2><Localized>{"Application releases using this baseline"}</Localized></h2>
      <p><Localized>{"Recorded count"}</Localized><Localized>{": "}</Localized><Localized>{applicationCount}</Localized></p>
      {applications ? <><table><thead><tr><th><Localized>{"Release"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead>
        <tbody>{applications.items.map(row => <tr key={row.id}><td><Link href={`/releases/application/${encodeURIComponent(row.id)}`}><Localized>{"ASR "}</Localized><Localized>{row.version}</Localized></Link></td><td><Localized>{row.status}</Localized></td></tr>)}</tbody></table>
        {applications.items.length === 0 && <p className="muted"><Localized>{"No application releases on this page."}</Localized></p>}{paging('application_offset', applications.next_offset)}</>
        : <p className="muted"><Localized>{"Application release page unavailable. The API is unavailable or pagination is invalid."}</Localized></p>}
    </section>
  </></Localized>;
}
