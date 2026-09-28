import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Readiness={
  overall:string;
  coverage:{snapshot_no:string|null;dvp_execution_coverage:number};
  artifact_policy?:{sha_completeness:number;policy_completeness:number};
  rules:{group:string;rule:string;raw:string;effective:string;evidence:string}[];
  exceptions:{exception_no:string;status:string;scope:string;reason:string;snapshot_no:string|null}[];
};

const fallback:Readiness={
  overall:'READY',
  coverage:{snapshot_no:'SNAP-008',dvp_execution_coverage:67},
  artifact_policy:{sha_completeness:100,policy_completeness:100},
  rules:[
    {group:'Change Control',rule:'Required changes linked to DVP',raw:'PASS',effective:'PASS',evidence:'2 / 2'},
    {group:'Issue Control',rule:'Verification-required issues linked to DVP',raw:'PASS',effective:'PASS',evidence:'1 / 1'},
    {group:'Verification',rule:'Required DVP executed on current snapshot',raw:'FAIL',effective:'EXCEPTION_GRANTED',evidence:'2 / 3'},
    {group:'Software Integrity',rule:'Tested snapshot equals current snapshot',raw:'PASS',effective:'PASS',evidence:'SNAP-008'},
    {group:'Software Integrity',rule:'Current snapshot is frozen',raw:'PASS',effective:'PASS',evidence:'FROZEN'},
    {group:'Artifact Control',rule:'SHA-256 complete for formal artifacts',raw:'PASS',effective:'PASS',evidence:'3 / 3'},
    {group:'Distribution Control',rule:'Artifact distribution policy complete',raw:'PASS',effective:'PASS',evidence:'3 / 3'},
    {group:'Governance',rule:'Approved exceptions are bound to current snapshot',raw:'PASS',effective:'PASS',evidence:'1 current-snapshot exception'}
  ],
  exceptions:[
    {exception_no:'PEX-0018',status:'APPROVED',scope:'Verification',reason:'DVP-034 endurance test pending',snapshot_no:'SNAP-008'}
  ]
};

export default async function Page(){
  const apiData=await apiGet<Readiness>('/api/v1/releases/application/2.3.4/readiness');
  const d=apiData||fallback;
  const rawPass=d.rules.filter(r=>r.raw==='PASS').length;
  return <>
    <div className="readinessHero">
      <div>
        <span className="eyebrow">RELEASE READINESS ASSESSMENT</span>
        <h2>{d.overall} <small>{d.exceptions.length?'with '+d.exceptions.length+' governed exception':'without exception'}</small></h2>
        <p>Raw facts are preserved. Approved exceptions affect the effective result without rewriting the raw result.</p>
      </div>
      <div className="score">{rawPass}<span>/{d.rules.length} raw pass</span></div>
    </div>
    <section className="panel tablewrap">
      <table><thead><tr><th>Gate</th><th>Rule</th><th>Raw</th><th>Effective</th><th>Evidence</th></tr></thead>
      <tbody>{d.rules.map(r=><tr key={r.group+r.rule}><td><b>{r.group}</b></td><td>{r.rule}</td><td><span className={'status '+(r.raw==='PASS'?'pass':'warning')}>{r.raw}</span></td><td>{r.effective}</td><td>{r.evidence}</td></tr>)}</tbody></table>
    </section>
    {d.exceptions.map(ex=><section className="panel" key={ex.exception_no}>
      <div className="sectiontitle">
        <div><h2>{ex.exception_no} · {ex.scope} exception</h2><p className="muted">Bound to {ex.snapshot_no||'current snapshot'}.</p></div>
        <span className="status pass">{ex.status}</span>
      </div>
      <div className="kv"><span>Reason</span><b>{ex.reason}</b><span>Snapshot</span><b>{ex.snapshot_no||'—'}</b></div>
    </section>)}
    <div className="nextbar"><span>{d.overall==='READY'?'Assessment is ready for approval submission.':'Blocking rules remain.'}</span><Link className="button" href="/releases/demo/approval">Continue to Approval →</Link></div>
    {!apiData&&<p className="datasource">Demo fallback active.</p>}
  </>;
}
