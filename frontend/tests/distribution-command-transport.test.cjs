'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-distribution-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/distribution-command-transport.ts','lib/distribution-command-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {parseDistributionCommand:parse,distributionReview:review,distributionPath:eventPath,distributionEvent:eventNo,projectDistributionReceipt:project,DistributionSubmission:Submission}=require(path.join(output,'distribution-command-transport.js'));
const {projectDistributionAudit:audit}=require(path.join(output,'distribution-command-audit.js'));
const f=require('./fixtures/distribution-command.cjs'),copy=value=>JSON.parse(JSON.stringify(value));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
for(const operation of ['delivery','distribution','authorization']){
 test(operation+' exact parser freezes original body, target and fixed collection path',()=>{
  const c=f.command(operation),parsed=parse(c);assert.deepEqual(parsed,c);assert.ok(Object.isFrozen(parsed));assert.ok(Object.isFrozen(parsed.body));
  assert.equal(eventPath(parsed),'/api/v1/'+(operation==='delivery'?'deliveries':operation==='distribution'?'distributions':'authorizations'));
  assert.equal(eventNo(parsed),f.eventNo(c));if(operation==='delivery')assert.ok(Object.isFrozen(parsed.body.snapshot_artifact_ids));
 });
 test(operation+' actor-bound exact original audit projects a bounded secret-free receipt',()=>{
  const c=f.command(operation),e=f.audit(c);assert.deepEqual(audit(e,c,f.principal),f.receipt(c));
  assert.equal(project({...f.receipt(c),token:'private',current_status:'APPROVED'},c).current_status,undefined);
  for(const mutate of [e=>e.event_no='WRONG',e=>e.id='invalid',e=>e.actor_principal_id=f.key,e=>e.payload.actor_source='LEGACY',
   e=>e.entity_id=f.release,e=>e.entity_type='WRONG',e=>e.event_type='WRONG',e=>e.action='WRONG',e=>e.entity_ref='WRONG',
   e=>e.payload.request.token='private',e=>e.payload.request=null,e=>e.payload.request.request_id=f.key]){
   const bad=copy(e);mutate(bad);assert.equal(audit(bad,c,f.principal),null);
  }
  for(const [field,value]of Object.entries(c.body)){if(field==='request_id')continue;
   const bad=copy(e);bad.payload.request[field]=value===null?'CHANGED':Array.isArray(value)?[f.release]:typeof value==='number'?value+1:'CHANGED';
   assert.equal(audit(bad,c,f.principal),null,field);
  }
 });
 test(operation+' receipt rejects mismatched original identity, status, scope and evidence',()=>{
  const c=f.command(operation),good=f.receipt(c),r=good.result;
  for(const patch of [{operation:'resource'},{request_id:f.release},{target:f.key},{audit_event_no:'WRONG'}])assert.equal(project({...good,...patch},c),null);
  for(const field of Object.keys(r)){
   const value=r[field],changed=field==='id'?f.release:field==='status'?'APPROVED':
    Array.isArray(value)?[f.release]:typeof value==='number'?2147483648:value===null?'CHANGED':
    /_id$/.test(field)?'invalid':'';
   assert.equal(project({...good,result:{...r,[field]:changed}},c),null,field);
  }
 });
 test(operation+' fixed frozen body posts once and an exact receipt becomes terminal',async()=>{
  const c=f.command(operation),s=new Submission(review(c));let calls=0;
  await s.send(true,async(url,init)=>{calls++;assert.equal(url,'/auth/distribution-command');assert.equal(init.method,'POST');
   assert.equal(init.body,JSON.stringify(c));assert.equal(init.credentials,'same-origin');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
   return Response.json(f.receipt(c));});assert.equal(s.state.phase,'confirmed');
  const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 });
 test(operation+' uncertain result queries without resubmitting and explicitly retries identical bytes',async()=>{
  const c=f.command(operation),s=new Submission(review(c)),bodies=[];let calls=0;
  await s.send(true,async(url,init)=>{calls++;bodies.push(init.body);throw Error('lost');});assert.equal(s.state.phase,'unknown');
  c.target=f.key;c.body.request_id=f.release;if(operation==='delivery')c.body.snapshot_artifact_ids.push(f.release);
  await s.recover(true,async(url,init)=>{calls++;bodies.push(init.body);assert.equal(url,'/auth/distribution-command-receipt');
   return Response.json({error:'outcome_unknown'},{status:502});});assert.equal(s.state.phase,'unknown');
  await s.send(true,async(url,init)=>{calls++;bodies.push(init.body);return Response.json(f.receipt(s.state.command));});
  assert.equal(s.state.phase,'confirmed');assert.equal(new Set(bodies).size,1);assert.equal(calls,3);
 });
}
test('canonical UUIDs, immutable artifact sets and explicit null/unlimited retain exact semantics',()=>{
 const c=f.command('delivery');c.target=c.target.toUpperCase();c.body.release_id=c.body.release_id.toUpperCase();
 c.body.request_id=c.body.request_id.toUpperCase();c.body.snapshot_artifact_ids.reverse();c.body.created_by=null;
 const expected=f.command('delivery');expected.body.created_by=null;assert.deepEqual(parse(c),expected);
 const authorization=f.command('authorization');authorization.body.batch_limit=null;authorization.body.restriction_note=null;
 assert.deepEqual(parse(authorization),authorization);const r=audit(f.audit(authorization),authorization,f.principal);
 assert.equal(r.result.batch_limit,null);assert.equal(r.result.status,'DRAFT');
});
test('strict body fields, redundant target binding, arrays, positive PG integers and UTF-8 size fail closed',()=>{
 const c=f.command('delivery'),d=f.command('distribution'),a=f.command('authorization');
 const badBodies=[{...c.body,revision:'2'},{...c.body,revision:0},{...c.body,revision:2147483648},
  {...c.body,release_id:f.packageId},{...c.body,created_by:''},{...c.body,created_by:'x'.repeat(121)},
  {...c.body,recipient_type:'bad\nvalue'},{...c.body,recipient_code:'x'.repeat(81)},{...c.body,purpose:'x'.repeat(51)},
  {...c.body,snapshot_artifact_ids:[]},{...c.body,snapshot_artifact_ids:'invalid'},
  {...c.body,snapshot_artifact_ids:[f.artifact,f.artifact.toUpperCase()]},{...c.body,snapshot_artifact_ids:[null]},
  {...c.body,snapshot_artifact_ids:Array(201).fill(f.artifact)},{...c.body,token:'private'}];
 for(const body of badBodies)assert.equal(parse({...c,body}),null);
 for(const bad of [null,[],{...c,url:'https://evil'},{...c,operation:'approval'},{...c,target:'../evil'},
  {...c,body:{...c.body,request_id:'invalid'}},{...d,body:{...d.body,delivery_package_id:f.release}},
  {...d,body:{...d.body,distribution_no:'../evil'}},{...a,body:{...a.body,distribution_id:f.release}},
  {...a,body:{...a.body,batch_limit:undefined}},{...a,body:{...a.body,batch_limit:0}},{...a,body:{...a.body,batch_limit:'2'}},
  {...a,body:{...a.body,customer_id:'invalid'}},{...a,body:{...a.body,site_code:'bad\nsite'}},
  {...a,body:{...a.body,restriction_note:''}},{...a,body:{...a.body,restriction_note:'中'.repeat(3000)}}])assert.equal(parse(bad),null);
});
test('delivery audit matches artifact set and original revision, policy and frozen evidence',()=>{
 const c=f.command('delivery'),good=f.audit(c);good.payload.snapshot_artifact_ids.reverse();good.current_status='SENT';
 assert.deepEqual(audit(good,c,f.principal),f.receipt(c));
 for(const mutate of [e=>e.payload.revision=3,e=>e.payload.release_id=f.packageId,e=>e.payload.snapshot_id='invalid',
  e=>e.payload.snapshot_no='',e=>e.payload.decision_no='',e=>e.payload.approval_no='',e=>e.payload.recipient_code='CHANGED',
  e=>e.payload.purpose='CHANGED',e=>e.payload.snapshot_artifact_ids=[f.artifact,f.artifact],e=>e.payload.snapshot_artifact_ids=[f.release],
  e=>e.payload.request.snapshot_artifact_ids.reverse()]){
  const bad=copy(f.audit(c));mutate(bad);assert.equal(audit(bad,c,f.principal),null);
 }
});
test('distribution and authorization retain original READY/DRAFT, exact revision and finite/unlimited scope',()=>{
 for(const operation of ['distribution','authorization']){
  const c=f.command(operation),e=f.audit(c);e.current_status=operation==='distribution'?'ACKNOWLEDGED':'APPROVED';
  assert.equal(audit(e,c,f.principal).result.status,operation==='distribution'?'READY':'DRAFT');
  const changes=operation==='distribution'?{delivery_package_id:f.release,recipient_type:'OTHER',recipient_code:'OTHER',revision:0}:
   {distribution_id:f.release,customer_id:f.release,project_id:f.release,release_id:f.packageId,site_code:'OTHER',line_code:'OTHER',
    purpose:'OTHER',batch_limit:null,revision:0,delivery_package_id:'invalid',distribution_no:''};
  for(const [field,value]of Object.entries(changes)){const bad=copy(e);bad.payload[field]=value;assert.equal(audit(bad,c,f.principal),null,field);}
 }
});
test('unconfirmed and forged route/trace/audit/payload cannot construct an original submission',()=>{
 const c=review(f.command('delivery'));
 for(const patch of [{confirmed:false},{confirmed:'true'},{draft:{...c.draft,path:'https://evil'}},
  {draft:{...c.draft,trace:'/other'}},{draft:{...c.draft,audit:'/other'}},
  {draft:{...c.draft,payload:{...c.draft.payload,token:'private'}}}])assert.throws(()=>new Submission({...c,...patch}));
});
test('synchronous write/query locks reject double clicks and concurrent retry',async()=>{
 const s=new Submission(review(f.command('delivery')));let calls=0,finish;
 const pending=s.send(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'sending');
 const never=async()=>{calls++;throw Error('unexpected');};await s.send(true,never);await s.recover(true,never);assert.equal(calls,1);
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;
 const checking=s.recover(true,async()=>{calls++;return new Promise(resolve=>{finish=resolve;});});assert.equal(s.state.phase,'checking');
 await s.send(true,never);await s.recover(true,never);assert.equal(calls,2);finish(Response.json(f.receipt(s.state.command)));await checking;
 assert.equal(s.state.phase,'confirmed');
});
test('later gate/key/business/scope denial cannot erase earlier uncertainty',async()=>{
 const s=new Submission(review(f.command('authorization')));let calls=0;await s.send(false,async()=>{calls++;});assert.equal(s.state.phase,'rejected');
 await s.send(true,async()=>{throw Error('lost');});
 for(const error of ['request_conflict','submission_conflict']){await s.send(true,async()=>Response.json({error},{status:409}));assert.equal(s.state.phase,'unknown');}
 await s.send(true,async()=>Response.json({error:'submission_forbidden'},{status:403}));assert.equal(s.state.phase,'unknown');
 await s.recover(false,async()=>{calls++;});assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'distribution_submission_disabled');assert.equal(calls,0);
});
test('invalid, oversized, interrupted or unexpected response stays unknown with no automatic retry',async()=>{
 for(const reply of [()=>Response.json({}),()=>Response.json({error:'private'},{status:409}),()=>Response.json({},{status:201}),()=>new Response('private'),
  ()=>Response.json({padding:'x'.repeat(16385)}),()=>Response.json({},{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new ReadableStream({start(c){c.error(Error('broken'));}}),{headers:{'Content-Type':'application/json'}})]){
  const s=new Submission(review(f.command('distribution')));let calls=0;await s.send(true,async()=>{calls++;return reply();});assert.equal(s.state.phase,'unknown');assert.equal(calls,1);
 }
});
test('a denied explicit audit query never proves the original operation was not committed',async()=>{
 const s=new Submission(review(f.command('distribution')));await s.recover(true,async()=>Response.json({error:'session_required'},{status:401}));
 assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'session_required');
});
