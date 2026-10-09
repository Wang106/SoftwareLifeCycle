'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-production-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/production-command-transport.ts','lib/production-command-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {parseProductionCommand:parse,productionReview:review,productionPath:eventPath,productionEvent:eventNo,projectProductionReceipt:project,ProductionSubmission:Submission,productionTime:time}=require(path.join(output,'production-command-transport.js'));
const {projectProductionAudit:audit}=require(path.join(output,'production-command-audit.js'));
const f=require('./fixtures/production-command.cjs'),copy=value=>JSON.parse(JSON.stringify(value));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
for(const operation of ['test-release','deployment','changeover']){
 test(operation+' exact parser freezes canonical body and existing fixed path/event',()=>{
  const c=f.command(operation),parsed=parse(c);assert.deepEqual(parsed,c);assert.ok(Object.isFrozen(parsed));assert.ok(Object.isFrozen(parsed.body));
  assert.equal(eventPath(parsed),operation==='test-release'?'/api/v1/testing/releases':operation==='deployment'?'/api/v1/deployments':'/api/v1/deployments/'+encodeURIComponent(c.target)+'/changeovers');
  assert.equal(eventNo(parsed),f.eventNo(c));
 });
 test(operation+' original actor-bound audit projects only exact original receipt',()=>{
  const c=f.command(operation),e=f.audit(c);assert.deepEqual(audit(e,c,f.principal),f.receipt(c));
  assert.equal(project({...f.receipt(c),token:'private',current_status:'APPROVED'},c).current_status,undefined);
  for(const mutate of [e=>e.event_no='WRONG',e=>e.id='invalid',e=>e.actor_principal_id=f.key,e=>e.payload.actor_source='LEGACY',
   e=>e.entity_id=f.release,e=>e.entity_type='WRONG',e=>e.event_type='WRONG',e=>e.action='WRONG',e=>e.entity_ref='WRONG',
   e=>e.declared_actor_name='OTHER',e=>e.payload.status='APPROVED']){
   const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
  }
 });
 test(operation+' exact receipt rejects altered identity, status, scope and original evidence',()=>{
  const c=f.command(operation),good=f.receipt(c);
  for(const patch of [{operation:'resource'},{request_id:f.release},{target:f.key},{audit_event_no:'WRONG'}])assert.equal(project({...good,...patch},c),null);
  for(const field of Object.keys(good.result)){const value=good.result[field],changed=value===null?'CHANGED':'';
   assert.equal(project({...good,result:{...good.result,[field]:changed}},c),null,field);}
 });
 test(operation+' confirmed frozen request sends original bytes once and becomes terminal',async()=>{
  const c=f.command(operation),r=review(c),s=new Submission(r),original=JSON.stringify({operation,target:c.target,body:r.draft.payload});let calls=0;
  await s.send(true,async(url,init)=>{calls++;assert.equal(url,'/auth/production-command');assert.equal(init.method,'POST');assert.equal(init.body,original);
   assert.equal(init.credentials,'same-origin');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);return Response.json(f.receipt(c));});
  assert.equal(s.state.phase,'confirmed');const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 });
 test(operation+' lost response freezes target/body and only explicit retry repeats original bytes',async()=>{
  const c=f.command(operation),s=new Submission(review(c)),bodies=[];let calls=0;
  await s.send(true,async(url,init)=>{calls++;bodies.push(init.body);throw Error('lost');});assert.equal(s.state.phase,'unknown');c.target=f.key;c.body.request_id=f.release;
  await s.recover(true,async(url,init)=>{calls++;bodies.push(init.body);assert.equal(url,'/auth/production-command-receipt');return Response.json({error:'outcome_unknown'},{status:502});});
  assert.equal(s.state.phase,'unknown');await s.send(true,async(url,init)=>{calls++;bodies.push(init.body);return Response.json(f.receipt(s.state.command));});
  assert.equal(s.state.phase,'confirmed');assert.equal(new Set(bodies).size,1);assert.equal(calls,3);
 });
}
test('strict fields, redundant UUID targets, declarations and UTF-8 bounds fail closed',()=>{
 const t=f.command('test-release'),d=f.command('deployment'),c=f.command('changeover');
 for(const bad of [null,[],{...t,url:'https://evil'},{...t,operation:'delivery'},{...t,target:f.authorization},
  {...t,body:{...t.body,release_id:f.key}},{...t,body:{...t.body,request_id:'invalid'}},{...t,body:{...t.body,snapshot_id:'invalid'}},
  {...t,body:{...t.body,purpose_scope:'PRODUCTION'}},{...t,body:{...t.body,actor_name:'x'.repeat(121)}},
  {...t,body:{...t.body,reason:' '}},{...t,body:{...t.body,reason:'中'.repeat(3000)}},
  {...d,body:{...d.body,authorization_id:f.release}},{...d,body:{...d.body,production_line_id:'invalid'}},{...d,body:{...d.body,deployment_no:'../evil'}},
  {...c,target:'../evil'},{...c,body:{...c.body,changed_at:0}},{...c,body:{...c.body,changed_at:''}},{...c,body:{...c.body,changed_at:'2026-02-30T00:00:00Z'}},{...c,body:{...c.body,changed_at:'0100-01-01T00:00:00+23:59'}},
  {...c,body:{...c.body,changed_at:'2026-10-09T02:00:00'}},{...c,body:{...c.body,note:''}},{...c,body:{...c.body,note:'中'.repeat(3000)}},
  {...c,body:{...c.body,token:'private'}}])assert.equal(parse(bad),null);
});
test('canonical case, trimmed test declarations, exact changeover note and UTC request time preserve backend semantics',()=>{
 const t=f.command('test-release');t.target=t.target.toUpperCase();t.body.release_id=t.body.release_id.toUpperCase();t.body.request_id=t.body.request_id.toUpperCase();
 t.body.actor_name='  Declared operator  ';t.body.reason='  Original reason\n原文  ';assert.deepEqual(parse(t),f.command('test-release'));
 const c=f.command('changeover');c.body.note='  exact\n原文  ';c.body.changed_at='2026-10-09T10:00:00.123+08:00';
 assert.equal(parse(c).body.changed_at,'2026-10-09T02:00:00.123Z');assert.equal(parse(c).body.note,c.body.note);
});
test('test-release existing audit binds declaration, reason and all original fields without requiring a request payload',()=>{
 const c=f.command('test-release'),e=f.audit(c);assert.equal(e.payload.request,undefined);assert.ok(audit(e,c,f.principal));
 for(const mutate of [e=>e.detail='OTHER',e=>e.declared_actor_name='OTHER',e=>e.payload.release_id=f.key,
  e=>e.payload.snapshot_id=f.key,e=>e.payload.purpose_scope='CUSTOMER_TEST',e=>e.payload.snapshot_no='']){
  const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
 }
});
test('deployment and changeover bind every original request fingerprint field, including null timestamp/note',()=>{
 for(const operation of ['deployment','changeover']){const c=f.command(operation),e=f.audit(c);
  for(const [field,value]of Object.entries(e.payload.request)){const bad=copy(e);bad.payload.request[field]=value===null?'CHANGED':'OTHER';assert.equal(audit(bad,c,f.principal),null,field);}
  for(const request of [null,{...e.payload.request,token:'private'}])assert.equal(audit({...e,payload:{...e.payload,request}},c,f.principal),null);
 }
});
test('later current status never replaces original DRAFT, PENDING or COMPLETED',()=>{
 for(const operation of ['test-release','deployment','changeover']){const c=f.command(operation),e=f.audit(c);e.current_status='APPROVED';assert.deepEqual(audit(e,c,f.principal),f.receipt(c));}
});
test('changeover occurrence preserves original generated microseconds and exact UTC explicit time',()=>{
 const c=f.command('changeover'),e=f.audit(c);assert.equal(audit(e,c,f.principal).result.changed_at,'2026-10-09T02:00:00.123456Z');
 c.body.changed_at='2026-10-09T02:00:00.123Z';assert.deepEqual(audit(f.audit(c),c,f.principal),f.receipt(c));
 const wrong=f.audit(c);wrong.occurred_at='2026-10-09T02:00:00.123001Z';assert.equal(audit(wrong,c,f.principal),null);
 const same=f.audit(c);same.payload.to_release_id=c.body.from_release_id;assert.equal(audit(same,c,f.principal),null);
 assert.equal(time('2026-10-09T10:00:00.123456+08:00'),'2026-10-09T02:00:00.123456Z');
 for(const value of ['2026-02-30T00:00:00Z','2026-10-09T24:00:00Z','2026-10-09T00:00:00+24:00','2026-10-09T00:00:00.1234567Z','2026-10-09T00:00:00',null])assert.equal(time(value),null);
});

