'use strict';
// Loopback-only synthetic HTTP backend and real Next production runner. No provider/database.
const http=require('node:http');
const {once}=require('node:events');
const {spawn}=require('node:child_process');
const {existsSync,readFileSync}=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const values=Object.freeze({batchNo:'PB-BROWSER-FIXTURE',deploymentNo:'DEP-BROWSER-FIXTURE',baselineNote:'BROWSER_BASELINE_NOTE 原始',effectiveNote:'BROWSER_EFFECTIVE_NOTE 更正',baselineVersion:'BROWSER-v1',effectiveVersion:'BROWSER-v1',correctionReason:'BROWSER_SYNTHETIC_CORRECTION'});
const paths=Object.freeze({batchPage:'/production/batches/'+values.batchNo,historyPage:'/deployments/'+values.deploymentNo+'/batches/'+values.batchNo+'/history',batchApi:'/api/v1/batches/'+values.batchNo,historyApi:'/api/v1/deployments/'+values.deploymentNo+'/batches/'+values.batchNo+'/history'});
const ids=Object.freeze({batch:'11111111-1111-4111-8111-111111111111',release1:'22222222-2222-4222-8222-222222222222',release2:'33333333-3333-4333-8333-333333333333',snapshot1:'44444444-4444-4444-8444-444444444444',snapshot2:'55555555-5555-4555-8555-555555555555',correction:'66666666-6666-4666-8666-666666666666'});
function historyFixture(){
 const baseline={release_id:ids.release1,version:values.baselineVersion,snapshot_id:ids.snapshot1,snapshot_no:'BROWSER-SNP-1',changeover_id:null,changeover_no:null,started_at:'2026-01-01T00:00:00Z',ended_at:null,note:values.baselineNote};
 const effective={...baseline,started_at:'2026-01-01T01:00:00Z',note:values.effectiveNote};
 return{kind:'batch',record_no:values.batchNo,deployment_no:values.deploymentNo,stored_status:'ACTIVE',history_state:'ORIGINAL_CORRECTED',recorded_baseline:{source:'ORIGINAL',recorded_at:'2026-01-01T00:00:00Z',baseline_event_no:'EVT-BROWSER-BASELINE',values:baseline},effective:{revision:1,head_id:ids.correction,values:effective},correction_count:1,limit:50,truncated:false,corrections:[{id:ids.correction,revision:1,predecessor_id:null,correction_reason:values.correctionReason,recorded_at:'2026-01-02T00:00:00Z',audit_event_no:'EVT-BROWSER-CORRECTION',values:effective}]};
}
function batchFixture(){return{id:ids.batch,batch_no:values.batchNo,status:'ACTIVE',started_at:'2026-01-01T01:00:00Z',ended_at:null,note:values.effectiveNote,software:{release_id:ids.release1,version:values.effectiveVersion,snapshot_id:ids.snapshot1,snapshot_no:'BROWSER-SNP-1'},deployment:{deployment_no:values.deploymentNo,status:'MATCH',actual:{release_id:ids.release1,version:values.effectiveVersion,snapshot_id:ids.snapshot1,snapshot_no:'BROWSER-SNP-1'}},authorization:{authorization_no:'AUTH-BROWSER-FIXTURE',status:'APPROVED',batch_limit:1},changeover:null,matches:{authorized_release:true,authorized_snapshot:true,deployed_release:true,deployed_snapshot:true,changeover_deployment:null}};}
async function listen(server){server.listen(0,'127.0.0.1');await once(server,'listening');return server.address().port;}
async function closeServer(server){if(!server.listening)return;await new Promise((resolve,reject)=>{server.close(error=>error?reject(error):resolve());server.closeAllConnections();});}
async function startFixtureServer(){
 const requests=[],violations=[];let mode='ready';
 const server=http.createServer((req,res)=>{
  const entry={method:req.method,url:req.url,mode};requests.push(entry);
  // Exact route/method allowlist; no general API, credentials, mutation or control route.
  if(req.method!=='GET'||![paths.batchApi,paths.historyApi].includes(req.url)||req.headers.authorization||req.headers.cookie){violations.push(entry);res.writeHead(400,{'content-type':'application/json'});res.end(JSON.stringify({error:'synthetic_fixture_rejected'}));return;}
  if(req.url===paths.historyApi&&mode==='unavailable'){res.writeHead(503,{'content-type':'application/json'});res.end(JSON.stringify({detail:'BROWSER_PRIVATE_UPSTREAM_ERROR'}));return;}
  res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(req.url===paths.batchApi?batchFixture():historyFixture()));
 });
 const port=await listen(server);
 return{apiOrigin:`http://127.0.0.1:${port}`,requests,violations,setMode(next){if(!['ready','unavailable'].includes(next))throw Error('invalid_fixture_mode');mode=next;},close:()=>closeServer(server)};
}
function appEnvironment(apiOrigin){
 const u=new URL(apiOrigin);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'||u.origin!==apiOrigin)throw Error('fixture_must_be_loopback');
 const env={PATH:process.env.PATH||'',NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',API_BASE_URL:apiOrigin,NEXT_PUBLIC_API_BASE_URL:'',NEXT_PUBLIC_API_URL:'',BROWSER_OIDC_MODE:'disabled',BROWSER_SESSION_MODE:'disabled'};
 // Discover mode keys from checked-in frontend source, never inherit operator configuration.
 // All are forced disabled, including future independently gated preparation/read modes.
 const gateSource=readFileSync(path.join(root,'lib/browser-auth.ts'),'utf8')+readFileSync(path.join(root,'lib/browser-session.ts'),'utf8');
 for(const match of gateSource.matchAll(/\b[A-Z][A-Z0-9_]*_MODE\b/g))env[match[0]]='disabled';
 return env;
}
async function startApp(createFixture = startFixtureServer){
 if(!existsSync(path.join(root,'.next/BUILD_ID')))throw Error('Build the actual Next production app before browser acceptance.');
 const fixture=await createFixture();let child,logs='';
 const stop=async()=>{try{if(child&&child.pid&&child.exitCode===null){const exit=once(child,'exit');child.kill('SIGTERM');const timer=setTimeout(()=>child.kill('SIGKILL'),5000);try{await exit;}finally{clearTimeout(timer);}}}finally{await fixture.close();}};
 try{
  const reservation=http.createServer();const port=await listen(reservation);await closeServer(reservation);
  const appOrigin=`http://127.0.0.1:${port}`;
  child=spawn(process.execPath,[require.resolve('next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(port)],{cwd:root,env:appEnvironment(fixture.apiOrigin),stdio:['ignore','pipe','pipe']});
  child.on('error',error=>{logs=(logs+'\n'+error.message).slice(-16000);});
  for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{logs=(logs+chunk.toString()).slice(-16000);});
  let ready=false;for(let n=0;n<100;n++){if(child.exitCode!==null)throw Error('Next exited before readiness: '+logs);try{const r=await fetch(appOrigin+'/auth/session',{signal:AbortSignal.timeout(1000),redirect:'error'});await r.arrayBuffer();if(r.status===503){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}
  if(!ready)throw Error('Next production readiness failed: '+logs);
  return{appOrigin,fixture,stop,logs:()=>logs};
 }catch(error){await stop();throw error;}
}
module.exports={paths,values,ids,historyFixture,batchFixture,appEnvironment,startFixtureServer,startApp};
