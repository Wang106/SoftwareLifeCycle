import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
type Search = Record<string, string | string[] | undefined>;
type Kind = 'criteria' | 'points' | 'issues';
type Page = { item_id: string; kind: Kind; total: number; limit: number; offset: number; next_offset: number | null; items: { id: string; number: string; text: string }[] };
export async function DvpRelations({ item, search }: { item: { id: string; relation_counts: Record<Kind, number> }; search: Search }) {
  const kinds: Kind[] = ['criteria', 'points', 'issues'];
  const labels = { criteria: 'Acceptance criteria', points: 'Change points', issues: 'Issues' };
  const raw = (key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
  const responses = await Promise.all(kinds.map(kind => {
    const query = new URLSearchParams({ dvp_item_id: item.id });
    if (search.relation_limit !== undefined) query.set('limit', raw('relation_limit'));
    if (search[`${kind}_offset`] !== undefined) query.set('offset', raw(`${kind}_offset`));
    return apiGet<Page>(`/api/v1/testing/dvp/id/${encodeURIComponent(item.id)}/relations/${kind}?${query}`);
  }));
  const href = (kind: Kind, offset: number) => {
    const q = new URLSearchParams({ relation_item_id: item.id });
    for (const key of ['relation_limit', 'criteria_offset', 'points_offset', 'issues_offset', 'release_id', 'snapshot_no', 'result', 'before_number']) if (search[key] !== undefined) q.set(key, raw(key));
    q.set(`${kind}_offset`, String(offset));
    return `/testing/dvp/${encodeURIComponent(item.id)}?${q}`;
  };
  return <Localized><>{kinds.map((kind, index) => {
    const response = responses[index];
    const expectedLimit = search.relation_limit === undefined ? 50 : Number(raw('relation_limit'));
    const expectedOffset = search[`${kind}_offset`] === undefined ? 0 : Number(raw(`${kind}_offset`));
    const page = response?.item_id === item.id && response.kind === kind && response.limit === expectedLimit && response.offset === expectedOffset ? response : null;
    return <section className="panel" key={kind}>
      <h3><Localized>{labels[kind]}</Localized> ({item.relation_counts[kind]})</h3>
      {page ? <><p className="muted"><Localized>{"Full linked total"}</Localized>: {page.total}</p>
        <ul>{page.items.map(row => <li key={row.id}>{kind === 'issues' ? <Link href={`/issues/${encodeURIComponent(row.number)}`}>{row.number}</Link> : row.number}: <Localized>{row.text}</Localized></li>)}</ul>
        {page.items.length === 0 && <p className="muted"><Localized>{"No linked records on this page."}</Localized></p>}
        <p><Link href={href(kind, 0)}><Localized>{"First page"}</Localized></Link>{page.next_offset !== null && <> · <Link href={href(kind, page.next_offset)}><Localized>{"Next page →"}</Localized></Link></>}</p>
      </> : <p className="muted"><Localized>{"Linked records unavailable. Check pagination or API availability."}</Localized></p>}
    </section>;
  })}</></Localized>;
}
