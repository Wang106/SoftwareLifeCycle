import 'server-only';
import {privateUploadGate} from './browser-auth';
import {privateUploadSession} from './browser-session';
import {record,exactFields} from './first-command-transport';
import {MAX_UPLOAD_BYTES,uploadId,parseReserve,parseUploadContext,parseReservation,parseStatus,parseStored,uploadHash} from './private-upload-transport';
const headers={'Cache-Control':'private, no-store',Pragma:'no-cache',Vary:'Cookie','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'};
class Refusal extends Error {constructor(readonly status:number,readonly code:string){super(code);}}
function refuse(status:number,code:string):never {throw new Refusal(status,code);}
/** One monotonic budget spans authentication, ingress and all upstream response reads. */
export class UploadBudget {
 readonly end:number;readonly aborter=new AbortController();readonly pending=new Set<Promise<unknown>>();
 constructor(milliseconds=120000){this.end=performance.now()+milliseconds;}
 left(){return this.end-performance.now();}
 own<T>(operation:Promise<T>):Promise<T>{
  const p=Promise.resolve(operation);this.pending.add(p);void p.then(()=>this.pending.delete(p),()=>this.pending.delete(p));return p;
 }
 async drain():Promise<void>{while(this.pending.size)await Promise.allSettled([...this.pending]);}
 async wait<T>(operation:Promise<T>,maximum=this.left()):Promise<T>{
  const p=this.own(operation);
  const remaining=Math.min(maximum,this.left());if(remaining<=0||this.aborter.signal.aborted)refuse(408,'private_upload_timeout');
  const operationEnd=performance.now()+remaining;
  let timer:ReturnType<typeof setTimeout>|undefined;let abort:()=>void=()=>{};
  try {const value=await Promise.race([p,new Promise<never>((_,reject)=>{abort=()=>reject(new Refusal(408,'private_upload_timeout'));this.aborter.signal.addEventListener('abort',abort,{once:true});timer=setTimeout(abort,remaining);})]);if(performance.now()>=operationEnd||this.left()<=0||this.aborter.signal.aborted)refuse(408,'private_upload_timeout');return value;}
  finally{clearTimeout(timer);this.aborter.signal.removeEventListener('abort',abort);}
 }
}
export async function readUploadBytes(stream:ReadableStream<Uint8Array>|null,limit:number,budget:UploadBudget,idleMs=10000):Promise<Uint8Array>{
 if(!stream)refuse(400,'invalid_request');const reader=stream.getReader();const chunks:Uint8Array[]=[];let size=0,idleEnd=performance.now()+idleMs,finished=false;
 try {for(;;){const left=Math.min(idleEnd-performance.now(),budget.left());if(left<=0)refuse(408,'private_upload_timeout');const part=await budget.wait(reader.read(),left);if(performance.now()>=idleEnd)refuse(408,'private_upload_timeout');if(part.done){finished=true;break;}if(!(part.value instanceof Uint8Array)||part.value.length>limit-size)refuse(413,'request_too_large');if(part.value.length){chunks.push(part.value);size+=part.value.length;idleEnd=performance.now()+idleMs;}}
 const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}return bytes;
 }finally{if(!finished)void budget.own(reader.cancel()).catch(()=>{});reader.releaseLock();}
}
async function jsonResponse(response:Response,budget:UploadBudget):Promise<unknown>{
 if(response.status>=300&&response.status<400||response.headers.get('content-type')?.split(';')[0].trim().toLowerCase()!=='application/json'||Number(response.headers.get('content-length')||0)>32768){if(response.body)void budget.own(response.body.cancel()).catch(()=>{});refuse(502,'outcome_unknown');}
 return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await readUploadBytes(response.body,32768,budget)));
}
let active=0; // Isolate/process-local only, not a fleet-wide storage quota.
const activeRequests=new Set<string>();
export async function handlePrivateUpload(request:Request,env:Record<string,string|undefined>,mode:'context'|'reserve'|'content'|'receipt',fetcher:typeof fetch=fetch):Promise<Response>{
 const reply=(value:unknown,status=200)=>Response.json(value,{status,headers});
 const budget=new UploadBudget();let admitted=false,key:string|undefined,writeStarted=false;
 const abort=()=>budget.aborter.abort();request.signal.addEventListener('abort',abort,{once:true});
 try {
  if(!['context','reserve','content','receipt'].includes(mode))refuse(400,'invalid_request');
  if(request.method!==(mode==='content'?'PUT':'POST'))return new Response(null,{status:405,headers:{...headers,Allow:mode==='content'?'PUT':'POST'}});
  const gate=await budget.wait(privateUploadGate(request,env));if('error'in gate)return reply({error:gate.error},gate.status);
  if(request.signal.aborted)refuse(408,'private_upload_timeout');
  const media=mode==='content'?'application/octet-stream':'application/json';
  if(request.headers.get('content-type')!==media||['content-encoding','content-range','transfer-encoding'].some(k=>request.headers.has(k)))refuse(415,'invalid_upload_headers');
  const declared=request.headers.get('content-length');if(declared!==null&&(!/^(0|[1-9][0-9]{0,9})$/.test(declared)||Number(declared)>(mode==='content'?MAX_UPLOAD_BYTES:32768)))refuse(413,'request_too_large');
  const url=new URL(request.url);let requestId:string|undefined;
  if(mode==='content'){const pairs=[...url.searchParams];if(pairs.length!==1||pairs[0][0]!=='request_id'||!uploadId(pairs[0][1]))refuse(400,'invalid_request');requestId=pairs[0][1];}
  else if(url.search)refuse(400,'invalid_request');
  if(active>=2)refuse(429,'private_upload_busy');active++;admitted=true;
  // Override only this feature's complete request chain, including resolveSession's /me read.
  const fixedFetch:typeof fetch=async(input,init)=>{
   if(budget.left()<=0||budget.aborter.signal.aborted)refuse(408,'private_upload_timeout');
   const target=String(input);if(!target.startsWith(gate.config.apiBase+'/api/v1/'))refuse(502,'outcome_unknown');
   const controller=new AbortController();const cancel=()=>controller.abort();budget.aborter.signal.addEventListener('abort',cancel,{once:true});
   const auth=target===gate.config.apiBase+'/api/v1/security/me';
   try {return await budget.wait((async()=>{
    const response=await budget.wait(fetcher(input,{...init,redirect:'manual',cache:'no-store',signal:controller.signal}));
    // The five-second identity limit includes its response body, not just headers.
    const value=await jsonResponse(response,budget);return Response.json(value,{status:response.status});
   })(),auth?Math.min(5000,budget.left()):budget.left());
   }catch(e){controller.abort();throw e;}finally{budget.aborter.signal.removeEventListener('abort',cancel);}
  };
  const session=await budget.wait(privateUploadSession(gate.config,gate.cookie,fixedFetch));if(!session)refuse(401,'session_required');
  if((mode==='reserve'||mode==='content')&&session.identity.read_only_mode)refuse(403,'read_only_mode');
  const actor=session.identity.principal.id;
  const call=async(path:string,method:'GET'|'POST'|'PUT'='GET',body?:string|Uint8Array)=>{
   const r=await budget.wait(session.request(path,method,body));const v=await jsonResponse(r,budget);
   if(![200,201].includes(r.status)){const known:Record<number,string>={401:'session_required',403:'submission_forbidden',404:'target_not_found',409:'request_conflict',422:'invalid_request',429:'private_upload_busy'};refuse(known[r.status]?r.status:502,known[r.status]||'outcome_unknown');}return {status:r.status,value:v};
  };
  const base='/api/v1/private-uploads/';
  const status=async(id:string)=>{const r=await call(base+'receipts/'+id);const s=r.status===200?parseStatus(r.value,id,actor):null;if(!s)refuse(502,'outcome_unknown');return s;};
  const context=async(id:string)=>{const r=await call(base+'context?component_id='+id);const c=r.status===200?await budget.wait(parseUploadContext(r.value,id)):null;if(!c)refuse(502,'outcome_unknown');return c;};
  if(mode==='content'){
   const original=await status(requestId!);if(original.state!=='RESERVED')refuse(409,'private_upload_attempt_consumed');const r=original.reservation;
   const c=await context(r.component_id);if(c.context.storage_scope_id!==r.storage_scope_id||r.expected_bytes>Math.min(MAX_UPLOAD_BYTES,c.context.admission_max_bytes))refuse(409,'context_conflict');
   if(declared!==null&&Number(declared)!==r.expected_bytes)refuse(422,'invalid_request');
   key=actor+':'+r.request_id;if(activeRequests.has(key)){key=undefined;refuse(409,'private_upload_busy');}activeRequests.add(key);
   const data=await readUploadBytes(request.body,r.expected_bytes,budget);if(data.length!==r.expected_bytes||await budget.wait(uploadHash(data))!==r.sha256)refuse(422,'invalid_request');
   // Authority can be revoked during ingress; recheck before sending a single PUT. Backend rechecks again.
   const renewed=await budget.wait(privateUploadSession(gate.config,gate.cookie,fixedFetch));if(!renewed||renewed.identity.principal.id!==actor)refuse(401,'session_required');if(renewed.identity.read_only_mode)refuse(403,'read_only_mode');
   writeStarted=true;const result=await call(base+r.request_id+'/content','PUT',data);if(result.status!==200||!parseStored(result.value,r))refuse(502,'outcome_unknown');
   const final=await status(r.request_id);if(final.state!=='STORED_PRIVATE'||!parseStored(final.stored_receipt,r))refuse(502,'outcome_unknown');return reply(final);
  }
  const raw=await readUploadBytes(request.body,32768,budget);if(declared!==null&&raw.length!==Number(declared))refuse(400,'invalid_request');
  let value:unknown;try{const text=new TextDecoder('utf-8',{fatal:true}).decode(raw);value=JSON.parse(text);const tokens=text.match(/"(?:\\.|[^"\\])*"|[{}:,\[\]]|[^\s{}:,\[\]"]+/g)||[];const keys=tokens.filter((_,i)=>tokens[i+1]===':').map(k=>JSON.parse(k));if(new Set(keys).size!==keys.length)refuse(400,'invalid_request');}catch{refuse(400,'invalid_request');}
  if(mode==='reserve'){
   const command=parseReserve(value);if(!command)refuse(400,'invalid_request');const c=await context(command.component_id);
   if(c.context_digest!==command.expected_context_digest||command.expected_bytes>Math.min(MAX_UPLOAD_BYTES,c.context.admission_max_bytes))refuse(409,'context_conflict');
   writeStarted=true;const result=await call(base+'reservations','POST',JSON.stringify(command));const r=parseReservation(result.value,command.request_id,actor);
   if(!r||r.component_id!==command.component_id||r.expected_bytes!==command.expected_bytes||r.sha256!==command.sha256||r.storage_scope_id!==c.context.storage_scope_id)refuse(502,'outcome_unknown');return reply(r,result.status);
  }
  const d=record(value),field=mode==='context'?'component_id':'request_id';if(!d||!exactFields(d,[field])||!uploadId(d[field]))refuse(400,'invalid_request');
  return reply(mode==='context'?await context(d[field] as string):await status(d[field] as string));
 }catch(e){if(writeStarted)return reply({error:'outcome_unknown'},502);return reply({error:e instanceof Refusal?e.code:'outcome_unknown'},e instanceof Refusal?e.status:502);}
 finally{
  request.signal.removeEventListener('abort',abort);budget.aborter.abort();
  // Aborting a fetch is not evidence it stopped. Keep admission until owned asynchronous work settles.
  const release=()=>{if(admitted)active--;if(key)activeRequests.delete(key);};
  if(budget.pending.size)void budget.drain().then(release);else release();
 }
}
