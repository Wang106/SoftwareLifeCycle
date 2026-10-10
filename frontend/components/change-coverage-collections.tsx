import Link from 'next/link';
import { Localized } from './localized';
import { apiGet } from '../lib/api';
import { rawCoverage, matchingCoverage, type CoverageSearch, type CoverageSummary, type CoveragePage, type CoverageRow, type SelectedCoverage } from '../lib/change-coverage-views';

type Kind = 'candidates'|'gaps'|'acceptance'|'points'|'issues'|'items'|'group_items'|'assignments';
const offsets:Record<Kind,string> = {candidates:'candidates_offset',gaps:'gaps_offset',acceptance:'acceptance_offset',points:'coverage_points_offset',issues:'coverage_issues_offset',items:'coverage_items_offset',group_items:'group_items_offset',assignments:'assignments_offset'};
const titles:Record<Kind,string> = {candidates:'Candidate releases for coverage review',gaps:'Definition and assignment gaps',acceptance:'Acceptance criteria',points:'Change points',issues:'Linked issues',items:'All DVP items in SCR plans',group_items:'Selected group DVP items',assignments:'Selected criterion assignment records'};

function TestCells({row}:{row:CoverageRow}) {
  return <Localized><td><Link href={`/testing/dvp/${encodeURIComponent(row.id)}`}>{row.item_no}</Link><p><code>{row.id}</code></p></td>
    <td><Localized>{row.title}</Localized> · <Localized>{row.scope}</Localized><div><Localized>{row.declared_status}</Localized></div></td>
    <td>{row.execution_no !== null && row.execution_no !== undefined ? <><Localized>{'Execution number'}</Localized>: {row.execution_no} · <Localized>{row.result}</Localized><p>{row.executed_at}</p></> : <Localized>{'No matching execution'}</Localized>}</td>
    <td><Localized>{row.actual_result || '—'}</Localized></td></Localized>;
}

