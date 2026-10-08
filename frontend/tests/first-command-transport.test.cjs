'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-first-command-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/first-command-transport.ts','lib/first-command-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {parseFirstCommand:parse,commandReview,firstCommandPath,firstCommandEvent,projectFirstReceipt,FirstSubmission}=require(path.join(output,'first-command-transport.js'));
const {projectFirstAudit}=require(path.join(output,'first-command-audit.js'));
const {prepare,confirm,blankFields}=require(path.join(output,'command-draft.js'));
const f=require('./fixtures/first-command.cjs');after(()=>fs.rmSync(output,{recursive:true,force:true}));
for(const operation of ['snapshot','actual','batch'])test('canonical frozen '+operation+' command, paths and actor-bound audit projection',()=>{
 const c=parse(f.command(operation));assert.ok(c);assert.ok(Object.isFrozen(c));assert.ok(Object.isFrozen(c.body));
 assert.ok(firstCommandPath(c).startsWith('/api/v1/'));assert.equal(firstCommandEvent(c),f.eventNo(c));
 assert.deepEqual(projectFirstAudit(f.audit(c),c,f.release),f.receipt(c));
 const result=projectFirstReceipt({...f.receipt(c),token:'private',result:{...f.receipt(c).result,token:'private'}},c);
 assert.deepEqual(result,f.receipt(c));assert.ok(!JSON.stringify(result).includes('private'));
});
test('extra fields, unsupported commands and path/credential selection are rejected',()=>{
 for(const operation of ['snapshot','actual','batch']){
  const c=f.command(operation);
  for(const extra of [{url:'https://evil'},{actor:f.release},{token:'private'},{mode:'recover'}])assert.equal(parse({...c,...extra}),null);
  assert.equal(parse({...c,body:{...c.body,actor:'fake'}}),null);assert.equal(parse({...c,body:[]}),null);
  for(const target of ['../evil','/evil','..','bad\u0000'])assert.equal(parse({...c,target}),null);
 }
 for(const operation of ['approval','decision','deployment','unknown'])assert.equal(parse({...f.command('snapshot'),operation}),null);
 for(const request_id of ['',undefined,'../x'])assert.equal(parse({...f.command('actual'),body:{...f.command('actual').body,request_id}}),null);
});
test('actual PostgreSQL version and explicit calendar timestamp boundaries are checked',()=>{
 const c=f.command('actual');
 for(const expected_version of [-1,1.5,true,'4',2147483647,Number.MAX_SAFE_INTEGER])assert.equal(parse({...c,body:{...c.body,expected_version}}),null);
 for(const deployed_at of [1,'2026-02-30T00:00:00Z','2026-10-08T00:00:00','garbage'])assert.equal(parse({...c,body:{...c.body,deployed_at}}),null);
 assert.ok(parse({...c,body:{...c.body,expected_version:2147483646}}));
 const timed=parse({...c,body:{...c.body,deployed_at:'2026-10-08T08:00:00.123+08:00'}});
 assert.equal(timed.body.deployed_at,'2026-10-08T00:00:00.123Z');assert.deepEqual(projectFirstAudit(f.audit(timed),timed,f.release),f.receipt(timed));
 const whole=parse({...c,body:{...c.body,deployed_at:'2026-10-08T00:00:00Z'}});
 assert.deepEqual(projectFirstAudit(f.audit(whole),whole,f.release),f.receipt(whole));
});
test('frozen review must be explicitly confirmed and reconstruct exact path/body/trace/audit',()=>{
 const review=commandReview(parse(f.command('actual')));
 assert.throws(()=>new FirstSubmission({...review,confirmed:false}));assert.throws(()=>new FirstSubmission({...review,confirmed:'true'}));
 for(const patch of [{path:'https://evil'},{trace:'/wrong'},{audit:'/wrong'},
  {payload:{...review.draft.payload,actor:'fake'}},{operation:'approval'}])
  assert.throws(()=>new FirstSubmission({...review,draft:{...review.draft,...patch}}));
 const mutable={...review,draft:{...review.draft,payload:{...review.draft.payload}}},s=new FirstSubmission(mutable);
 mutable.draft.payload.correction_reason='different';assert.equal(s.state.command.body.correction_reason,review.draft.payload.correction_reason);
});
for(const operation of ['snapshot','actual','batch'])test('wrong audit actor, original target/body, entity or action cannot confirm '+operation,()=>{
 const c=parse(f.command(operation)),event=f.audit(c);
 for(const patch of [{actor_principal_id:f.key},{actor_principal_id:null},{event_no:'EVT-wrong'},{entity_id:f.event},
  {entity_ref:'wrong'},{event_type:'WRONG'},{entity_type:'WRONG'},{action:'WRONG'}]){
  // An actual operation's entity UUID is the deployment, not the request UUID; any different UUID still fails through explicit checks below.
  if(operation==='actual'&&Object.hasOwn(patch,'entity_id'))continue;
  assert.equal(projectFirstAudit({...event,...patch},c,f.release),null);
 }
 for(const request of [null,{...event.payload.request,actor:'fake'},{...event.payload.request,...(operation==='snapshot'?{release_id:f.key}:{deployment_no:'DEP-other'})}])
  assert.equal(projectFirstAudit({...event,payload:{...event.payload,request}},c,f.release),null);
 assert.equal(projectFirstAudit({...event,payload:{...event.payload,actor_source:'NOT_PROVIDED'}},c,f.release),null);
});
test('actual audit original applied pair/version is independent of later status reads',()=>{
 const c=parse(f.command('actual')),event=f.audit(c);
 for(const after of [{...event.payload.after,actual_version:6},{...event.payload.after,actual_release_id:f.key},
  {...event.payload.after,actual_snapshot_id:f.key},{...event.payload.after,status:'ACTIVE'}])
  assert.equal(projectFirstAudit({...event,payload:{...event.payload,after}},c,f.release),null);
 assert.equal(projectFirstAudit({...event,payload:{...event.payload,before:{actual_version:3}}},c,f.release),null);
 const projected=projectFirstAudit({...event,current_status:'MATCH',current_version:9},c,f.release);
 assert.equal(projected.result.status,'MISMATCH');assert.equal(projected.result.actual_version,5);
});
test('batch audit requires exact initial scope and snapshot identity, not current row status',()=>{
 const c=parse(f.command('batch')),event=f.audit(c);
 for(const patch of [{deployment_no:'other'},{changeover_id:f.key},{status:'STOPPED'},
  {deployment_id:'bad'},{authorization_id:'bad'},{release_id:'bad'},{snapshot_id:'bad'}])
  assert.equal(projectFirstAudit({...event,payload:{...event.payload,...patch}},c,f.release),null);
 const current={...event,current_status:'STOPPED'};assert.equal(projectFirstAudit(current,c,f.release).result.status,'ACTIVE');
});
test('browser rejects mismatched receipt key/target, snapshot number/hash, actual pair/version and batch identifiers',()=>{
 for(const operation of ['snapshot','actual','batch']){
  const c=parse(f.command(operation)),r=f.receipt(c);
  for(const patch of [{operation:'wrong'},{request_id:f.release},{target:'wrong'},{audit_event_no:'wrong'}])assert.equal(projectFirstReceipt({...r,...patch},c),null);
  const patches=operation==='snapshot'?[{id:f.release},{release_id:f.key},{snapshot_number:3},{content_hash:'x'}, {status:'ACTIVE'}]:
   operation==='actual'?[{actual_version:6},{actual_release_id:f.key},{actual_snapshot_id:f.key},{deployment_no:'wrong'},{status:'ACTIVE'}]:
   [{id:f.release},{batch_no:'wrong'},{deployment_no:'wrong'},{status:'STOPPED'},{release_id:'bad'}];
  for(const patch of patches)assert.equal(projectFirstReceipt({...r,result:{...r.result,...patch}},c),null);
 }
});
for(const operation of ['snapshot','actual','batch'])test('controller sends exact original '+operation+' bytes and becomes confirmed terminal',async()=>{
 const c=parse(f.command(operation)),s=new FirstSubmission(commandReview(c));let calls=0;
 const mock=async(url,init)=>{calls++;assert.equal(url,'/auth/first-command');assert.equal(init.method,'POST');
  assert.equal(init.credentials,'same-origin');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');assert.ok(init.signal);
  assert.deepEqual(JSON.parse(init.body),c);return Response.json({...f.receipt(c),token:'private'});};
 await s.send(true,mock);assert.equal(s.state.phase,'confirmed');assert.deepEqual(s.state.receipt,f.receipt(c));
 await s.send(true,mock);await s.recover(true,mock);assert.equal(calls,1);
});
test('synchronous lock prevents overlapping writes and recovery reads',async()=>{
 const c=parse(f.command('actual')),s=new FirstSubmission(commandReview(c));let finish,calls=0;
 const pending=s.send(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});
 assert.equal(s.state.phase,'sending');await s.send(true,async()=>{calls++;});await s.recover(true,async()=>{calls++;});assert.equal(calls,1);
 finish(Response.json(f.receipt(c)));await pending;assert.equal(s.state.phase,'confirmed');
});
test('lost write recovers through explicit read-only audit route with identical bytes and no automatic retry',async()=>{
 const c=parse(f.command('actual')),s=new FirstSubmission(commandReview(c)),calls=[];
 await s.send(true,async(url,init)=>{calls.push({url,body:init.body});throw Error('lost after commit');});
 assert.equal(s.state.phase,'unknown');assert.equal(calls.length,1);
 await s.recover(true,async(url,init)=>{calls.push({url,body:init.body});return Response.json(f.receipt(c));});
 assert.equal(s.state.phase,'confirmed');assert.equal(calls[1].url,'/auth/first-command-receipt');assert.equal(calls[0].body,calls[1].body);
});
test('missing audit, later denial and closed gate keep earlier uncertain write unknown',async()=>{
 const c=parse(f.command('batch')),s=new FirstSubmission(commandReview(c));let calls=0;
 await s.send(true,async()=>{calls++;throw Error('lost');});
 await s.recover(true,async()=>{calls++;return Response.json({error:'outcome_unknown'},{status:502});});assert.equal(s.state.phase,'unknown');
 await s.send(true,async()=>{calls++;return Response.json({error:'submission_forbidden'},{status:403});});
 assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'submission_forbidden');
 await s.send(false,async()=>{calls++;});assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'first_submission_disabled');assert.equal(calls,3);
});
test('first definitive rejection is limited to that attempt; recovery denial cannot prove an original write absent',async()=>{
 const s=new FirstSubmission(commandReview(parse(f.command('snapshot'))));
 await s.send(true,async()=>Response.json({error:'request_conflict'},{status:409}));assert.equal(s.state.phase,'rejected');
 await s.recover(true,async()=>Response.json({error:'session_required'},{status:401}));assert.equal(s.state.phase,'unknown');
 const disabled=new FirstSubmission(commandReview(parse(f.command('actual'))));let calls=0;
 await disabled.send(false,async()=>{calls++;});assert.equal(disabled.state.phase,'rejected');assert.equal(calls,0);
});
test('malformed, wrong-media, interrupted, oversized or unexpected responses stay unknown without retries',async()=>{
 const c=parse(f.command('snapshot'));
 for(const reply of [()=>new Response('private'),()=>new Response('{',{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>Response.json(f.receipt(c),{status:201}),()=>Response.json({error:'private'},{status:409}),
  ()=>Response.json({...f.receipt(c),padding:'x'.repeat(16385)}),
  ()=>Response.json(f.receipt(c),{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new ReadableStream({start(controller){controller.error(Error('interrupted'));}}),{headers:{'Content-Type':'application/json'}})]){
  const s=new FirstSubmission(commandReview(c));let calls=0;await s.send(true,async()=>{calls++;return reply();});
  assert.equal(s.state.phase,'unknown');assert.equal(calls,1);
 }
});

test('checking original audit locks out a simultaneous new write and keeps original bytes',async()=>{
 const c=parse(f.command('batch')),s=new FirstSubmission(commandReview(c));let finish,calls=0;
 const pending=s.recover(true,async(url,init)=>{calls++;assert.equal(url,'/auth/first-command-receipt');
  assert.deepEqual(JSON.parse(init.body),c);return new Promise(resolve=>{finish=resolve;});});
 assert.equal(s.state.phase,'checking');await s.send(true,async()=>{calls++;});await s.recover(true,async()=>{calls++;});assert.equal(calls,1);
 finish(Response.json(f.receipt(c)));await pending;assert.equal(s.state.phase,'confirmed');
});
