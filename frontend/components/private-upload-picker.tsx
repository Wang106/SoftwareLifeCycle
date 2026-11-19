'use client';
import {useEffect,useRef,useState} from 'react';
import {Localized} from './localized';
import {UploadDraft} from '../lib/private-upload-draft';
import {browserUploadJournal} from '../lib/private-upload-journal';
export default function PrivateUploadPicker({componentId='',enabled=false}:{componentId?:string;enabled?:boolean}){
 const controller=useRef<UploadDraft|null>(null),fileInput=useRef<HTMLInputElement>(null);
 const [,render]=useState(0),[reason,setReason]=useState('');
 useEffect(()=>{
  let live=true;let journal;try{journal=browserUploadJournal(window.localStorage,navigator.locks);}catch{journal={read:()=>{throw Error();},claim:async()=>false};}
  const draft=new UploadDraft(componentId,enabled,journal,fetch,()=>{if(live)render(n=>n+1);});controller.current=draft;render(n=>n+1);
  const sync=()=>draft.sync();window.addEventListener('storage',sync);
  return()=>{live=false;window.removeEventListener('storage',sync);draft.clear();if(controller.current===draft)controller.current=null;};
 },[componentId,enabled]);
 const draft=controller.current,state=draft?.state,revision=draft?.revision;
 const current=()=>!!draft&&controller.current===draft&&draft.component===componentId&&draft.revision===revision;
 const locked=!enabled||!draft||draft.locked, busy=state?.phase==='sending'||state?.phase==='checking';
 const clear=()=>{if(!current())return;draft!.clear();if(fileInput.current)fileInput.current.value='';};
 return <Localized><section aria-label="Private single-file upload"><h2><Localized>{'Private single-file upload'}</Localized></h2>
 <p><Localized>{'Private storage is not scanning, distribution approval or release readiness.'}</Localized></p>
 {!enabled&&<p role="status"><Localized>{'Private upload is disabled. No file is read or sent.'}</Localized></p>}
 {componentId&&<p><Localized>{'Declared component UUID'}</Localized>: <code>{componentId}</code></p>}
 {enabled&&componentId&&<fieldset disabled={locked||!componentId}><legend><Localized>{'Select one file for this declared component'}</Localized></legend>
 <label htmlFor="upload-reason"><Localized>{'Reason (maximum 4000 characters)'}</Localized></label><textarea id="upload-reason" maxLength={4000} value={reason} onChange={e=>{if(!current()||draft!.locked)return;clear();setReason(e.target.value);}}/>
 <label htmlFor="upload-file"><Localized>{'Single private file'}</Localized></label><input ref={fileInput} id="upload-file" type="file" onChange={e=>{if(!current()||draft!.locked)return;const files=e.target.files;if(files?.length===1)void draft!.prepare(files[0],reason);else clear();}}/>
 <button type="button" onClick={clear}><Localized>{'Clear selected file and confirmation'}</Localized></button></fieldset>}
 {state?.phase==='review'&&<section><h3><Localized>{'Review exact private upload'}</Localized></h3><p><Localized>{'Bytes'}</Localized>: {state.bytes}</p><p>SHA-256: <code>{state.sha256}</code></p><p><Localized>{'Reason'}</Localized>: {reason}</p>
 <label><input type="checkbox" checked={state.confirmed} onChange={e=>{if(current())draft!.confirm(revision!,e.target.checked);}}/><Localized>{'I confirm this exact component, file digest, byte count and reason.'}</Localized></label>
 <button type="button" disabled={!state.confirmed||locked} onClick={()=>{if(current())void draft!.send(revision!);}}><Localized>{'Reserve and send once'}</Localized></button></section>}
 <p role="status" aria-live="polite"><Localized>{state?.phase==='preparing'?'Checking admission before reading this file.':state?.phase==='invalid'?'File or context rejected. No reservation was sent.':state?.phase==='blocked'?'Recovery storage unavailable. Upload remains blocked.':state?.phase==='sending'?'Sending once. Network completion is not storage confirmation.':state?.phase==='checking'?'Checking the original private receipt.':state?.phase==='stored'?'Original receipt confirms STORED_PRIVATE only.':state?.phase==='unknown'?'Outcome unknown. Only the original receipt may be checked; do not resend.':''}</Localized></p>
 {(state?.phase==='preparing'||state?.phase==='sending')&&<button type="button" onClick={clear}><Localized>{'Cancel and keep original receipt recovery'}</Localized></button>}
 {state?.receipt&&<section><p><Localized>{'Original receipt component UUID'}</Localized>: <code>{state.receipt.reservation.component_id}</code></p>{componentId&&state.receipt.reservation.component_id!==componentId&&<p role="alert"><Localized>{'This original receipt belongs to a different component. It does not confirm an upload to the current declaration.'}</Localized></p>}<p><Localized>{'Bytes'}</Localized>: {state.receipt.reservation.expected_bytes}</p><p>SHA-256: <code>{state.receipt.reservation.sha256}</code></p></section>}
 {state?.requestId&&<><p><Localized>{'Original upload request UUID'}</Localized>: <code>{state.requestId}</code></p><button type="button" disabled={!enabled||busy} onClick={()=>{if(current())void draft!.recover();}}><Localized>{'Check original private upload receipt'}</Localized></button></>}
 <p><Localized>{'Only a random request ID is retained across refresh. File bytes and identity are not saved. Clearing browser storage or using another browser can bypass this local guard; server permissions still apply.'}</Localized></p>
 </section></Localized>;
}