function AssignmentHistory({row}:{row:CoverageRow}) {
  const audit=(id:string)=>'/activity/'+encodeURIComponent('EVT-AC-'+id);
  return <Localized>
    {row.action&&<p><Localized>{row.action}</Localized></p>}
    {row.effective!==undefined&&<p><Localized>{row.effective?'Effective assignment':'Historical assignment only'}</Localized></p>}
    {row.supersedes_id&&<p><Localized>{'Replaces or withdraws assignment'}</Localized>: <code>{row.supersedes_id}</code> <Link href={audit(row.supersedes_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open predecessor audit'}</Localized></Link></p>}
    {row.superseded_by_id&&<p><Localized>{'Assignment ended by record'}</Localized>: <code>{row.superseded_by_id}</code> <Link href={audit(row.superseded_by_id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open replacement audit'}</Localized></Link></p>}
    <Link href={audit(row.id)} target="_blank" rel="noopener noreferrer" prefetch={false}><Localized>{'Open original audit'}</Localized></Link>
  </Localized>;
}

export default async function ChangeCoverageCollections({data,search}:{data:CoverageSummary;search:CoverageSearch}) {
  const path=`/changes/${encodeURIComponent(data.request_no)}/coverage`;
  const base=`/api/v1/change-coverage-views/${encodeURIComponent(data.request_no)}`;
  const query=new URLSearchParams();
  if(data.release_id!=='none') {query.set('release_id',data.release_id);query.set('snapshot_id',data.snapshot_id);}
  for(const key of ['coverage_limit',...Object.values(offsets),'group_kind','group_id']) {const value=rawCoverage(search,key);if(value!==undefined)query.set(key,value);}
  const href=(key:string,value?:string,clear:string[]=[])=>{const q=new URLSearchParams(query);if(value===undefined)q.delete(key);else q.set(key,value);for(const field of clear)q.delete(field);return `${path}?${q}`;};
  const params=(kind:Kind)=>new URLSearchParams({change_id:data.change_id,release_id:data.release_id,snapshot_id:data.snapshot_id,limit:rawCoverage(search,'coverage_limit')??'50',offset:rawCoverage(search,offsets[kind])??'0'});
  const groupKind=rawCoverage(search,'group_kind'),groupId=rawCoverage(search,'group_id');
  const selected=groupKind!==undefined||groupId!==undefined;
  const groupBase=`${base}/groups/${encodeURIComponent(groupKind||'invalid')}/${encodeURIComponent(groupId||'invalid')}`;
  const kinds:Kind[]=['candidates','gaps','acceptance','points','issues','items'];
  const [pages,selection]=await Promise.all([
    Promise.all(kinds.map(async kind=>{
      const endpoint=['acceptance','points','issues'].includes(kind)?`groups/${kind}`:kind;
      const page=await apiGet<CoveragePage>(`${base}/${endpoint}?${params(kind)}`);
      return matchingCoverage(page,data) && (!['acceptance','points','issues'].includes(kind)||page?.kind===kind)?page:null;
    })),
    selected?apiGet<SelectedCoverage>(`${groupBase}/summary?${params('group_items')}`):Promise.resolve(null)
  ]);
  const group=matchingCoverage(selection,data)&&selection?.kind===groupKind&&selection.group_id.toLowerCase()===groupId?.toLowerCase()?selection:null;
  if(selected){
    kinds.push('group_items');if(groupKind==='acceptance')kinds.push('assignments');
    const children=await Promise.all(kinds.slice(6).map(async kind=>{
      if(!group)return null;
      const endpoint=kind==='assignments'?`${base}/acceptance/${encodeURIComponent(groupId!)}/assignments`:`${groupBase}/items`;
      const page=await apiGet<CoveragePage>(`${endpoint}?${params(kind)}`);
      return matchingCoverage(page,data)&&page?.kind===groupKind&&page.group_id?.toLowerCase()===groupId?.toLowerCase()?page:null;
    }));pages.push(...children);
  }
  const total:Partial<Record<Kind,number>>={candidates:data.candidate_count,gaps:data.gap_count,acceptance:data.summary.acceptance.total,points:data.summary.change_points.total,issues:data.summary.issues.total,items:data.summary.dvp.total,group_items:group?.item_count,assignments:group?.assignment_count};
  const select=(kind:Kind,row:CoverageRow)=>{
    const q=new URLSearchParams(query);q.set('group_kind',kind);q.set('group_id',row.id);q.delete(offsets.group_items);q.delete(offsets.assignments);return `${path}?${q}`;
  };
  return <Localized>
    <section className="panel"><h2><Localized>{'Paged coverage evidence'}</Localized></h2><p className="muted"><Localized>{'Definitions and assignments remain live; the selected frozen snapshot pins execution evidence only.'}</Localized></p>
      <p className="muted"><Localized>{'Only effective assignments count toward coverage. Replacement and withdrawal preserve history and do not prove test success or acceptance.'}</Localized></p>
      <p className="muted"><Localized>{'The latest execution number is selected within the exact release and frozen snapshot. An earlier PASS cannot override a later FAIL.'}</Localized></p>
      {group?<><p><Localized>{'Selected coverage group'}</Localized>: {group.ref} · <code>{group.group_id}</code> · <Localized>{group.verification?.replaceAll('_',' ')}</Localized></p><p><Localized>{group.description}</Localized></p><p><Localized>{'Assigned DVP'}</Localized>: {group.item_count} · <Localized>{'Excluded outside-SCR links'}</Localized>: {group.excluded_link_count}</p>
        {group.kind==='acceptance'&&<Link href={`/commands?${new URLSearchParams({operation:'acceptance',target:data.request_no,criterion:group.group_id})}`}><Localized>{'Prepare DVP assignment →'}</Localized></Link>}
      </>:selected?<p><Localized>{'Selected coverage group unavailable.'}</Localized></p>:<p><Localized>{'Select a coverage row to inspect its DVP items and assignment records.'}</Localized></p>}
    </section>
    {kinds.map((kind,index)=>{const page=pages[index];return <section className="panel tablewrap" key={kind}><h2><Localized>{titles[kind]}</Localized></h2>
      <p><Localized>{'Complete count'}</Localized>: {total[kind]??page?.total??'—'} · <Localized>{'Records on this page'}</Localized>: {page?page.items.length:'—'}</p>
      {page?<><table><thead><tr><th><Localized>{'Reference'}</Localized></th><th><Localized>{'Description'}</Localized></th><th><Localized>{'Status / Evidence'}</Localized></th><th><Localized>{'Review'}</Localized></th></tr></thead><tbody>{page.items.map((row,i)=><tr key={row.id||`${row.code}:${row.owner_id}:${row.ref}:${i}`}>
        {kind==='items'||kind==='group_items'?<TestCells row={row}/>:kind==='candidates'?<><td>{row.type==='APPLICATION'?'ASR':'SSR'} {row.version}<p><code>{row.id}</code></p></td><td><Localized>{row.status}</Localized></td><td>—</td><td><Link href={`${path}?${new URLSearchParams({release_id:row.id})}`}><Localized>{'Review this release →'}</Localized></Link></td></>:kind==='gaps'?<><td>{row.ref}<p><code>{row.owner_id}</code></p></td><td><Localized>{row.message}</Localized></td><td><Localized>{row.code}</Localized></td><td>—</td></>:kind==='assignments'?<><td><code>{row.id}</code><p><Link href={`/testing/dvp/${encodeURIComponent(row.dvp_item_id!)}`}>{row.dvp_item_id}</Link></p></td><td><Localized>{row.reason}</Localized></td><td><Localized>{'Declared reviewer'}</Localized>: {row.actor_name}<p>{row.created_at}</p></td><td><AssignmentHistory row={row}/></td></>:<><td>{kind==='issues'?<Link href={`/issues/${encodeURIComponent(row.ref!)}`}>#{row.ref}</Link>:row.ref}<p><code>{row.id}</code></p></td><td><Localized>{row.description}</Localized></td><td><Localized>{row.verification?.replaceAll('_',' ')}</Localized><p><Localized>{'Assigned DVP'}</Localized>: {row.item_count} · <Localized>{'Excluded outside-SCR links'}</Localized>: {row.excluded_link_count}</p></td><td><Link href={select(kind,row)}><Localized>{'Inspect coverage row →'}</Localized></Link>{kind==='acceptance'&&<p><Link href={`/commands?${new URLSearchParams({operation:'acceptance',target:data.request_no,criterion:row.id})}`}><Localized>{'Prepare DVP assignment →'}</Localized></Link></p>}</td></>}
      </tr>)}</tbody></table>{!page.items.length&&<p><Localized>{'No records on this page.'}</Localized></p>}<p><Link href={href(offsets[kind])}><Localized>{'First page'}</Localized></Link> {page.next_offset!==null&&<Link href={href(offsets[kind],String(page.next_offset))}><Localized>{'Next page →'}</Localized></Link>}</p></>:<p><Localized>{'Coverage collection page unavailable.'}</Localized></p>}
    </section>;})}
  </Localized>;
}
