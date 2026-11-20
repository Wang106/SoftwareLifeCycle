'use strict';
// Test-only HTTP API double. Never imports production storage or accepts a root/path.
const fs=require('node:fs/promises'),C=require('node:fs').constants,os=require('node:os'),path=require('node:path'),http=require('node:http'),{createHash}=require('node:crypto');
const id=n=>`${n}2345678-1234-4234-8234-123456789abc`,component=id(5),principal=id(8),sid=id(7),uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const bytes=Buffer.from(Array.from({length:65539},(_,i)=>i%256)),hash=b=>createHash('sha256').update(b).digest('hex'),sha256=hash(bytes);
function context(limit){const c={release_id:id(1),component_definition_id:id(2),base_component_id:id(3),project_id:id(1),standard_base_release_id:id(2),project_code:'P',project_name:'Synthetic',customer_id:id(3),customer_code:'C',customer_name:'Synthetic',software_id:id(4),software_code:'S',software_name:'Synthetic',standard_base_version:'1',standard_base_status:'DRAFT',release_version:'1',release_status:'DRAFT',component_code:'APP',component_name:'Application',base_component_version:'0',component_id:component,component_version:'1',delta_type:'MODIFIED',storage_scope_id:id(6),admission_max_bytes:limit};return {version:1,context:c,context_digest:hash(JSON.stringify({context:Object.fromEntries(Object.entries(c).sort(([a],[b])=>a<b?-1:1)),version:1}))}}
async function readBody(req,cap){const chunks=[];let size=0;const timer=setTimeout(()=>req.destroy(),3000);try{for await(const b of req){size+=b.length;if(size>cap)throw Error('limit');chunks.push(b)}return Buffer.concat(chunks)}finally{clearTimeout(timer)}}
async function startStorage({limit=1048576,loseResponse=false}={}){
 if(!Number.isSafeInteger(limit)||limit<0||limit>8388608||typeof loseResponse!=='boolean')throw Error('invalid fixture');
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'slc-upload-storage-'));let rootStat;try{rootStat=await fs.lstat(directory)}catch(e){await fs.rmdir(directory);throw e}async function removeOwned(){const current=await fs.lstat(directory);if(current.ino!==rootStat.ino||current.dev!==rootStat.dev||!current.isDirectory()||current.isSymbolicLink())throw Error('owned directory changed');await fs.rm(directory,{recursive:true});try{await fs.lstat(directory);throw Error('cleanup incomplete')}catch(e){if(e.code!=='ENOENT')throw e}}
 try{await fs.chmod(directory,0o700)}catch(e){await removeOwned();throw e}const filename=path.join(directory,'payload.bin'),ctx=context(limit);
 let reservation=null,stored=null,origin,closed=false,active=false;const counts={reserve:0,put:0,writes:0,receipts:0},pending=new Set(),violations=[],queries={identity:0,context:0};
 const status=()=>({version:1,state:stored?'STORED_PRIVATE':'RESERVED',revision:stored?4:0,reservation,stored_receipt:stored});
 async function handle(req,res){const reply=(s,v)=>{res.writeHead(s,{'Content-Type':'application/json','Cache-Control':'private, no-store'});res.end(JSON.stringify(v))};
  if(req.headers.host!==new URL(origin).host||req.headers.authorization!=='Bearer synthetic-token'||req.headers['x-browser-session']!==sid)return reply(403,{error:'forbidden'});
  const url=req.url;
  if(req.method==='GET'&&url==='/api/v1/security/me'){queries.identity++;return reply(200,{principal:{id:principal,principal_type:'USER',display_name:'Synthetic'},browser_session_id:sid,read_only_mode:false,active_grant_counts:{GLOBAL:0,PROJECT:1,SOFTWARE:1}});}
  if(req.method==='GET'&&url==='/api/v1/private-uploads/context?component_id='+component){queries.context++;return reply(200,ctx);}
  if(req.method==='POST'&&url==='/api/v1/private-uploads/reservations'){
   counts.reserve++;if(reservation||active)return reply(409,{error:'consumed'});active=true;
   try{const d=JSON.parse((await readBody(req,32768)).toString());if(Object.keys(d).sort().join(',')!=='component_id,expected_bytes,expected_context_digest,reason,request_id,sha256'||!uuid.test(d.request_id)||d.component_id!==component||d.expected_bytes!==bytes.length||d.expected_bytes>limit||d.sha256!==sha256||d.expected_context_digest!==ctx.context_digest||d.reason!=='Synthetic only')return reply(422,{error:'invalid'});
    reservation={version:1,request_id:d.request_id,component_id:component,object_id:id(4),storage_scope_id:id(6),expected_bytes:bytes.length,sha256,actor_principal_id:principal,state:'RESERVED',created_at:'2026-11-20T00:00:00Z'};return reply(201,reservation);
   }finally{active=false}
  }
  if(req.method==='GET'&&url.startsWith('/api/v1/private-uploads/receipts/')){counts.receipts++;return reservation&&url==='/api/v1/private-uploads/receipts/'+reservation.request_id?reply(200,status()):reply(404,{error:'missing'})}
  if(req.method==='PUT'&&reservation&&url==='/api/v1/private-uploads/'+reservation.request_id+'/content'){
   counts.put++;if(stored||active)return reply(409,{error:'consumed'});active=true;
   try{if(req.headers['content-type']!=='application/octet-stream')return reply(415,{error:'type'});const data=await readBody(req,bytes.length);if(data.length!==bytes.length||hash(data)!==sha256)return reply(422,{error:'bytes'});
    const file=await fs.open(filename,C.O_WRONLY|C.O_CREAT|C.O_EXCL|C.O_NOFOLLOW,0o600);try{await file.writeFile(data);await file.sync()}finally{await file.close()}
    counts.writes++;stored={...reservation,state:'STORED_PRIVATE',revision:4,stored_at:'2026-11-20T00:01:00Z'};
    if(loseResponse){req.socket.destroy();return}return reply(200,stored);
   }finally{active=false}
  }
  violations.push('unexpected-route');reply(404,{error:'missing'});
 }
 const server=http.createServer((req,res)=>{const p=handle(req,res).catch(()=>{if(!res.destroyed){res.writeHead(400,{'Content-Type':'application/json'});res.end('{"error":"fixture_refused"}')}});pending.add(p);void p.finally(()=>pending.delete(p))});server.on('upgrade',(_,socket)=>{violations.push('upgrade');socket.destroy()});server.requestTimeout=5000;server.headersTimeout=5000;
 try{await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)});origin='http://127.0.0.1:'+server.address().port}catch(e){await removeOwned();throw e}
 return {origin,context:ctx,bytes:Buffer.from(bytes),sha256,component,violations,counts:()=>({...counts}),queries:()=>({...queries}),async inspect(){
  if(!stored)return null;if(active)throw Error('write pending');const file=await fs.open(filename,C.O_RDONLY|C.O_NOFOLLOW);try{const before=await file.stat();if(!before.isFile()||before.nlink!==1||before.size!==65539)throw Error('invalid disk file');const data=await file.readFile();const after=await file.stat();if(before.ino!==after.ino||before.size!==after.size||data.length!==65539||hash(data)!==sha256)throw Error('disk mismatch');return {request_id:reservation.request_id,component_id:component,bytes:data.length,sha256:hash(data),closed_before_read:true}}finally{await file.close()}},async close(){if(closed)throw Error('already closed');closed=true;await new Promise((resolve,reject)=>{server.close(e=>e?reject(e):resolve());server.closeAllConnections()});await Promise.all([...pending]);if(active)throw Error('storage still active');await removeOwned();return {cleaned:true,listener_closed:!server.listening,pending:pending.size}}};
}
module.exports={startStorage,component,principal,sid,bytes,sha256};
