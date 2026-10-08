'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-governance-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/governance-command-transport.ts','lib/governance-command-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {parseGovernanceCommand:parse,governanceReview:review,governancePath:eventPath,governanceEvent:eventNo,projectGovernanceReceipt:project,GovernanceSubmission:Submission}=require(path.join(output,'governance-command-transport.js'));
const {projectGovernanceAudit:audit}=require(path.join(output,'governance-command-audit.js'));
const f=require('./fixtures/governance-command.cjs'),copy=value=>JSON.parse(JSON.stringify(value));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
for(const operation of ['approval','decision']){
 test(operation+' exact parser preserves declared text, null and original key; fixed encoded paths',()=>{
  const c=f.command(operation),parsed=parse(c);assert.deepEqual(parsed,c);assert.ok(Object.isFrozen(parsed));assert.ok(Object.isFrozen(parsed.body));
  assert.equal(eventPath(parsed),'/api/v1/approvals/'+encodeURIComponent(c.target)+(operation==='approval'?'/actions':'/release-decision'));
  assert.equal(eventNo(parsed),f.eventNo(c));const field=operation==='approval'?'comment':'notes';c.body[field]=null;assert.deepEqual(parse(c),c);
 });
 test(operation+' exact authenticated atomic audit produces a secret-free original receipt',()=>{
  const c=f.command(operation),e=f.audit(c);assert.deepEqual(audit(e,c,f.principal),f.receipt(c));
  assert.equal(audit(e,c,f.principal).token,undefined);assert.equal(project({...f.receipt(c),token:'private',current_status:'OTHER'},c).current_status,undefined);
  for(const mutate of [e=>e.event_no='WRONG',e=>e.id='invalid',e=>e.actor_principal_id=f.key,e=>e.payload.actor_source='LEGACY',
   e=>e.entity_id='invalid',e=>e.entity_type='WRONG',e=>e.event_type='WRONG',e=>e.action='WRONG',e=>e.entity_ref='WRONG',
   e=>e.payload.request.approval_no='WRONG',e=>e.payload.request.token='private',e=>e.payload.request[operation==='approval'?'actor':'decided_by']='Changed',
   e=>e.payload.request[operation==='approval'?'comment':'notes']='Changed',e=>e.payload.request=null]){
   const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
  }
 });
 test(operation+' receipt identity, original result and evidence mismatches are rejected',()=>{
  const c=f.command(operation),good=f.receipt(c);
  const changes=operation==='approval'?{approval_action_id:f.approval,step_id:f.release,action:'REJECTED',step_status:'PENDING',approval_status:'CANCELLED',
   step_order:2147483648,role_name:'',target_type:'',target_id:'invalid',snapshot_id:'invalid'}:
   {id:f.approval,decision_no:'WRONG',decision:'RELEASE',readiness_status:'READY',release_id:'invalid',snapshot_id:'invalid',snapshot_no:'',content_hash:'invalid'};
  for(const [field,value]of Object.entries(changes)){assert.equal(project({...good,result:{...good.result,[field]:value}},c),null);}
  for(const patch of [{operation:'resource'},{request_id:f.approval},{target:'WRONG'},{audit_event_no:'WRONG'},
   {result:{...good.result,approval_id:'invalid'}},{result:{...good.result,approval_no:'WRONG'}}])assert.equal(project({...good,...patch},c),null);
 });
 test(operation+' controller posts fixed original bytes and becomes terminal after exact receipt',async()=>{
  const c=f.command(operation),s=new Submission(review(c));let calls=0;
  await s.send(true,async(url,init)=>{calls++;assert.equal(url,'/auth/governance-command');assert.equal(init.method,'POST');assert.equal(init.body,JSON.stringify(c));
   assert.equal(init.credentials,'same-origin');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);return Response.json(f.receipt(c));});
  assert.equal(s.state.phase,'confirmed');const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 });
 test(operation+' lost response, explicit audit query and retry use immutable identical body',async()=>{
  const c=f.command(operation),s=new Submission(review(c)),bodies=[];let calls=0;
  await s.send(true,async(url,init)=>{bodies.push(init.body);calls++;throw Error('lost');});assert.equal(s.state.phase,'unknown');c.target='EDITED';c.body.request_id=f.approval;
  await s.recover(true,async(url,init)=>{assert.equal(url,'/auth/governance-command-receipt');bodies.push(init.body);calls++;return Response.json({error:'outcome_unknown'},{status:502});});
  assert.equal(s.state.phase,'unknown');await s.send(true,async(url,init)=>{assert.equal(url,'/auth/governance-command');bodies.push(init.body);calls++;return Response.json(f.receipt(s.state.command));});
  assert.equal(s.state.phase,'confirmed');assert.equal(new Set(bodies).size,1);assert.equal(calls,3);
 });
}
test('extra fields, invalid UUIDs/actions/declarations, paths and encoded bounds fail closed',()=>{
 const a=f.command('approval'),d=f.command('decision');
 for(const bad of [null,[],{...a,url:'https://evil'},{...a,operation:'snapshot'},{...a,target:'../evil'},
  {...a,body:{...a.body,request_id:'------------------------------------'}},{...a,body:{...a.body,expected_step_id:'invalid'}},
  {...a,body:{...a.body,action:'CANCELLED'}},{...a,body:{...a.body,actor:'x'.repeat(121)}},
  {...a,body:{...a.body,actor:'bad\nactor'}},{...a,body:{...a.body,comment:''}},
  {...a,body:{...a.body,token:'private'}},{...a,body:{...a.body,comment:'中'.repeat(3000)}},
  {...d,body:{...d.body,decision_no:'../evil'}},{...d,body:{...d.body,readiness_status:'x'.repeat(31)}},
  {...d,body:{...d.body,decided_by:' '}},{...d,body:{...d.body,decision:true}},{...d,body:{...d.body,notes:{}}}])assert.equal(parse(bad),null);
});
test('approval audit binds original step/action and preserves PENDING even after later closure',()=>{
 const c=f.command('approval'),e=f.audit(c);e.current_status='APPROVED';e.payload.current_step=f.release;
 assert.equal(audit(e,c,f.principal).result.approval_status,'PENDING');
 for(const mutate of [e=>e.payload.approval_action_id=f.approval,e=>e.payload.step_id=f.release,
  e=>e.payload.after_step_status='WAITING',e=>e.payload.after_status='REJECTED',e=>e.payload.request.expected_step_id=f.release]){
  const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
 }
 for(const action of ['RETURNED','REJECTED']){const c=f.command('approval');c.body.action=action;const e=f.audit(c);e.payload.snapshot_id=null;
  const receipt=audit(e,c,f.principal);assert.equal(receipt.result.approval_status,action);assert.equal(receipt.result.snapshot_id,null);}
});
test('decision audit binds approval and original declarations without assuming readiness or latest state',()=>{
 const c=f.command('decision'),e=f.audit(c);e.current_decision='RELEASE';assert.equal(audit(e,c,f.principal).result.decision,'  HOLD  ');
 for(const mutate of [e=>e.entity_id=f.approval,e=>e.payload.approval_no='WRONG',e=>e.payload.approval_id='invalid',
  e=>e.payload.decision='RELEASE',e=>e.payload.readiness_status='READY',e=>e.payload.release_id='invalid',e=>e.payload.content_hash='invalid']){
  const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
 }
});
test('unconfirmed, forged path/trace/audit/body and non-boolean confirmation cannot construct submission',()=>{
 const c=review(f.command('approval'));for(const patch of [{confirmed:false},{confirmed:'true'},
  {draft:{...c.draft,path:'https://evil'}},{draft:{...c.draft,trace:'/other'}},{draft:{...c.draft,audit:'/other'}},
  {draft:{...c.draft,payload:{...c.draft.payload,token:'private'}}}])assert.throws(()=>new Submission({...c,...patch}));
});
test('synchronous sending/checking lock prevents duplicate write and query',async()=>{
 const s=new Submission(review(f.command('approval')));let calls=0,finish;
 const pending=s.send(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'sending');
 const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;
 const checking=s.recover(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'checking');
 await s.send(true,never);await s.recover(true,never);assert.equal(calls,2);finish(Response.json(f.receipt(s.state.command)));await checking;assert.equal(s.state.phase,'confirmed');
});
test('closed capability and later step/key/permission denial cannot erase earlier uncertain result',async()=>{
 const s=new Submission(review(f.command('approval')));let calls=0;await s.send(false,async()=>{calls++;});assert.equal(s.state.phase,'rejected');assert.equal(calls,0);
 await s.send(true,async()=>{throw Error('lost');});for(const error of ['step_conflict','request_conflict','submission_conflict']){
  await s.send(true,async()=>Response.json({error},{status:409}));assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,error);
 }
 await s.send(true,async()=>Response.json({error:'submission_forbidden'},{status:403}));assert.equal(s.state.phase,'unknown');
 await s.recover(false,async()=>{calls++;});assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'governance_submission_disabled');assert.equal(calls,0);
});
test('strict bounded UTF-8 JSON responses and unexpected outcomes remain unknown',async()=>{
 for(const reply of [()=>Response.json({}),()=>Response.json({error:'private'},{status:409}),()=>Response.json({},{status:201}),
  ()=>new Response('private'),()=>Response.json({padding:'x'.repeat(16385)}),()=>Response.json({},{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new ReadableStream({start(c){c.error(Error('broken'));}}),{headers:{'Content-Type':'application/json'}})]){
  const s=new Submission(review(f.command('decision')));let calls=0;await s.send(true,async()=>{calls++;return reply();});assert.equal(s.state.phase,'unknown');assert.equal(calls,1);
 }
});
test('missing audit response after explicit query is never classified as uncommitted',async()=>{
 const s=new Submission(review(f.command('decision')));await s.recover(true,async()=>Response.json({error:'session_required'},{status:401}));
 assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'session_required');
});
