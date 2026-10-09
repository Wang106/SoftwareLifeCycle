'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-recovery-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/business-recovery.ts',
 '--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
const {exportBusinessRecovery,parseBusinessRecovery,importBusinessRecovery,businessReview}=require(path.join(output,'business-recovery.js'));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const origin='https://lifecycle.example';
const groups=[['first',['snapshot','actual','batch']],['governance',['approval','decision']],['distribution',['delivery','distribution','authorization']],
 ['production',['test-release','deployment','changeover']],['evidence',['impact','acceptance']],['resource',['resource']]];
for(const [group,operations] of groups)for(const operation of operations){
 const f=require('./fixtures/'+group+'-command.cjs');
 test(operation+' canonical recovery export/import preserves original request and never sends',async()=>{
  const review=businessReview(f.command(operation)),text=exportBusinessRecovery(review,origin),command=parseBusinessRecovery(text,origin);
  assert.ok(command);assert.deepEqual(command.body,review.draft.payload);assert.equal(command.body.request_id,f.key);
  assert.ok(!text.includes('token'));assert.ok(!text.includes('receipt'));assert.ok(!text.includes('principal'));
  assert.deepEqual(parseBusinessRecovery(JSON.stringify(JSON.parse(text)),origin),command);
  const oldFetch=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};const imported=importBusinessRecovery(text,origin);
   assert.equal(calls,0);assert.equal(imported.state.phase,'unknown');assert.equal(imported.send,undefined);
   const expected='/auth/'+(group==='first'?'first':group)+'-command-receipt';
   await imported.recover(true,async(url,init)=>{calls++;assert.equal(url,expected);assert.equal(init.method,'POST');
    assert.equal(init.body,JSON.stringify(command));return Response.json(f.receipt(command));});
   assert.equal(imported.state.phase,'confirmed');assert.equal(calls,1);
   await imported.recover(true,async()=>{throw Error('terminal');});assert.equal(imported.state.phase,'confirmed');
  }finally{globalThis.fetch=oldFetch;}
 });
 test(operation+' missing/denied original audit cannot turn imported uncertainty into rejection',async()=>{
  const imported=importBusinessRecovery(exportBusinessRecovery(businessReview(f.command(operation)),origin),origin);
  await imported.recover(true,async()=>Response.json({error:'outcome_unknown'},{status:502}));
  assert.equal(imported.state.phase,'unknown');
  await imported.recover(true,async()=>Response.json({error:'session_required'},{status:401}));
  assert.equal(imported.state.phase,'unknown');assert.equal(imported.state.error,'session_required');
  await imported.recover(false,async()=>{throw Error('disabled must not fetch');});assert.equal(imported.state.phase,'unknown');
 });
}
test('strict origin, version, shape, canonical body and duplicate JSON keys are rejected',()=>{
 const f=require('./fixtures/evidence-command.cjs'),review=businessReview(f.command('impact')),text=exportBusinessRecovery(review,origin);
 const mutations=[d=>d.version=2,d=>d.origin='https://another.example',d=>d.token='secret',d=>d.receipt={confirmed:true},
  d=>d.operation='admin',d=>d.body.request_id='invalid',d=>d.body.reason+=' ',d=>d.body.release_id=d.body.release_id.toUpperCase(),
  d=>d.body.actor_name='x'+String.fromCharCode(0xD800),d=>d.target+=' ',d=>d.body={...d.body,url:'https://evil.example'},
  d=>d.body=Object.fromEntries(Object.entries(d.body).reverse())];
 for(const mutate of mutations){const d=JSON.parse(text);mutate(d);assert.equal(parseBusinessRecovery(JSON.stringify(d,null,2),origin),null);}
 assert.equal(parseBusinessRecovery(text.replace('"version": 1','"version": 2, "version": 1'),origin),null);
 assert.equal(parseBusinessRecovery(text.replace('"request_id":','"request_id": "other", "request_id":'),origin),null);
 assert.equal(parseBusinessRecovery('null',origin),null);assert.equal(parseBusinessRecovery(text,'http://remote.example'),null);
 assert.equal(parseBusinessRecovery(text,origin+'/'),null);assert.equal(parseBusinessRecovery(' '.repeat(32769),origin),null);
 assert.throws(()=>exportBusinessRecovery({...review,confirmed:false},origin));
 assert.throws(()=>exportBusinessRecovery({...review,draft:{...review.draft,audit:'/activity/forged'}},origin));
});
test('query lock is synchronous and lost streams do not prove absence',async()=>{
 const f=require('./fixtures/resource-command.cjs'),text=exportBusinessRecovery(businessReview(f.command()),origin),c=importBusinessRecovery(text,origin);let finish,calls=0;
 const fetcher=async()=>{calls++;return new Promise(resolve=>finish=resolve);};
 const pending=c.recover(true,fetcher);await c.recover(true,fetcher);assert.equal(calls,1);assert.equal(c.state.phase,'checking');
 finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;assert.equal(c.state.phase,'unknown');
});
