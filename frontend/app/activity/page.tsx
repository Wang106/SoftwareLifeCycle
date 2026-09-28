import Link from 'next/link';
const events=[
['10:17','DEPLOYMENT','Cloudflare build completed','softwarelifecycle · version 55f03393'],
['09:52','APPROVAL','APR-0121 submitted','ASR 2.3.4 · SNAP-008'],
['09:36','READINESS','Readiness evaluated','READY · PEX-0018 applied'],
['09:10','SNAPSHOT','SNAP-008 frozen','18 artifacts · policy hash included'],
['08:44','TEST','DVP-032 Execution #2 PASS','TR-0061 · SNAP-008'],
['08:02','CHANGE','SCR-142 moved to IN TEST','CP-001 / CP-002 linked']
];
export default function Page(){return <><div className="top"><div><div className="eyebrow">AUDIT & ACTIVITY</div><h1>Activity</h1><p className="muted">Chronological domain history for formal lifecycle actions and operational events.</p></div><span className="badge">AUDIT ENABLED</span></div><section className="panel"><div className="activitylist">{events.map(e=><div className="activityitem" key={e[0]+e[2]}><time>{e[0]}</time><span className="activitytype">{e[1]}</span><div><b>{e[2]}</b><small>{e[3]}</small></div></div>)}</div></section><section className="panel"><h2>Audit principles</h2><div className="grid2"><div className="notice">Formal records are append-only. Retests, package revisions and approval returns create new history instead of overwriting prior evidence.</div><div className="notice">Snapshots, approval targets and released artifacts are immutable. Integrity-relevant changes require a new formal object.</div></div></section></>}
