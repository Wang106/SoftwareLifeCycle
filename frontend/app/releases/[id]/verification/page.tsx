import Link from 'next/link';
import { apiGet } from '../../../../lib/api';

type Verification={coverage:{change_coverage:number;issue_verification_coverage:number;dvp_execution_coverage:number;snapshot_match:boolean;snapshot_no:string|null};items:{item_no:string;title:string;scope:string;status:string;execution_no:number;result:string;snapshot_id:string;is_current_snapshot:boolean}[]};

const fallback:Verification={
  coverage:{change_coverage:100,issue_verification_coverage:100,dvp_execution_coverage:67,snapshot_match:true,snapshot_no:'SNAP-008'},
  items:[
    {item_no:'DVP-031',title:'Normal charging regression',scope:'SOFTWARE_TEST',status:'COMPLETED',execution_no:1,result:'PASS',snapshot_id:'SNAP-008',is_current_snapshot:true},
    {item_no:'DVP-032',title:'Low-temp charging timeout',scope:'SOFTWARE_TEST',status:'COMPLETED',execution_no:2,result:'PASS',snapshot_id:'SNAP-008',is_current_snapshot:true},
    {item_no:'DVP-033',title:'Calibration boundary verification',scope:'BATTERY_TEST',status:'COMPLETED',execution_no:1,result:'PASS',snapshot_id:'SNAP-008',is_current_snapshot:true}
  ]
};

export default async function Page(){
  const apiData=await apiGet<Verification>('/api/v1/releases/application/2.3.4/verification');
  const d=apiData||fallback;
  return <>
    <div className="cards">
      <div className="card"><span className="muted">Change Coverage</span><div className="metric">{d.coverage.change_coverage}%</div></div>
      <div className="card"><span className="muted">Issue Coverage</span><div className="metric">{d.coverage.issue_verification_coverage}%</div></div>
      <div className="card"><span className="muted">DVP Execution</span><div className="metric">{d.coverage.dvp_execution_coverage}%</div></div>
      <div className="card"><span className="muted">Snapshot Match</span><div className="metric">{d.coverage.snapshot_match?'PASS':'FAIL'}</div><small>{d.coverage.snapshot_no||'No snapshot'}</small></div>
    </div>
    <section className="panel">
      <div className="sectiontitle"><h2>Verification evidence</h2><Link href="/testing/dvp">Open DVP workspace →</Link></div>
      <table><thead><tr><th>DVP</th><th>Test Item</th><th>Scope</th><th>Execution</th><th>Result</th><th>Current Snapshot</th></tr></thead>
      <tbody>{d.items.map(r=><tr key={r.item_no}><td><b>{r.item_no}</b></td><td>{r.title}</td><td>{r.scope}</td><td>#{r.execution_no}</td><td><span className={'status '+(r.result==='PASS'?'pass':'warning')}>{r.result}</span></td><td>{r.is_current_snapshot?<span className="status pass">YES</span>:<span className="status warning">NO</span>}</td></tr>)}</tbody></table>
    </section>
    {!apiData&&<p className="datasource">Demo fallback active.</p>}
  </>;
}
