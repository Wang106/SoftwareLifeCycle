import { Localized } from '../../../components/localized';
import ChangeCollections from '../../../components/change-collections';
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { ChangeSummary, ChangeSearch } from '../../../lib/change-views';

export default async function Page({params,searchParams}: {params: Promise<{id:string}>;searchParams:Promise<ChangeSearch>}) {
  const {id} = await params;
  const change = await apiGet<ChangeSummary>(`/api/v1/change-views/${encodeURIComponent(id)}/summary`);
  if (!change || change.request_no !== id) return <section className="panel"><h1><Localized>{'Change request unavailable'}</Localized></h1><p className="muted"><Localized>{'The request was not found or the API could not be reached.'}</Localized></p><Link href="/changes"><Localized>{'← All change requests'}</Localized></Link></section>;
  return <Localized>
    <p><Link href={`/resources?entity_type=SCR&entity_id=${change.id}`}><Localized>{'Materials & evidence references →'}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{'SOFTWARE CHANGE REQUEST · '}</Localized>{change.request_no}</div><h1><Localized>{change.title}</Localized></h1>
      <p className="muted"><Localized>{change.scope}</Localized> · <Localized>{change.change_type}</Localized> · <Localized>{'Source'}</Localized>: <Localized>{change.source}</Localized></p></div>
      <span className={'status ' + (change.status.includes('READY') || change.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{change.status.replaceAll('_',' ')}</Localized></span></div>
    <section className="panel"><h2><Localized>{'Requirement'}</Localized></h2><p><Localized>{change.requirement || 'No requirement recorded.'}</Localized></p>
      <div className="kv"><span><Localized>{'Background'}</Localized></span><b><Localized>{change.background || '—'}</Localized></b>
        <span><Localized>{'Software'}</Localized></span><b>{change.software ? <Localized>{`${change.software.name} · ${change.software.code}`}</Localized> : '—'}</b>
        <span><Localized>{'Customer'}</Localized></span><b>{change.customer ? <Link href={`/customers/${encodeURIComponent(change.customer.code)}`}>{change.customer.name}</Link> : '—'}</b>
        <span><Localized>{'Project'}</Localized></span><b>{change.project ? <Link href={`/projects/${encodeURIComponent(change.project.id)}`}>{change.project.name}</Link> : '—'}</b>
      </div></section>
    <section className="panel"><h2><Localized>{'Coverage review'}</Localized></h2><p><Localized>{'Review acceptance assignments, missing verification links, and execution evidence for a selected release and frozen snapshot.'}</Localized></p><Link href={`/changes/${encodeURIComponent(id)}/coverage`}><Localized>{'Open completeness and coverage report →'}</Localized></Link></section>
    <ChangeCollections change={change} search={await searchParams}/>
    <p className="datasource"><Link href="/changes"><Localized>{'← All change requests'}</Localized></Link></p>
  </Localized>;
}
