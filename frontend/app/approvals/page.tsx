import Link from 'next/link';
import { apiGet } from '../../lib/api';

type Approval={id:string;approval_no:string;target_type:string;target_id:string;snapshot_id:string|null;status:string;submitted_by:string|null};
const fallback:Approval[]=[{id:'1',approval_no:'APR-0121',target_type:'RELEASE',target_id:'demo',snapshot_id:'SNAP-008',status:'PENDING',submitted_by:'Release Manager'}];

export default async function Page(){
 const apiRows=await apiGet<Approval[]>('/api/v1/approvals');
 const rows=apiRows&&apiRows.length?apiRows:fallback;
 return <><div className="top"><div><div className="eyebrow">GOVERNANCE</div><h1>Approvals</h1><p className="muted">Formal approval requests with immutable targets and append-only decision history.</p></div><Link className="button" href="/create">+ Create</Link></div><div className="cards"><div className="card"><span className="muted">PENDING</span><div className="metric">{rows.filter(r=>r.status==='PENDING').length}</div></div><div className="card"><span className="muted">APPROVED</span><div className="metric">{rows.filter(r=>r.status==='APPROVED').length}</div></div><div className="card"><span className="muted">RETURNED</span><div className="metric">{rows.filter(r=>r.status==='RETURNED').length}</div></div><div className="card"><span className="muted">TOTAL</span><div className="metric">{rows.length}</div></div></div><section className="panel tablewrap"><table><thead><tr><th>Approval</th><th>Type</th><th>Snapshot-bound</th><th>Status</th><th>Submitted By</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><Link href={'/approvals/'+r.approval_no}><b>{r.approval_no}</b></Link></td><td>{r.target_type}</td><td>{r.snapshot_id?'YES':'NO'}</td><td><span className={'status '+(r.status==='APPROVED'?'pass':'warning')}>{r.status}</span></td><td>{r.submitted_by||'—'}</td></tr>)}</tbody></table></section>{!apiRows&&<p className="datasource">Demo fallback active.</p>}</>
}