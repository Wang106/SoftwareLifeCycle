import Link from 'next/link';
import { Localized } from './localized';
import { apiGet } from '../lib/api';
import type { ChangeSummary, ChangeSearch } from '../lib/change-views';

type Kind = 'criteria' | 'issues' | 'points' | 'plans' | 'point_items' | 'plan_items';
type Row = { id: string; criterion_no?: string; description?: string | null; relation_id?: string;
  issue_no?: string; relation_type?: string; change_no?: string; plan_no?: string;
  title?: string; status?: string; item_count?: number; item_no?: string; plan_id?: string };
type Page = { change_id: string; request_no: string; total: number; next_offset: number | null;
  point_id?: string; plan_id?: string; items: Row[] };
const titles: Record<Kind, string> = {criteria:'Acceptance criteria',issues:'Linked issues',points:'Change points & linked DVP items',plans:'DVP plans',point_items:'Selected point DVP items',plan_items:'Selected plan DVP items'};
const offsets: Record<Kind, string> = {criteria:'criteria_offset',issues:'issues_offset',points:'points_offset',plans:'plans_offset',point_items:'point_items_offset',plan_items:'plan_items_offset'};

export default async function ChangeCollections({change, search}: {change: ChangeSummary; search: ChangeSearch}) {
  const raw = (key: string) => search[key] === undefined ? undefined : typeof search[key] === 'string' ? search[key] as string : 'invalid';
  const query = new URLSearchParams();
  for (const key of ['scr_limit', ...Object.values(offsets), 'point_id', 'plan_id']) {
    const value = raw(key); if (value !== undefined) query.set(key, value);
  }
  const point = raw('point_id'), plan = raw('plan_id');
  const kinds: Kind[] = ['criteria','issues','points','plans'];
  if (point !== undefined) kinds.push('point_items'); if (plan !== undefined) kinds.push('plan_items');
  const path = `/changes/${encodeURIComponent(change.request_no)}`;
  const href = (key: string, value?: string, clear?: string) => {
    const q = new URLSearchParams(query); if (value === undefined) q.delete(key); else q.set(key, value);
    if (clear) q.delete(clear); return `${path}?${q}`;
  };
  const pages = await Promise.all(kinds.map(async kind => {
    const params = new URLSearchParams({change_id:change.id,limit:raw('scr_limit') ?? '50',offset:raw(offsets[kind]) ?? '0'});
    const endpoint = kind === 'point_items' ? `points/${encodeURIComponent(point || 'invalid')}/items` : kind === 'plan_items' ? `plans/${encodeURIComponent(plan || 'invalid')}/items` : kind;
    const result = await apiGet<Page>(`/api/v1/change-views/${encodeURIComponent(change.request_no)}/${endpoint}?${params}`);
    return result?.change_id === change.id && result.request_no === change.request_no &&
      (kind !== 'point_items' || result.point_id?.toLowerCase() === point?.toLowerCase()) &&
      (kind !== 'plan_items' || result.plan_id?.toLowerCase() === plan?.toLowerCase()) ? result : null;
  }));
  const full: Partial<Record<Kind,number>> = {criteria:change.criterion_count,issues:change.issue_count,points:change.point_count,plans:change.plan_count};
  return <Localized>
    <section className="panel"><h2><Localized>{'Complete SCR counts'}</Localized></h2><p className="muted"><Localized>{'All point DVP assignments'}</Localized>: {change.point_item_count} · <Localized>{'All plan DVP items'}</Localized>: {change.plan_item_count}</p>
      <p className="muted"><Localized>{'A link to a DVP item is a verification assignment; its execution history is shown on the item page.'}</Localized></p></section>
    {kinds.map((kind,index) => {
      const data = pages[index]; const total = full[kind] ?? data?.total;
      return <section className="panel tablewrap" key={kind}><h2><Localized>{titles[kind]}</Localized></h2>
        <p><Localized>{'Complete count'}</Localized>: {total ?? '—'} · <Localized>{'Records on this page'}</Localized>: {data ? data.items.length : '—'}</p>
        {kind === 'point_items' && <p><Localized>{'Selected change point'}</Localized>: {point}</p>}
        {kind === 'plan_items' && <p><Localized>{'Selected DVP plan'}</Localized>: {plan}</p>}
        {data ? <><table><thead><tr><th><Localized>{'Record'}</Localized></th><th><Localized>{'Description'}</Localized></th><th><Localized>{'Status'}</Localized></th><th><Localized>{'Linked DVP'}</Localized></th></tr></thead>
          <tbody>{data.items.map(row => <tr key={row.relation_id || row.id}>
            <td>{kind === 'issues' ? <Link href={`/issues/${encodeURIComponent(row.issue_no!)}`}>#{row.issue_no}</Link> : kind.endsWith('_items') ? <Link href={`/testing/dvp/${encodeURIComponent(row.id)}`}>{row.item_no}</Link> : <b>{row.criterion_no || row.change_no || row.plan_no}</b>}</td>
            <td><Localized>{row.title || row.description || '—'}</Localized>{row.title && row.description && <div><Localized>{row.description}</Localized></div>}{kind === 'issues' && <div><Localized>{row.relation_type}</Localized></div>}</td>
            <td><Localized>{row.status || '—'}</Localized></td>
            <td>{kind === 'points' || kind === 'plans' ? <><Localized>{'Complete count'}</Localized>: {row.item_count} <Link href={href(kind === 'points' ? 'point_id' : 'plan_id',row.id,kind === 'points' ? offsets.point_items : offsets.plan_items)}><Localized>{'View DVP items →'}</Localized></Link></> : '—'}</td>
          </tr>)}</tbody></table>
          {!data.items.length && <p className="muted"><Localized>{'No records on this page.'}</Localized></p>}
          <p><Link href={href(offsets[kind])}><Localized>{'First page'}</Localized></Link> {data.next_offset !== null && <Link href={href(offsets[kind],String(data.next_offset))}><Localized>{'Next page →'}</Localized></Link>}</p>
        </> : <p className="muted"><Localized>{'SCR collection page unavailable.'}</Localized></p>}
      </section>;
    })}
    {point === undefined && <section className="panel"><p><Localized>{'Select a change point to inspect its exact DVP assignments.'}</Localized></p></section>}
    {plan === undefined && <section className="panel"><p><Localized>{'Select a DVP plan to inspect its exact test items.'}</Localized></p></section>}
  </Localized>;
}
