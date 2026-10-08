'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-principal-transport-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/principal-status-transport.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {PrincipalSubmission,parsePrincipalStatusCommand:parse,projectPrincipalStatusReceipt:project,principalSubmissionMessages}=require(path.join(output,'principal-status-transport.js'));
const {preparePrincipalStatus:prepare,confirmPrincipalStatus:confirm,exportPrincipalStatus:exportRequest}=require(path.join(output,'principal-status-draft.js'));
const dictionary=require('../lib/i18n/zh.json');
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id='12345678-1234-1234-1234-123456789abc',other='23456789-1234-1234-1234-123456789abc';
const target={id,principalType:'USER',status:'ACTIVE',historyStatus:'ACTIVE',protectedAdministrator:false,issuerMatchesConfiguration:true};
function reviewed(extra={},key='ADM-ORIGINAL'){return confirm(prepare({...target,...extra},key,'Controlled identity reason'),true);}
function command(review){return {principal_id:review.target.id,...review.request.body};}
function receipt(review,extra={}){return {principal_id:id,audit_event_no:review.request.body.event_no,
 applied_status:review.request.body.status,current_status:review.request.body.status,replayed:false,
 revoked_browser_sessions:review.request.body.status==='DISABLED'?3:0,...extra};}
test('unconfirmed, edited or forged path/body cannot construct a transport controller',()=>{
 const r=prepare(target,'ADM-1','Controlled reason');assert.throws(()=>new PrincipalSubmission(r),/Confirm/);
 const ready=confirm(r,true);
 for(const confirmed of [undefined,'true',1])assert.throws(()=>new PrincipalSubmission({...ready,confirmed}),/Confirm/);
 for(const patch of [{path:'/evil'},{method:'GET'},{body:{...r.request.body,status:'ACTIVE'}},
  {body:{...r.request.body,reason:' changed reason '}}])
  assert.throws(()=>new PrincipalSubmission({...ready,request:{...ready.request,...patch}}));
});
test('command parser binds UUID and exact five fields without actor, URL or snapshot claims',()=>{
 const c=command(reviewed()),normalized=parse({...c,principal_id:id.toUpperCase(),reason:'  '+c.reason+'  '});
 assert.deepEqual(normalized,c);assert.ok(Object.isFrozen(normalized));
 for(const patch of [{principal_id:'../evil'},{event_no:' bad '},{status:'SUSPENDED'},
  {expected_status:'DISABLED'},{reason:'four'},{reason:'😀'.repeat(501)},{reason:'reason\ncontrol'},
  {actor:id},{path:'/evil'},{token:'secret'},{protectedAdministrator:false},{principalType:'USER'}])
  assert.equal(parse({...c,...patch}),null);
 for(const input of [null,[],{},Object.fromEntries(Object.entries(c).filter(([k])=>k!=='event_no'))])assert.equal(parse(input),null);
 assert.equal(Array.from(parse({...c,event_no:'A'.repeat(50),reason:'😀'.repeat(500)}).reason).length,500);
 assert.equal(parse({...c,event_no:'A'.repeat(51)}),null);
});
test('disabled or non-boolean capability never sends a network request',async()=>{
 for(const enabled of [false,undefined,'enabled',1]){
  let calls=0;const state=await new PrincipalSubmission(reviewed()).send(enabled,async()=>{calls++;});
  assert.equal(calls,0);assert.equal(state.phase,'rejected');assert.equal(state.error,'principal_submission_disabled');
 }
});
for(const principalType of ['USER','SERVICE'])for(const status of ['ACTIVE','DISABLED'])
 test('fixed browser route, exact body and receipt: '+principalType+' '+status,async()=>{
  const r=reviewed({principalType,status,historyStatus:status}),controller=new PrincipalSubmission(r);
  const state=await controller.send(true,async(url,init)=>{
   assert.equal(url,'/auth/principal-status');assert.equal(init.method,'POST');assert.equal(init.credentials,'same-origin');
   assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');assert.ok(init.signal);
   assert.deepEqual(init.headers,{'Content-Type':'application/json',Accept:'application/json'});
   assert.deepEqual(JSON.parse(init.body),command(r));
   return Response.json(receipt(r,{token:'private',subject:'private'}));
  });
  assert.equal(state.phase,'confirmed');assert.deepEqual(state.receipt,receipt(r));
  assert.ok(Object.isFrozen(state));assert.ok(Object.isFrozen(state.receipt));
 });
