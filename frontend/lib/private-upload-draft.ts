import {MAX_UPLOAD_BYTES,uploadId,uploadHash,parseUploadContext,parseReserve,parseReservation,parseStatus,type Reserve,type Reservation,type Status} from './private-upload-transport';
import {record} from './first-command-transport';
import {readCreationResponse} from './application-component-declaration';
export interface UploadJournal {read():string|null;claim(id:string):Promise<boolean>}
export type UploadFile=Pick<File,'size'|'name'|'arrayBuffer'>;
export type UploadState=Readonly<{phase:'idle'|'preparing'|'review'|'invalid'|'blocked'|'sending'|'unknown'|'checking'|'stored';confirmed:boolean;requestId:string|null;bytes?:number;sha256?:string;receipt?:Status}>;
/** One controller owns one attempt. No method resets a consumed attempt. */
export class UploadDraft {
 revision=0;state:UploadState={phase:'idle',confirmed:false,requestId:null};
 private command:Reserve|null=null;private bytes:Uint8Array|null=null;private reservation:Reservation|null=null;
 private consumed=false;private busy=false;private aborter:AbortController|null=null;
 constructor(readonly component:string,readonly enabled:boolean,private journal:UploadJournal,private fetcher:typeof fetch=fetch,private changed:()=>void=()=>{}){this.fetcher=fetcher.bind(globalThis);if(enabled)this.sync();}
 private update(value:UploadState){this.state=Object.freeze(value);this.changed();}
 sync(){if(this.consumed)return;try{const id=this.journal.read();if(id){if(!uploadId(id))throw Error();this.consumed=true;this.revision++;this.bytes=null;this.command=null;this.update({phase:'unknown',confirmed:false,requestId:id});}}catch{this.consumed=true;this.update({phase:'blocked',confirmed:false,requestId:null});}}
 get locked(){return this.consumed;}
 clear(){this.revision++;this.aborter?.abort();this.bytes=null;this.command=null;if(this.consumed){this.update({...this.state,phase:'unknown',confirmed:false});return;}this.update({phase:'idle',confirmed:false,requestId:null});}
 confirm(revision:number,value:boolean){this.sync();if(!this.consumed&&revision===this.revision&&this.state.phase==='review')this.update({...this.state,confirmed:value});}
 private async call(mode:string,body:unknown,signal:AbortSignal){const response=await this.fetcher('/auth/private-upload-'+mode,{method:'POST',body:JSON.stringify(body),headers:{'Content-Type':'application/json',Accept:'application/json'},credentials:'same-origin',cache:'no-store',redirect:'error',signal});const value=await readCreationResponse(response);if(![200,201].includes(response.status))throw Error();return value;}
 async prepare(file:UploadFile,reason:string){
  if(!this.enabled||!uploadId(this.component))return;this.sync();if(this.consumed)return;
  this.clear();const revision=this.revision,aborter=new AbortController();this.aborter=aborter;const timer=setTimeout(()=>aborter.abort(),15000);
  this.update({phase:'preparing',confirmed:false,requestId:null});
  const current=()=>revision===this.revision&&!this.consumed&&!aborter.signal.aborted;
  try{
   const context=await parseUploadContext(await this.call('context',{component_id:this.component},aborter.signal),this.component);if(!current())return;
   if(!context||!Number.isSafeInteger(file.size)||file.size<0||file.size>Math.min(MAX_UPLOAD_BYTES,context.context.admission_max_bytes))throw Error();
   // Admission precedes arrayBuffer and hashing. File bytes never enter persistent storage.
   const bytes=new Uint8Array(await file.arrayBuffer());if(!current())return;if(bytes.length!==file.size)throw Error();
   const sha256=await uploadHash(bytes);if(!current())return;
   const command=parseReserve({request_id:crypto.randomUUID(),component_id:this.component,expected_bytes:bytes.length,sha256,expected_context_digest:context.context_digest,reason:reason.trim()});if(!command)throw Error();
   this.bytes=bytes;this.command=command;this.update({phase:'review',confirmed:false,requestId:null,bytes:bytes.length,sha256});
  }catch{if(revision===this.revision&&!this.consumed)this.update({phase:'invalid',confirmed:false,requestId:null});}
  finally{clearTimeout(timer);if(this.aborter===aborter)this.aborter=null;if(aborter.signal.aborted&&revision===this.revision&&!this.consumed)this.update({phase:'invalid',confirmed:false,requestId:null});}
 }
 async send(revision:number){
  if(!this.enabled||this.busy)return;this.sync();if(this.consumed||revision!==this.revision||!this.state.confirmed||!this.command||!this.bytes)return;
  this.busy=true;this.consumed=true;const command=this.command,bytes=this.bytes;this.bytes=null;this.command=null;
  const aborter=new AbortController();this.aborter=aborter;const timer=setTimeout(()=>aborter.abort(),120000);
  this.update({...this.state,phase:'sending',confirmed:false,requestId:command.request_id});
  try{
   // Persist before any write. Web Lock makes claim atomic across participating tabs.
   if(!await this.journal.claim(command.request_id)){const id=this.journal.read();this.update({phase:id?'unknown':'blocked',confirmed:false,requestId:id});return;}
   if(aborter.signal.aborted)throw Error();
   const value=await this.call('reserve',command,aborter.signal);if(aborter.signal.aborted)throw Error();
   const actor=record(value)?.actor_principal_id;const reservation=typeof actor==='string'?parseReservation(value,command.request_id,actor):null;
   if(!reservation||reservation.component_id!==this.component||reservation.expected_bytes!==command.expected_bytes||reservation.sha256!==command.sha256)throw Error();this.reservation=reservation;
   const response=await this.fetcher('/auth/private-upload-content?request_id='+command.request_id,{method:'PUT',body:bytes as BodyInit,headers:{'Content-Type':'application/octet-stream',Accept:'application/json'},credentials:'same-origin',cache:'no-store',redirect:'error',signal:aborter.signal});
   const status=await readCreationResponse(response);if(response.status!==200||aborter.signal.aborted)throw Error();this.accept(status,command.request_id);
  }catch{this.update({...this.state,phase:'unknown',confirmed:false});}
  finally{clearTimeout(timer);this.busy=false;if(this.aborter===aborter)this.aborter=null;}
 }
 private accept(value:unknown,id:string){const actor=record(record(value)?.reservation)?.actor_principal_id;const status=typeof actor==='string'?parseStatus(value,id,actor):null;if(!status||this.reservation&&Object.keys(this.reservation).some(k=>status.reservation[k as keyof Reservation]!==this.reservation![k as keyof Reservation]))throw Error();this.update({phase:status.state==='STORED_PRIVATE'?'stored':'unknown',confirmed:false,requestId:id,receipt:status});}
 async recover(){if(!this.enabled||this.busy)return;this.sync();const id=this.state.requestId;if(!this.consumed||!id)return;this.busy=true;this.update({...this.state,phase:'checking',confirmed:false});try{this.accept(await this.call('receipt',{request_id:id},AbortSignal.timeout(15000)),id);}catch{this.update({...this.state,phase:'unknown',confirmed:false});}finally{this.busy=false;}}
}
