import { apiGet } from '../../../../lib/api';

type ArtifactRule={recipient_type:string;purpose:string;recipient_code:string|null;decision:string};
type ArtifactRow={id:string;filename:string;artifact_type:string;component_version:string|null;sha256:string|null;classification:string;distribution_level:string|null;ai_access_policy:string;policy_rules:ArtifactRule[]};
type ArtifactData={summary:{artifact_total:number;sha_complete:number;sha_completeness:number;policy_complete:number;policy_completeness:number;externally_eligible:number;approval_required:number;internal_only:number};artifacts:ArtifactRow[]};

const fallback:ArtifactData={
 summary:{artifact_total:3,sha_complete:3,sha_completeness:100,policy_complete:3,policy_completeness:100,externally_eligible:1,approval_required:1,internal_only:1},
 artifacts:[
  {id:'1',filename:'CustomerA_BMS.hex',artifact_type:'HEX',component_version:'2.3.4',sha256:'9f8a…d12c',classification:'CONFIDENTIAL',distribution_level:'EXTERNAL',ai_access_policy:'DENY',policy_rules:[{recipient_type:'CUSTOMER',purpose:'PRODUCTION',recipient_code:'CUS-001',decision:'ALLOW'}]},
  {id:'2',filename:'BMS.elf',artifact_type:'ELF',component_version:'2.3.4',sha256:'a102…8bc1',classification:'STRICTLY_CONFIDENTIAL',distribution_level:'INTERNAL_ONLY',ai_access_policy:'LOCAL_ONLY',policy_rules:[]},
  {id:'3',filename:'CustomerA_BMS.a2l',artifact_type:'A2L',component_version:'CAL-32',sha256:'7ac9…33ef',classification:'CONFIDENTIAL',distribution_level:'CONTROLLED_EXTERNAL',ai_access_policy:'LOCAL_ONLY',policy_rules:[{recipient_type:'CUSTOMER',purpose:'PRODUCTION',recipient_code:'CUS-001',decision:'APPROVAL_REQUIRED'}]}
 ]
};

export default async function Page(){
 const apiData=await apiGet<ArtifactData>('/api/v1/releases/application/2.3.4/artifacts');
 const d=apiData||fallback;
 return <>
  <div className="cards">
   <div className="card"><span className="muted">Artifacts</span><div className="metric">{d.summary.artifact_total}</div><small>Formal release artifacts</small></div>
   <div className="card"><span className="muted">SHA Complete</span><div className="metric">{d.summary.sha_completeness}%</div><small>{d.summary.sha_complete} / {d.summary.artifact_total}</small></div>
   <div className="card"><span className="muted">Policy Complete</span><div className="metric">{d.summary.policy_completeness}%</div><small>{d.summary.policy_complete} / {d.summary.artifact_total}</small></div>
   <div className="card"><span className="muted">External Control</span><div className="metric">{d.summary.externally_eligible + d.summary.approval_required}</div><small>{d.summary.approval_required} approval required</small></div>
  </div>
  <section className="panel tablewrap">
   <table><thead><tr><th>Artifact</th><th>Type / Version</th><th>SHA-256</th><th>Classification</th><th>Distribution</th><th>Policy Rules</th></tr></thead>
   <tbody>{d.artifacts.map(a=><tr key={a.id}>
    <td><b>{a.filename}</b></td>
    <td>{a.artifact_type} · {a.component_version||'—'}</td>
    <td><code>{a.sha256?String(a.sha256).slice(0,12)+'…':'MISSING'}</code></td>
    <td>{a.classification}</td>
    <td><span className={'status '+(a.distribution_level==='INTERNAL_ONLY'?'':a.distribution_level==='CONTROLLED_EXTERNAL'?'warning':'pass')}>{a.distribution_level||'MISSING'}</span></td>
    <td>{a.distribution_level==='INTERNAL_ONLY'?<span>Implicit DENY external</span>:a.policy_rules.length?a.policy_rules.map((r,i)=><span key={i} className={'status '+(r.decision==='ALLOW'?'pass':r.decision==='APPROVAL_REQUIRED'?'warning':'')}>{r.recipient_code||r.recipient_type} · {r.purpose} · {r.decision}</span>):<span className="status warning">MISSING</span>}</td>
   </tr>)}</tbody></table>
  </section>
  {!apiData&&<p className="datasource">Demo fallback active · artifact policy API will load automatically when backend is configured.</p>}
 </>;
}