test('double clicks lock before React render and confirmed receipt is terminal',async()=>{
 const r=reviewed(),controller=new PrincipalSubmission(r);let calls=0,finish;
 const fetcher=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
 const first=controller.send(true,fetcher);
 assert.equal(controller.state.phase,'sending');assert.equal((await controller.send(true,fetcher)).phase,'sending');assert.equal(calls,1);
 finish(Response.json(receipt(r)));await first;
 assert.equal((await controller.send(true,fetcher)).phase,'confirmed');assert.equal(calls,1);
});
test('lost response retains frozen original bytes and explicit replay with independent current status',async()=>{
 const r=reviewed(),controller=new PrincipalSubmission(r),bodies=[];
 const fetcher=async(url,init)=>{bodies.push(init.body);if(bodies.length===1)throw Error('lost after commit');
  return Response.json(receipt(r,{replayed:true,current_status:'ACTIVE'}));};
 const unknown=await controller.send(true,fetcher);
 assert.equal(unknown.phase,'unknown');assert.equal(bodies.length,1);assert.equal(exportRequest(unknown.review),exportRequest(r));
 const success=await controller.send(true,fetcher);assert.equal(success.phase,'confirmed');
 assert.equal(success.receipt.applied_status,'DISABLED');assert.equal(success.receipt.current_status,'ACTIVE');
 assert.equal(success.receipt.revoked_browser_sessions,3);assert.equal(success.receipt.replayed,true);
 assert.equal(bodies[0],bodies[1]);assert.throws(()=>{unknown.review.request.body.event_no='CHANGED';},TypeError);
});
test('later denial or disabled capability never resolves an earlier uncertain operation',async()=>{
 const r=reviewed(),controller=new PrincipalSubmission(r);let calls=0;
 await controller.send(true,async()=>{calls++;throw Error('lost');});
 for(const [status,error] of [[401,'session_required'],[403,'read_only_mode'],[409,'admin_principal_protected'],[404,'principal_not_found']]){
  const state=await controller.send(true,async()=>{calls++;return Response.json({error},{status});});
  assert.equal(state.phase,'unknown');assert.equal(state.error,error);assert.equal(state.receipt,null);
 }
 const before=calls;const disabled=await controller.send(false,async()=>{calls++;});
 assert.equal(disabled.phase,'unknown');assert.equal(disabled.error,'principal_submission_disabled');assert.equal(calls,before);
 assert.equal((await controller.send(true,async()=>Response.json(receipt(r,{replayed:true})))).phase,'confirmed');
});
test('first known denial is definitive for that attempt and never retries itself',async()=>{
 for(const [status,error] of [[400,'invalid_request'],[401,'session_required'],[403,'cross_origin_request'],
  [403,'submission_forbidden'],[403,'read_only_mode'],[404,'principal_not_found'],[409,'principal_status_conflict'],
  [409,'admin_principal_protected'],[409,'audit_event_conflict'],[409,'submission_conflict'],
  [413,'request_too_large'],[415,'json_required'],[422,'invalid_request'],[503,'principal_submission_disabled']]){
  let calls=0;const state=await new PrincipalSubmission(reviewed()).send(true,async()=>{calls++;return Response.json({error},{status});});
  assert.equal(state.phase,'rejected');assert.equal(state.error,error);assert.equal(calls,1);
 }
});
test('receipt binds target, audit number, applied state and actual safe revocation count',()=>{
 const r=reviewed(),c=command(r);
 for(const extra of [{principal_id:other},{audit_event_no:'OTHER'},{applied_status:'ACTIVE'},{current_status:'SUSPENDED'},
  {replayed:1},{revoked_browser_sessions:-1},{revoked_browser_sessions:0.5},{revoked_browser_sessions:true},
  {revoked_browser_sessions:'3'},{revoked_browser_sessions:Number.MAX_SAFE_INTEGER+1},{revoked_browser_sessions:undefined}])
  assert.equal(project(receipt(r,extra),c),null);
 assert.equal(project(receipt(r,{principal_id:id.toUpperCase()}),c),null);
 assert.deepEqual(project(receipt(r,{principal_id:id.toUpperCase()}),c,true),receipt(r));
 assert.equal(project(receipt(r,{revoked_browser_sessions:0}),c).revoked_browser_sessions,0);
 const enable=reviewed({status:'DISABLED',historyStatus:'DISABLED'});
 assert.equal(project(receipt(enable,{revoked_browser_sessions:1}),command(enable)),null);
 assert.ok(project(receipt(enable,{current_status:'DISABLED',replayed:true}),command(enable)));
});
test('bad, oversized, redirected or unexpected receipts preserve uncertainty without leaking details',async()=>{
 const r=reviewed();
 for(const reply of [()=>new Response('secret'),()=>new Response('{',{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>Response.json(receipt(r),{status:201}),()=>Response.json(receipt(r,{principal_id:other})),
  ()=>Response.json(receipt(r,{revoked_browser_sessions:true})),()=>Response.json({error:'secret'},{status:403}),
  ()=>Response.json({error:'invalid_request'},{status:500}),()=>Response.json({error:'session_required'},{status:302}),
  ()=>Response.json(receipt(r),{headers:{'Content-Length':'16385'}}),()=>Response.json({padding:'x'.repeat(16385)}),
  ()=>Response.json(receipt(r),{headers:{'Content-Type':'application/json-extra'}}),()=>Response.json({error:'secret'},{status:503})]){
  let calls=0;const state=await new PrincipalSubmission(r).send(true,async()=>{calls++;return reply();});
  assert.equal(state.phase,'unknown');assert.equal(state.error,'outcome_unknown');assert.equal(state.receipt,null);assert.equal(calls,1);
 }
});
test('interrupted receipt stream remains unknown without automatic retry',async()=>{
 let calls=0;const r=reviewed();
 const state=await new PrincipalSubmission(r).send(true,async()=>{calls++;
  return new Response(new ReadableStream({start(controller){controller.error(Error('interrupted'));}}),{headers:{'Content-Type':'application/json'}});
 });
 assert.equal(state.phase,'unknown');assert.equal(calls,1);
});
test('separate controller cannot overwrite original unknown memory',async()=>{
 const old=new PrincipalSubmission(reviewed());await old.send(true,async()=>{throw Error('lost');});
 const next=new PrincipalSubmission(reviewed({},'ADM-NEW'));
 assert.equal(old.state.review.request.body.event_no,'ADM-ORIGINAL');assert.equal(next.state.review.request.body.event_no,'ADM-NEW');
});
test('all public denial messages have Chinese translations',()=>{
 for(const value of Object.values(principalSubmissionMessages))assert.match(dictionary[value],/[\u4e00-\u9fff]/);
});