test('unconfirmed and forged route/trace/audit/payload cannot construct an original submission',()=>{
 const c=review(f.command('test-release'));
 for(const patch of [{confirmed:false},{confirmed:'true'},{draft:{...c.draft,path:'https://evil'}},
  {draft:{...c.draft,trace:'/other'}},{draft:{...c.draft,audit:'/other'}},
  {draft:{...c.draft,payload:{...c.draft.payload,token:'private'}}}])assert.throws(()=>new Submission({...c,...patch}));
});
test('synchronous write/query locks reject double clicks and concurrent retry',async()=>{
 const s=new Submission(review(f.command('test-release')));let calls=0,finish;
 const pending=s.send(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'sending');
 const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;
 const checking=s.recover(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'checking');
 await s.send(true,never);await s.recover(true,never);assert.equal(calls,2);finish(Response.json(f.receipt(s.state.command)));await checking;
 assert.equal(s.state.phase,'confirmed');
});
test('later gate/key/business/scope denial cannot erase earlier uncertainty',async()=>{
 const s=new Submission(review(f.command('changeover')));let calls=0;await s.send(false,async()=>{calls++;});assert.equal(s.state.phase,'rejected');
 await s.send(true,async()=>{throw Error('lost');});
 for(const error of ['request_conflict','submission_conflict']){await s.send(true,async()=>Response.json({error},{status:409}));assert.equal(s.state.phase,'unknown');}
 await s.send(true,async()=>Response.json({error:'submission_forbidden'},{status:403}));assert.equal(s.state.phase,'unknown');
 await s.recover(false,async()=>{calls++;});assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'production_submission_disabled');assert.equal(calls,0);
});
test('invalid, oversized, interrupted or unexpected response stays unknown with no automatic retry',async()=>{
 for(const reply of [()=>Response.json({}),()=>Response.json({error:'private'},{status:409}),()=>Response.json({},{status:201}),()=>new Response('private'),
  ()=>Response.json({padding:'x'.repeat(16385)}),()=>Response.json({},{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new ReadableStream({start(c){c.error(Error('broken'));}}),{headers:{'Content-Type':'application/json'}})]){
  const s=new Submission(review(f.command('deployment')));let calls=0;await s.send(true,async()=>{calls++;return reply();});assert.equal(s.state.phase,'unknown');assert.equal(calls,1);
 }
});
test('a denied explicit audit query never proves the original operation was not committed',async()=>{
 const s=new Submission(review(f.command('deployment')));await s.recover(true,async()=>Response.json({error:'session_required'},{status:401}));
 assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'session_required');
});
