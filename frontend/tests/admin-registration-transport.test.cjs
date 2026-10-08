'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-register-transport-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/admin-registration-transport.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {RegistrationSubmission,registrationInput,projectRegistrationReceipt}=require(path.join(output,'admin-registration-transport.js'));
const {prepareRegistration,confirmRegistration}=require(path.join(output,'admin-registration-draft.js'));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id='34567890-1234-1234-1234-123456789abc',principalId='12345678-1234-1234-1234-123456789abc',
 scopeId='45678901-1234-1234-1234-123456789abc';
function input(kind='PRINCIPAL'){return {kind,newId:id,eventNo:'ADM-ORIGINAL',reason:'Approved registration',
 ...(kind==='PRINCIPAL'?{principalType:'SERVICE',subject:'Exact:Subject/😀',displayName:'Service'}:
 {principalId,role:kind==='GLOBAL'?'AUDITOR':kind==='PROJECT'?'PROJECT_VIEWER':'SOFTWARE_VIEWER',...(kind==='GLOBAL'?{}:{scopeId})})};}
const review=kind=>confirmRegistration(prepareRegistration(input(kind)),true);
function receipt(r,extras={}) {return {kind:r.kind,id,audit_event_no:'ADM-ORIGINAL',applied_status:r.initialStatus,
 current_status:r.initialStatus,replayed:false,...(r.kind==='PRINCIPAL'?{revoked_browser_sessions:0}:
 {principal_id:principalId,role:r.request.body.role,...(r.kind==='GLOBAL'?{}:{scope_id:scopeId})}),...extras};}
test('registration controller requires confirmed unaltered review and frozen input',()=>{
 const r=review();assert.throws(()=>new RegistrationSubmission({...r,confirmed:false}),/Confirm/);
 for(const change of [{request:{...r.request,path:'/evil'}},{initialStatus:'ACTIVE'},
  {request:{...r.request,body:{...r.request.body,issuer:'evil'}}}])assert.throws(()=>new RegistrationSubmission({...r,...change}),/invalid_review/);
 const c=new RegistrationSubmission(r);assert.ok(Object.isFrozen(c.state.review.request.body));
 assert.throws(()=>{c.state.review.request.body.subject='changed';},TypeError);
});
test('registration disabled transport makes no network call',async()=>{
 let calls=0;const c=new RegistrationSubmission(review()),s=await c.send(false,async()=>{calls++;});
 assert.equal(s.phase,'rejected');assert.equal(s.error,'registration_submission_disabled');assert.equal(calls,0);
});
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test('registration browser envelope and exact receipt '+kind,async()=>{
 const r=review(kind),c=new RegistrationSubmission(r);
 assert.deepEqual(registrationInput(r),input(kind));
 const s=await c.send(true,async(url,init)=>{
  assert.equal(url,'/auth/admin-registration');assert.equal(init.method,'POST');assert.equal(init.credentials,'same-origin');
  assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
  assert.deepEqual(JSON.parse(init.body),input(kind));assert.equal(init.headers.Authorization,undefined);
  return Response.json(receipt(r,{token:'secret',subject:'private',issuer:'private'}));
 });
 assert.equal(s.phase,'confirmed');assert.deepEqual(s.receipt,receipt(r));assert.ok(Object.isFrozen(s.receipt));
});
test('registration synchronous double click lock and confirmed operation stop further POST',async()=>{
 const r=review(),c=new RegistrationSubmission(r);let calls=0,finish;
 const fetcher=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
 const first=c.send(true,fetcher);assert.equal(c.state.phase,'sending');
 assert.equal((await c.send(true,fetcher)).phase,'sending');assert.equal(calls,1);
 finish(Response.json(receipt(r)));await first;await c.send(true,fetcher);assert.equal(calls,1);
});
test('registration unknown recovery retries original bytes and records observed ACTIVE separately',async()=>{
 for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE']){
  const r=review(kind),c=new RegistrationSubmission(r),bodies=[];
  const fetcher=async(url,init)=>{bodies.push(init.body);if(bodies.length===1)throw Error('lost after commit');
   return Response.json(receipt(r,{current_status:'ACTIVE',replayed:true}));};
  assert.equal((await c.send(true,fetcher)).phase,'unknown');assert.equal(bodies.length,1);
  const recovered=await c.send(true,fetcher);assert.equal(recovered.phase,'confirmed');
  assert.equal(recovered.receipt.applied_status,r.initialStatus);assert.equal(recovered.receipt.current_status,'ACTIVE');
  assert.equal(recovered.receipt.replayed,true);assert.equal(bodies[0],bodies[1]);
 }
});
test('registration later denial or disabled gate cannot erase earlier uncertainty',async()=>{
 const c=new RegistrationSubmission(review());await c.send(true,async()=>{throw Error('lost');});
 const denial=await c.send(true,async()=>Response.json({error:'submission_forbidden'},{status:403}));
 assert.equal(denial.phase,'unknown');assert.equal(denial.error,'submission_forbidden');
 assert.equal((await c.send(false)).phase,'unknown');assert.equal(c.state.review.request.body.event_no,'ADM-ORIGINAL');
});
test('registration first authoritative denial is rejected without automatic retry',async()=>{
 for(const [status,error] of [[401,'session_required'],[403,'read_only_mode'],[404,'registration_target_not_found'],
 [409,'admin_recipient_protected'],[409,'principal_registration_conflict'],[422,'invalid_request'],
 [503,'configured_issuer_required'],[503,'registration_submission_disabled']]){
  let calls=0;const c=new RegistrationSubmission(review()),s=await c.send(true,async()=>{calls++;return Response.json({error},{status});});
  assert.equal(s.phase,'rejected');assert.equal(s.error,error);assert.equal(calls,1);
 }
});
test('registration wrong identity, state or scope receipt remains unknown',async()=>{
 for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE']){
  const r=review(kind),changes=[{kind:'OTHER'},{id:principalId},{audit_event_no:'OTHER'},{applied_status:'ACTIVE'},
   {current_status:'OTHER'},{replayed:1},...(kind==='PRINCIPAL'?[{revoked_browser_sessions:1},{current_status:'SUSPENDED'}]:
   [{principal_id:id},{role:'OTHER'},{current_status:'DISABLED'},...(kind==='GLOBAL'?[]:[{scope_id:id}])])];
  for(const change of changes){const c=new RegistrationSubmission(r),s=await c.send(true,async()=>Response.json(receipt(r,change)));
   assert.equal(s.phase,'unknown');assert.equal(s.error,'outcome_unknown');assert.equal(s.receipt,null);}
  assert.equal(projectRegistrationReceipt([],r),null);
 }
});
test('registration malformed, oversized, arbitrary denial and server error are unknown',async()=>{
 const r=review();
 for(const response of [()=>new Response('private'),()=>new Response('{',{headers:{'Content-Type':'application/json'}}),
  ()=>Response.json(receipt(r),{headers:{'Content-Length':'16385'}}),()=>Response.json({padding:'x'.repeat(16385)}),
  ()=>Response.json({error:'private'},{status:403}),()=>Response.json({error:'invalid_request'},{status:500}),
  ()=>Response.json({error:'outcome_unknown'},{status:502}),()=>Response.json(receipt(r),{headers:{'Content-Type':'application/json-evil'}})]){
  let calls=0;const c=new RegistrationSubmission(r),s=await c.send(true,async()=>{calls++;return response();});
  assert.equal(s.phase,'unknown');assert.equal(s.error,'outcome_unknown');assert.equal(calls,1);
 }
});

