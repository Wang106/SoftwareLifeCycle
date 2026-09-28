import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Readiness={overall:string;approval_eligible:boolean;coverage:{snapshot_no:string|null};artifact_policy:{sha_completeness:number;policy_completeness:number};rules:{group:string;rule:string;raw:string;effective:string;evidence:string;exception_allowed?:boolean}[];exceptions:{exception_no:string;status:string}[]};
const fallback:Readiness={overall:'READY',approval_eligible:true,coverage:{snapshot_no:'SNAP-008'},artifact_policy:{sha_completeness:100,policy_completeness:100},rules:[],exceptions:[{exception_no:'PEX-0018',status:'APPROVED'}]};

export default async function Page(){
 const apiData=await apiGet<Readiness>('/api/v1/releases/application/2.3.4/readiness');
 const d=apiData||fallback;
 return <>
  <div className="grid2">
   <section className="panel"><div className="sectiontitle"><h2>APR-0121 · Release Approval</h2><span className={'status '+(d.approval_eligible?'warning':'')}>{d.approval_eligible?'READY TO SUBMIT':'BLOCKED'}</span></div><div className="kv"><span>Target</span><b>ASR 2.3.4 / {d.coverage.snapshot_no||'—'}</b><span>Readiness</span><b>{d.overall}</b><span>SHA completeness</span><b>{d.artifact_policy.sha_completeness}%</b><span>Policy completeness</span><b>{d.artifact_policy.policy_completeness}%</b></div></section>
   <section className="panel"><h2>Approval integrity</h2><p>Submission is only allowed when all non-exceptionable integrity and artifact-policy gates pass. The approval target is the immutable current snapshot.</p><div className="notice">{d.approval_eligible?'All blocking gates passed. Approval workflow may be created.':'Blocking readiness rules remain. Approval submission must stay disabled.'}</div></section>
  </div>
  <section className="panel"><h2>Gate summary before approval</h2><table><thead><tr><th>Gate</th><th>Rule</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{d.rules.length?d.rules.map(r=><tr key={r.group+r.rule}><td>{r.group}</td><td>{r.rule}</td><td><span className={'status '+(r.effective==='PASS'||r.effective==='EXCEPTION_GRANTED'?'pass':'warning')}>{r.effective}</span></td><td>{r.evidence}</td></tr>):<tr><td colSpan={4}>Demo workflow: all blocking gates passed; PEX-0018 approved.</td></tr>}</tbody></table></section>
  <section className="panel"><h2>Sequential approval workflow</h2><div className="approvalsteps"><div className="done"><b>1 · Software Lead</b><span>APPROVED · technical content</span></div><div className="done"><b>2 · Test Lead</b><span>APPROVED · verification evidence</span></div><div className="current"><b>3 · Quality Manager</b><span>PENDING · governance & exception</span></div><div><b>4 · Release Manager</b><span>WAITING · final release decision</span></div></div></section>
  <div className="nextbar"><span>{d.approval_eligible?'Release is eligible for approval submission.':'Resolve blocking gates before submission.'}</span><Link className="button" href="/releases/demo/passport">Preview Software Passport →</Link></div>
  {!apiData&&<p className="datasource">Demo fallback active.</p>}
 </>;
}
