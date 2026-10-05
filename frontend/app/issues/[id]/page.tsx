import { Localized } from '../../../components/localized';
import IssueCollections from '../../../components/issue-collections';
import Link from 'next/link';
import { apiGet } from '../../../lib/api';
import type { IssueSummary,IssueSearch } from '../../../lib/issue-views';
export default async function Page({params,searchParams}:{params:Promise<{id:string}>;searchParams:Promise<IssueSearch>}) {
  const {id}=await params;const data=await apiGet<IssueSummary>(`/api/v1/issue-views/${encodeURIComponent(id)}/summary`);
  if(!data||data.issue_no!==id)return <section className="panel"><h1><Localized>{'Issue unavailable'}</Localized></h1><p><Localized>{'The issue was not found or the API could not be reached.'}</Localized></p><Link href="/issues"><Localized>{'Back to issues →'}</Localized></Link></section>;
  return <Localized>
    <p><Link href={`/resources?entity_type=ISSUE&entity_id=${data.id}`}><Localized>{'Materials & evidence references →'}</Localized></Link></p>
    <div className="top"><div><div className="eyebrow"><Localized>{'ISSUE #'}</Localized>{data.issue_no} · <Localized>{data.scope}</Localized></div><h1><Localized>{data.title}</Localized></h1><p><Localized>{'Severity '}</Localized><Localized>{data.severity}</Localized> · <Localized>{data.description||'No description recorded.'}</Localized></p></div><span className={'status '+(data.status.includes('VERIFIED')||data.status==='CLOSED'?'pass':'warning')}><Localized>{data.status.replaceAll('_',' ')}</Localized></span></div>
    <section className="panel"><h2><Localized>{'Issue assessment'}</Localized></h2><p><Localized>{'Linked SCR'}</Localized>: {data.linked_count} · <Localized>{'Candidate release count'}</Localized>: {data.candidate_count} · <Localized>{'Manual judgment count'}</Localized>: {data.assessment_count}</p><p><Localized>{data.basis}</Localized></p><p className="muted"><Localized>{'Candidates and deployment counts are review leads, not confirmed issue impact.'}</Localized></p></section>
    <IssueCollections data={data} search={await searchParams}/>
  </Localized>;
}
