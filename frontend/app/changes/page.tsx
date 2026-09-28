import Link from 'next/link';
import { apiGet } from '../../lib/api';

type ChangeRow={id:string;request_no:string;title:string;source:string;scope:string;change_type:string;status:string};
const fallback:ChangeRow[]=[
{id:'demo-1',request_no:'SCR-142',title:'Charging timeout & low-temperature calibration',source:'ISSUE',scope:'STANDARD',change_type:'BUG FIX',status:'IN TEST'},
{id:'demo-2',request_no:'SCR-139',title:'Customer A diagnostic DID update',source:'CUSTOMER',scope:'APPLICATION',change_type:'INTERFACE CHANGE',status:'RELEASED'},
{id:'demo-3',request_no:'SCR-136',title:'Bootloader programming robustness',source:'INTERNAL',scope:'STANDARD',change_type:'IMPROVEMENT',status:'DEVELOPMENT COMPLETED'}
];
export default async function Page(){
 const apiRows=await apiGet<ChangeRow[]>('/api/v1/changes');
 const rows=apiRows&&apiRows.length?apiRows:fallback;
 return <><div className="top"><div><div className="eyebrow">CHANGE CONTROL</div><h1>Software Change Requests</h1><p className="muted">From approved requirement to verified software change and release traceability.</p></div><button>+ New SCR</button></div><div className="summary"><div><b>{rows.length}</b><span>Visible SCR</span></div><div><b>{rows.filter(r=>r.status.includes('TEST')).length}</b><span>In Verification</span></div><div><b>{rows.filter(r=>r.status.includes('READY')).length}</b><span>Ready for Release</span></div></div><div className="panel tablewrap"><table><thead><tr><th>SCR</th><th>Title</th><th>Source</th><th>Scope</th><th>Type</th><th>Status</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{r.request_no==='SCR-142'?<Link href="/changes/SCR-142"><b>{r.request_no}</b></Link>:r.request_no}</td><td>{r.title}</td><td>{r.source}</td><td>{r.scope}</td><td>{r.change_type}</td><td><span className={'status '+r.status.toLowerCase().replaceAll(' ','-')}>{r.status}</span></td></tr>)}</tbody></table></div>{!apiRows&&<p className="datasource">Demo fallback active · configure NEXT_PUBLIC_API_BASE_URL to load FastAPI data.</p>}</>
}