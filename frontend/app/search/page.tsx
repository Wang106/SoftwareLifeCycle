import Link from 'next/link';
import { apiGet } from '../../lib/api';

type SearchResult = { type: string; label: string; description: string; href: string };
type SearchResponse = { query: string; results: SearchResult[] };

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const params = await searchParams;
  const query = (params.q || '').trim().slice(0, 100);
  const response = query ? await apiGet<SearchResponse>(`/api/v1/search?q=${encodeURIComponent(query)}`) : null;
  return <>
    <div className="top"><div><div className="eyebrow">GLOBAL SEARCH</div><h1>Search</h1><p className="muted">Search by release, snapshot, SCR, issue, artifact filename, SHA, customer, project or batch.</p></div></div>
    <form className="searchpage" action="/search" method="get">
      <input name="q" maxLength={100} defaultValue={query} aria-label="Search lifecycle records" placeholder="Try: SNAP-008, SCR-142, CustomerA_BMS.hex, PB-1005-A…" required />
      <button type="submit">Search</button>
    </form>
    {query && response && <section className="panel"><h2>{response.results.length} result{response.results.length === 1 ? '' : 's'} for “{query}”</h2>
      {response.results.length ? <div className="searchresults">{response.results.map((row, index) => <Link key={`${row.type}-${row.label}-${index}`} href={row.href}><b>{row.label}</b><span>{row.type} · {row.description}</span></Link>)}</div> : <p className="muted">No matching records.</p>}
    </section>}
    {query && !response && <section className="panel"><h2>Search unavailable</h2><p className="muted">The lifecycle API could not be reached. Please try again after it is connected.</p></section>}
    {!query && <section className="panel"><h2>Find a record</h2><p className="muted">Enter an identifier, name, filename or SHA-256 fragment to search lifecycle records.</p></section>}
  </>;
}
