const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-batch-recovery-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/batch-correction-recovery.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const r=require(path.join(output,'batch-correction-recovery.js')),t=require(path.join(output,'batch-correction-transport.js')),f=require('./fixtures/batch-correction.cjs');
const origin='https://lifecycle.example',exportText=(c=f.command())=>r.exportBatchCorrectionRecovery(t.confirmBatchCorrection(c,true),origin),copy=v=>JSON.parse(JSON.stringify(v));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
test('canonical compact and pretty exports preserve exact frozen command and all null semantics',()=>{
 const c=t.parseBatchCorrectionCommand(f.command()),text=exportText(c);
 assert.deepEqual(r.parseBatchCorrectionRecovery(text,origin),c);
 assert.deepEqual(r.parseBatchCorrectionRecovery(JSON.stringify(JSON.parse(text)),origin),c);
 const raw=f.command(),review=t.confirmBatchCorrection(raw,true);raw.body.note='changed after confirmation';
 assert.equal(r.exportBatchCorrectionRecovery(review,origin),text);
 assert.equal(r.parseBatchCorrectionRecovery(text,origin).body.started_at,null);
 assert.equal(r.parseBatchCorrectionRecovery(text,origin).body.note,null);
});
test('origin format version and every envelope boundary fail closed',()=>{
 const text=exportText();for(const mutate of [d=>d.format='slc-acceptance-correction-recovery',d=>d.version=2,d=>d.origin='https://other.example',d=>d.operation='batch',d=>d.actor_principal_id=f.principal,d=>d.token='secret',d=>d.proof='secret',d=>d.receipt={confirmed:true},d=>d.target.url='https://other.example',d=>d.context.actor_principal_id=f.principal,d=>d.body.token='secret',d=>delete d.context]){
  const value=JSON.parse(text);mutate(value);assert.equal(r.parseBatchCorrectionRecovery(JSON.stringify(value),origin),null);
 }
 assert.equal(r.parseBatchCorrectionRecovery(text,'https://other.example'),null);
 const other=r.exportBatchCorrectionRecovery(t.confirmBatchCorrection(f.command(),true),'https://other.example');assert.ok(r.parseBatchCorrectionRecovery(other,'https://other.example'));assert.equal(r.parseBatchCorrectionRecovery(other,origin),null);
 for(const invalid of ['https://lifecycle.example/','https://user:pass@lifecycle.example','http://lifecycle.example','null','file:///tmp']){
  assert.equal(r.parseBatchCorrectionRecovery(text,invalid),null);assert.throws(()=>r.exportBatchCorrectionRecovery(t.confirmBatchCorrection(f.command(),true),invalid));
 }
 for(const local of ['http://localhost','http://127.0.0.1:3000','http://[::1]:3000']){
  const value=r.exportBatchCorrectionRecovery(t.confirmBatchCorrection(f.command(),true),local);assert.ok(r.parseBatchCorrectionRecovery(value,local));
 }
});
test('duplicate keys reordered keys alternate whitespace and silent timestamp normalization rejected',()=>{
 const text=exportText(),compact=JSON.stringify(JSON.parse(text));
 for(const value of [compact.replace('"version":1','"version":1,"version":1'),compact.replace('"note":null','"note":null,"note":null'),text.replace('  "format"',' "format"'),compact.replace('2026-01-01T00:00:00.000000Z','2026-01-01T00:00:00+00:00'),JSON.stringify({...JSON.parse(text),body:{...JSON.parse(text).body,request_id:f.key.toUpperCase()}})])assert.equal(r.parseBatchCorrectionRecovery(value,origin),null);
 const d=JSON.parse(text),{format,...rest}=d;assert.equal(r.parseBatchCorrectionRecovery(JSON.stringify({...rest,format}),origin),null);
});
test('head mismatch invalid times target drift and oversized text never import',()=>{
 for(const mutate of [d=>d.body.expected_revision=1,d=>d.body.predecessor_id=f.key,d=>d.target.batch_no='OTHER',d=>d.context.started_at='invalid',d=>d.body.note='x'.repeat(8192)]){
  const d=JSON.parse(exportText());mutate(d);assert.throws(()=>r.importBatchCorrectionRecovery(JSON.stringify(d),origin));
 }
 for(const text of ['', '{', ' '.repeat(r.batchCorrectionRecoveryTextLimit+1),'中'.repeat(Math.ceil(r.batchCorrectionRecoveryTextLimit/3)+1)])assert.equal(r.parseBatchCorrectionRecovery(text,origin),null);
 assert.throws(()=>r.exportBatchCorrectionRecovery(t.confirmBatchCorrection(f.command(),false),origin));
 const review=t.confirmBatchCorrection(f.command(),true);assert.throws(()=>r.exportBatchCorrectionRecovery({...review,confirmed:'true'},origin));
 assert.throws(()=>r.exportBatchCorrectionRecovery({...review,command:{...review.command,token:'secret'}},origin));
});
test('import has zero network starts unknown and exposes only frozen audit recovery',async()=>{
 const old=globalThis.fetch;let calls=0;try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  const s=r.importBatchCorrectionRecovery(exportText(),origin);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');assert.equal(s.state.error,'outcome_unknown');
  assert.deepEqual(Object.keys(s),['state','recover']);assert.equal(s.send,undefined);assert.equal(s.retry,undefined);assert.ok(Object.isFrozen(s));assert.ok(Object.isFrozen(s.state.command.body));
  await s.recover(false);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');
  await s.recover(true,async(url,init)=>{calls++;assert.equal(url,'/auth/batch-correction-receipt');assert.equal(init.body,JSON.stringify(s.state.command));assert.equal(init.credentials,'same-origin');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');return Response.json(f.receipt(s.state.command));});
  assert.equal(s.state.phase,'confirmed');await s.recover(true,async()=>calls++);assert.equal(calls,1);
 }finally{globalThis.fetch=old;}
});
test('lost original response survives export refresh and current session refusal without changing bytes',async()=>{
 const original=new t.BatchCorrectionSubmission(t.confirmBatchCorrection(f.command(),true));let bytes;
 await original.send(true,async(_url,init)=>{bytes=init.body;throw Error('lost');});assert.equal(original.state.phase,'unknown');
 const s=r.importBatchCorrectionRecovery(r.exportBatchCorrectionRecovery(original.state.review,origin),origin);
 for(const [status,error]of [[401,'session_required'],[403,'submission_forbidden'],[404,'target_not_found'],[502,'outcome_unknown']]){
  await s.recover(true,async(url,init)=>{assert.equal(url,'/auth/batch-correction-receipt');assert.equal(init.body,bytes);return Response.json({error},{status});});assert.equal(s.state.phase,'unknown');
 }
 await s.recover(true,async(_url,init)=>{assert.equal(init.body,bytes);return Response.json(f.receipt(JSON.parse(bytes)));});assert.equal(s.state.phase,'confirmed');
});
test('only exact receipt confirms; wrong target body head status or malformed response stays unknown',async()=>{
 const c=t.parseBatchCorrectionCommand(f.command());const bad=[];
 for(const mutate of [d=>d.target.batch_no='OTHER',d=>d.request_id=f.principal,d=>d.result.revision++,d=>d.result.note='OTHER',d=>d.result.release_id=f.key,d=>d.audit_event_no='OTHER']){const d=copy(f.receipt(c));mutate(d);bad.push(()=>Response.json(d));}
 bad.push(()=>Response.json(f.receipt(c),{status:201}),()=>new Response('{'),()=>Response.json({pad:'x'.repeat(17000)}),()=>{throw Error('lost');});
 for(const reply of bad){const s=r.importBatchCorrectionRecovery(exportText(c),origin);await s.recover(true,reply);assert.equal(s.state.phase,'unknown');assert.equal(s.send,undefined);}
});
test('concurrent recovery calls share interlock and cannot become a business write',async()=>{
 const s=r.importBatchCorrectionRecovery(exportText(),origin);let calls=0,finish;
 const pending=s.recover(true,async(url)=>{calls++;assert.equal(url,'/auth/batch-correction-receipt');return new Promise(resolve=>finish=resolve);});
 assert.equal(s.state.phase,'checking');await s.recover(true,async()=>calls++);assert.equal(calls,1);
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;assert.equal(s.state.phase,'unknown');
});
