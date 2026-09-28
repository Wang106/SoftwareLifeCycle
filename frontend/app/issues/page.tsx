import Link from 'next/link';
import { apiGet } from '../../lib/api';

type IssueRow={id:string;issue_no:string;title:string;scope:string;severity:string;status:string;description?:string|null};
const fallback:IssueRow[]=[
{id:'1',issue_no:'310',title:'Low-temperature charging timeout',scope:'STANDARD',severity:'HIGH',status:'FIX_VERIFIED'},
{id:'2',issue_no:'327',title:'Customer A DVP-032 validation finding',scope:'APPLICATION',severity:'MEDIUM',status:'INVESTIGATING'},
{id:'3',issue_no:'402',title:'Programming failure on Line 2',scope:'DEPLOYMENT',severity:'HIGH',status:'OPEN'}
];
export default async function Page(){
 const apiRows=await apiGet<IssueRow[]>('/api/v1/issues');
 const rows=apiRows&&apiRows.length?apiRows:fallback;
 return <><div className="top"><div><div className="eyebrow">QUALITY & IMPACT</div><h1>Issues</h1><p className="muted">One issue truth across standard software, applications, distribution and production.</p></div><button>+ New Issue</button></div><div className="panel tablewrap"><table><thead><tr><th>Issue</th><th>Title</th><th>Scope</th><th>Severity</th><th>Status</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><Link href={'/issues/'+r.issue_no}><b>#{r.issue_no}</b></Link></td><td>{r.title}</td><td>{r.scope}</td><td>{r.severity}</td><td><span className={'status '+(r.status.includes('VERIFIED')?'pass':'warning')}>{r.status.replaceAll('_',' ')}</span></td></tr>)}</tbody></table></div>{!apiRows&&<p className="datasource">Demo fallback active · issue API will load automatically when backend is configured.</p>}</>
}