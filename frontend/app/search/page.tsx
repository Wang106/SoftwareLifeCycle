
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';

type SearchResult = { type: string; label: string; description: string; href: string };
type SearchResponse = { query: string; results: SearchResult[] };

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const params = await searchParams;
  const query = (params.q || '').trim().slice(0, 100);
  const response = query ? await apiGet<SearchResponse>(`/api/v1/search?q=${encodeURIComponent(query)}`) : null;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"GLOBAL SEARCH"}</Localized></div><h1><Localized>{"Search"}</Localized></h1><p className="muted"><Localized>{"Search by release, snapshot, SCR, issue, artifact filename, SHA, customer, project or batch."}</Localized></p></div></div>
    <form className="searchpage" action="/search" method="get">
      <LocalizedAttributes><input name="q" maxLength={100} defaultValue={query} aria-label="Search lifecycle records" placeholder="Try: SNAP-008, SCR-142, CustomerA_BMS.hex, PB-1005-A…" required /></LocalizedAttributes>
      <button type="submit"><Localized>{"Search"}</Localized></button>
    </form>
    <Localized>{query && response && <section className="panel"><h2><Localized>{response.results.length}</Localized><Localized>{" result"}</Localized><Localized>{response.results.length === 1 ? '' : 's'}</Localized><Localized>{" for “"}</Localized><Localized>{query}</Localized><Localized>{"”"}</Localized></h2>
      <Localized>{response.results.length ? <div className="searchresults"><Localized>{response.results.map((row, index) => <Link key={`${row.type}-${row.label}-${index}`} href={row.href}><b><Localized>{row.label}</Localized></b><span><Localized>{row.type}</Localized><Localized>{" · "}</Localized><Localized>{row.description}</Localized></span></Link>)}</Localized></div> : <p className="muted"><Localized>{"No matching records."}</Localized></p>}</Localized>
    </section>}</Localized>
    <Localized>{query && !response && <section className="panel"><h2><Localized>{"Search unavailable"}</Localized></h2><p className="muted"><Localized>{"The lifecycle API could not be reached. Please try again after it is connected."}</Localized></p></section>}</Localized>
    <Localized>{!query && <section className="panel"><h2><Localized>{"Find a record"}</Localized></h2><p className="muted"><Localized>{"Enter an identifier, name, filename or SHA-256 fragment to search lifecycle records."}</Localized></p></section>}</Localized>
  </>;
}
