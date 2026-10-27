const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-changeover-recovery-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/changeover-correction-recovery.ts','lib/batch-correction-recovery.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const r=require(path.join(output,'changeover-correction-recovery.js')),t=require(path.join(output,'changeover-correction-transport.js')),f=require('./fixtures/changeover-correction.cjs');
const origin='https://lifecycle.example',exportText=(c=f.command())=>r.exportChangeoverCorrectionRecovery(t.confirmChangeoverCorrection(c,true),origin),copy=v=>JSON.parse(JSON.stringify(v));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
test('canonical compact and pretty exports preserve exact frozen command and all null semantics',()=>{
 const c=t.parseChangeoverCorrectionCommand(f.command()),text=exportText(c);
 assert.deepEqual(r.parseChangeoverCorrectionRecovery(text,origin),c);
 assert.deepEqual(r.parseChangeoverCorrectionRecovery(JSON.stringify(JSON.parse(text)),origin),c);
 const raw=f.command(),review=t.confirmChangeoverCorrection(raw,true);raw.body.note='changed after confirmation';
 assert.equal(r.exportChangeoverCorrectionRecovery(review,origin),text);
 assert.equal(r.parseChangeoverCorrectionRecovery(text,origin).body.changed_at,c.body.changed_at);
 assert.equal(r.parseChangeoverCorrectionRecovery(text,origin).body.note,null);
});
test('origin format version and every envelope boundary fail closed',()=>{
 const text=exportText();for(const mutate of [d=>d.format='slc-acceptance-correction-recovery',d=>d.version=2,d=>d.origin='https://other.example',d=>d.operation='changeover',d=>d.actor_principal_id=f.principal,d=>d.token='secret',d=>d.proof='secret',d=>d.receipt={confirmed:true},d=>d.target.url='https://other.example',d=>d.context.actor_principal_id=f.principal,d=>d.body.token='secret',d=>delete d.context]){
  const value=JSON.parse(text);mutate(value);assert.equal(r.parseChangeoverCorrectionRecovery(JSON.stringify(value),origin),null);
 }
 assert.equal(r.parseChangeoverCorrectionRecovery(text,'https://other.example'),null);
 const other=r.exportChangeoverCorrectionRecovery(t.confirmChangeoverCorrection(f.command(),true),'https://other.example');assert.ok(r.parseChangeoverCorrectionRecovery(other,'https://other.example'));assert.equal(r.parseChangeoverCorrectionRecovery(other,origin),null);
 for(const invalid of ['https://lifecycle.example/','https://user:pass@lifecycle.example','http://lifecycle.example','null','file:///tmp']){
  assert.equal(r.parseChangeoverCorrectionRecovery(text,invalid),null);assert.throws(()=>r.exportChangeoverCorrectionRecovery(t.confirmChangeoverCorrection(f.command(),true),invalid));
 }
 for(const local of ['http://localhost','http://127.0.0.1:3000','http://[::1]:3000']){
  const value=r.exportChangeoverCorrectionRecovery(t.confirmChangeoverCorrection(f.command(),true),local);assert.ok(r.parseChangeoverCorrectionRecovery(value,local));
 }
});
test('duplicate keys reordered keys alternate whitespace and silent timestamp normalization rejected',()=>{
 const text=exportText(),compact=JSON.stringify(JSON.parse(text));
 for(const value of [compact.replace('"version":1','"version":1,"version":1'),compact.replace('"note":null','"note":null,"note":null'),text.replace('  "format"',' "format"'),compact.replace('2026-01-01T00:00:00.000000Z','2026-01-01T00:00:00+00:00'),JSON.stringify({...JSON.parse(text),body:{...JSON.parse(text).body,request_id:f.key.toUpperCase()}})])assert.equal(r.parseChangeoverCorrectionRecovery(value,origin),null);
 const d=JSON.parse(text),{format,...rest}=d;assert.equal(r.parseChangeoverCorrectionRecovery(JSON.stringify({...rest,format}),origin),null);
});
test('head mismatch invalid times target drift and oversized text never import',()=>{
 for(const mutate of [d=>d.body.expected_revision=1,d=>d.body.predecessor_id=f.key,d=>d.target.changeover_no='OTHER',d=>d.context.changed_at='invalid',d=>d.body.note='x'.repeat(8192)]){
  const d=JSON.parse(exportText());mutate(d);assert.throws(()=>r.importChangeoverCorrectionRecovery(JSON.stringify(d),origin));
 }
 for(const text of ['', '{', ' '.repeat(r.changeoverCorrectionRecoveryTextLimit+1),'中'.repeat(Math.ceil(r.changeoverCorrectionRecoveryTextLimit/3)+1)])assert.equal(r.parseChangeoverCorrectionRecovery(text,origin),null);
 assert.throws(()=>r.exportChangeoverCorrectionRecovery(t.confirmChangeoverCorrection(f.command(),false),origin));
 const review=t.confirmChangeoverCorrection(f.command(),true);assert.throws(()=>r.exportChangeoverCorrectionRecovery({...review,confirmed:'true'},origin));
 assert.throws(()=>r.exportChangeoverCorrectionRecovery({...review,command:{...review.command,token:'secret'}},origin));
});
test('import has zero network starts unknown and exposes only frozen audit recovery',async()=>{
 const old=globalThis.fetch;let calls=0;try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  const s=r.importChangeoverCorrectionRecovery(exportText(),origin);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'outcome_unknown');
  assert.deepEqual(Object.keys(s),['state','recover']);assert.equal(s.send,undefined);assert.equal(s.retry,undefined);assert.ok(Object.isFrozen(s));assert.ok(Object.isFrozen(s.state.command.body));
  await s.recover(false);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');
  await s.recover(true,async(url,init)=>{calls++;assert.equal(url,'/auth/changeover-correction-receipt');assert.equal(init.body,JSON.stringify(s.state.command));assert.equal(init.credentials,'same-origin');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');return Response.json(f.receipt(s.state.command));});
  assert.equal(s.state.phase,'confirmed');await s.recover(true,async()=>calls++);assert.equal(calls,1);
 }finally{globalThis.fetch=old;}
});
test('lost original response survives export refresh and current session refusal without changing bytes',async()=>{
 const original=new t.ChangeoverCorrectionSubmission(t.confirmChangeoverCorrection(f.command(),true));let bytes;
 await original.send(true,async(_url,init)=>{bytes=init.body;throw Error('lost');});assert.equal(original.state.phase,'unknown');
 const s=r.importChangeoverCorrectionRecovery(r.exportChangeoverCorrectionRecovery(original.state.review,origin),origin);
 for(const [status,error]of [[401,'session_required'],[403,'submission_forbidden'],[404,'target_not_found'],[502,'outcome_unknown']]){
  await s.recover(true,async(url,init)=>{assert.equal(url,'/auth/changeover-correction-receipt');assert.equal(init.body,bytes);return Response.json({error},{status});});assert.equal(s.state.phase,'unknown');
 }
 await s.recover(true,async(_url,init)=>{assert.equal(init.body,bytes);return Response.json(f.receipt(JSON.parse(bytes)));});assert.equal(s.state.phase,'confirmed');
});
test('only exact receipt confirms; wrong target body head status or malformed response stays unknown',async()=>{
 const c=t.parseChangeoverCorrectionCommand(f.command());const bad=[];
 for(const mutate of [d=>d.target.changeover_no='OTHER',d=>d.request_id=f.principal,d=>d.result.revision++,d=>d.result.note='OTHER',d=>d.result.to_release_id=f.key,d=>d.audit_event_no='OTHER']){const d=copy(f.receipt(c));mutate(d);bad.push(()=>Response.json(d));}
 bad.push(()=>Response.json(f.receipt(c),{status:201}),()=>new Response('{'),()=>Response.json({pad:'x'.repeat(17000)}),()=>{throw Error('lost');});
 for(const reply of bad){const s=r.importChangeoverCorrectionRecovery(exportText(c),origin);await s.recover(true,reply);assert.equal(s.state.phase,'unknown');assert.equal(s.send,undefined);}
});
test('concurrent recovery calls share interlock and cannot become a business write',async()=>{
 const s=r.importChangeoverCorrectionRecovery(exportText(),origin);let calls=0,finish;
 const pending=s.recover(true,async(url)=>{calls++;assert.equal(url,'/auth/changeover-correction-receipt');return new Promise(resolve=>finish=resolve);});
 assert.equal(s.state.phase,'checking');await s.recover(true,async()=>calls++);assert.equal(calls,1);
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;assert.equal(s.state.phase,'unknown');
});
test('nullable original timestamp and required explicit replacement survive recovery without clock regeneration',async()=>{
 const raw=f.command();raw.context.changed_at=null;raw.body.changed_at='2026-01-02T00:00:00.123456Z';const text=exportText(raw),s=r.importChangeoverCorrectionRecovery(text,origin);
 assert.equal(s.state.command.context.changed_at,null);assert.equal(s.state.command.body.changed_at,raw.body.changed_at);
 for(const changed_at of [null,undefined,''])assert.throws(()=>exportText({...raw,body:{...raw.body,changed_at}}));
 for(const from_release_id of [null,undefined,raw.context.to_release_id])assert.throws(()=>exportText({...raw,body:{...raw.body,from_release_id}}));
 await s.recover(true,async(url,init)=>{assert.equal(url,'/auth/changeover-correction-receipt');assert.equal(JSON.parse(init.body).body.changed_at,raw.body.changed_at);return Response.json(f.receipt(s.state.command));});assert.equal(s.state.phase,'confirmed');
});
test('Batch and Changeover recovery envelopes cannot cross kinds in either direction',()=>{
 const batch=require(path.join(output,'batch-correction-recovery.js')),batchTransport=require(path.join(output,'batch-correction-transport.js')),bf=require('./fixtures/batch-correction.cjs');
 const batchText=batch.exportBatchCorrectionRecovery(batchTransport.confirmBatchCorrection(bf.command(),true),origin);
 assert.equal(r.parseChangeoverCorrectionRecovery(batchText,origin),null);assert.equal(batch.parseBatchCorrectionRecovery(exportText(),origin),null);
});
