'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import type {PrincipalReview} from '../lib/principal-status-draft';
import type {GrantReview} from '../lib/grant-status-draft';
import {exportAdminStatusRecovery,importAdminStatusRecovery,type ImportedAdminStatusRecovery} from '../lib/admin-status-recovery';
type Kind='PRINCIPAL'|'GLOBAL'|'PROJECT'|'SOFTWARE';
export default function AdminStatusRecoveryPanel({kind,id,review=null,recoveryEnabled=false,guard,onLock}:{kind:Kind;id:string;review?:PrincipalReview|GrantReview|null;recoveryEnabled?:boolean;guard:(mode:'import'|'export')=>boolean;onLock:(locked:boolean)=>void}){
 const [text,setText]=useState(''),[message,setMessage]=useState(''),[revealed,setRevealed]=useState(false),[copying,setCopying]=useState(false),[state,setState]=useState<ImportedAdminStatusRecovery['state']|null>(null);
 const controller=useRef<ImportedAdminStatusRecovery|null>(null),source=useRef(''),pending=useRef(false);
 const current=useRef({kind,id,review,recoveryEnabled,guard,onLock});current.current={kind,id,review,recoveryEnabled,guard,onLock};
 const key=JSON.stringify([kind,id.toLowerCase()]),previous=useRef(key);
 useEffect(()=>{if(previous.current!==key){previous.current=key;if(!controller.current){source.current='';setText('');setMessage('');setRevealed(false);}}},[key]);
 useEffect(()=>{if(!state||state.phase==='confirmed')return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[state?.phase]);
 const same=()=>current.current.kind===kind&&current.current.id.toLowerCase()===id.toLowerCase();
 const usable=()=>same()&&!pending.current&&!controller.current&&review?.confirmed===true&&current.current.review===review&&current.current.guard('export');
 function stage(){if(!same()||pending.current||controller.current||source.current!==text||!current.current.guard('import'))return;
  try{const restored=importAdminStatusRecovery(text,window.location.origin),c=restored.state.command;if(c.kind!==kind||c.id!==id.toLowerCase())throw Error('target');controller.current=restored;current.current.onLock(true);setState(restored.state);source.current='';setText('');setRevealed(false);setMessage('');}
  catch{setMessage('Status recovery text is invalid or does not match this site and exact target. Nothing was sent.');}}
 async function query(){if(pending.current||!controller.current||!current.current.recoveryEnabled)return;const task=controller.current.recover(current.current.recoveryEnabled);setState(controller.current.state);setState(await task);}
 async function copy(){if(!usable())return;pending.current=true;setCopying(true);current.current.onLock(true);
  try{await navigator.clipboard.writeText(exportAdminStatusRecovery(review!,window.location.origin));if(same())setMessage('Recovery text copied. It contains business data, not proof of execution. Store it securely.');}
  catch{if(same())setMessage('Clipboard unavailable. Reveal and copy the recovery text manually.');}
  finally{pending.current=false;setCopying(false);current.current.onLock(false);}}
 let exported='';try{if(revealed&&review?.confirmed&&typeof window!=='undefined')exported=exportAdminStatusRecovery(review,window.location.origin);}catch{/* Invalid export cannot break status preparation. */}
 const labels:Record<string,string>={kind:'Object kind',id:'Target UUID',audit_event_no:'Audit event number',expected_status:'Original expected status',applied_status:'Original applied status',revoked_browser_sessions:'Originally revoked browser sessions',principal_id:'Recipient principal UUID',role:'Role',scope_id:'Scope UUID'};
 return <Localized><section className="panel"><h3><Localized>{'Manual status audit recovery'}</Localized></h3>
  <p className="notice"><Localized>{'Status recovery contains internal identity or grant identifiers and the original reason. Store it securely on your device; do not share or upload it. It contains no session credentials and grants no permission.'}</Localized></p>
  <p><Localized>{'Import makes no request and cannot submit, retry or generate another audit number. Query requires the original administrator with current authorization; revoked access stays unknown. Another administrator cannot query this original event through this import. If access cannot be restored, use a separately approved recovery procedure without bypassing authorization.'}</Localized></p>
  {!controller.current&&review?.confirmed&&<><button type="button" disabled={copying} onClick={()=>{if(usable())setRevealed(true);}}><Localized>{'Reveal status recovery text'}</Localized></button><button type="button" disabled={copying} onClick={copy}><Localized>{'Copy status recovery text'}</Localized></button>{exported&&<textarea name="statusRecoveryExport" readOnly value={exported}/>}</>}
  {!controller.current&&!review&&<><label><Localized>{'Status recovery text'}</Localized><textarea name="statusRecoveryImport" value={text} maxLength={32768} disabled={copying} onChange={e=>{if(!same()||pending.current||controller.current||!current.current.guard('import'))return;source.current=e.target.value;setText(e.target.value);}}/></label><button type="button" disabled={copying||!text} onClick={stage}><Localized>{'Import status request for audit query only'}</Localized></button></>}
  {state&&<><h4><Localized>{'Imported original status request — unverified until matching audit'}</Localized></h4><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(state.command,null,2)}</pre>
   <p><Localized>{'Operation phase'}</Localized>: <Localized>{state.phase}</Localized></p><button type="button" disabled={!recoveryEnabled||state.phase==='checking'||state.phase==='confirmed'} onClick={query}><Localized>{'Query original status audit without resubmitting'}</Localized></button>
   {state.error&&<p><Localized>{'Result code'}</Localized>: <code>{state.error}</code></p>}
   {state.historicalreceipt&&<><p><Localized>{'This historical receipt confirms only the original status operation. It does not certify current status, current roles, active sessions, restored access or permission to act.'}</Localized></p><dl className="kv">{Object.entries(state.historicalreceipt).map(([k,v])=><div key={k}><dt><Localized>{labels[k]??k}</Localized></dt><dd>{['kind','expected_status','applied_status'].includes(k)?<Localized>{String(v)}</Localized>:String(v)}</dd></div>)}</dl></>}
  </>}
  {message&&<p role="status"><Localized>{message}</Localized></p>}
 </section></Localized>;
}
