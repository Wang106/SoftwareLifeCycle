'use strict';
const{test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),cp=require('node:child_process');
const out=fs.mkdtempSync(path.join(os.tmpdir(),'slc-release-chain-revocation-'));
cp.execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/release-chain-revocation-transport.ts','lib/release-chain-revocation-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',out]);
after(()=>fs.rmSync(out,{recursive:true,force:true}));
const transport=require(path.join(out,'release-chain-revocation-transport.js')),
  audit=require(path.join(out,'release-chain-revocation-audit.js')),f=require('./fixtures/release-chain-revocation.cjs');
const{parseReleaseChainRevocationCommand:parse,confirmReleaseChainRevocation:confirm,
  ReleaseChainRevocationSubmission:Submission,projectReleaseChainRevocationReceipt:project}=transport;

test('strict revocation command binds four kinds to their exact reviewed context',()=>{
  for(const kind of ['RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION']){
    const c=f.command(kind);assert.deepEqual(parse(c),c);
  }
  const c=f.command('RELEASE');
  for(const mutate of [d=>d.operation='revocation',d=>d.target_kind='BAD',d=>d.target_id=d.target_id.toUpperCase(),
    d=>d.body.request_id=d.body.request_id.toUpperCase(),d=>d.body.reason=' ',d=>d.body.expected_context.version=2,
    d=>d.body.expected_context.release_id='bad',d=>d.body.expected_context.delivery_package_id=f.delivery,
    d=>d.body.expected_context.release_id=f.release.toUpperCase(),d=>d.extra=true]){
    const value=structuredClone(c);mutate(value);assert.equal(parse(value),null);
  }
});
test('depth forces the target node identity and rejects wrong nullability',()=>{
  // RELEASE depth 0: package/distribution/authorization must be null and release_id === target_id.
  assert.equal(parse(f.command('RELEASE',f.release))===null,false);
  assert.equal(parse(f.command('RELEASE',f.delivery)),null);
  // DELIVERY_PACKAGE depth 1: package required, distribution/authorization null.
  const d=f.command('DELIVERY_PACKAGE',f.delivery);
  assert.equal(parse(d)===null,false);
  const wrong=structuredClone(d);wrong.body.expected_context.distribution_id=f.distribution;assert.equal(parse(wrong),null);
  // AUTHORIZATION depth 3: all three nodes required.
  assert.equal(parse(f.command('AUTHORIZATION',f.authorization))===null,false);
});
test('receipt and atomic audit prove the original revocation without current-state inference',()=>{
  for(const kind of ['RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION']){
    const c=f.command(kind);assert.deepEqual(project(f.receipt(c),c),f.receipt(c));
    assert.deepEqual(audit.projectReleaseChainRevocationAudit(f.audit(c),c,f.principal),f.receipt(c));
  }
  const c=f.command('AUTHORIZATION');
  for(const mutate of [e=>e.action='AUTHORIZATION_RECORDED',e=>e.actor_principal_id=f.release,e=>e.payload.snapshot_id=f.release,
    e=>e.payload.request.reason='other',e=>e.payload.review_context.snapshot_id=f.release,e=>e.entity_type='RELEASE',
    e=>e.payload.protocol_version=2,e=>e.declared_actor_name='Someone']){
    const event=f.audit(c);mutate(event);assert.equal(audit.projectReleaseChainRevocationAudit(event,c,f.principal),null);
  }
});
test('lost response locks the original bytes and recovery only queries its audit',async()=>{
  const c=f.command('DISTRIBUTION'),submission=new Submission(confirm(c,true)),bodies=[];
  await submission.send(true,async(_url,init)=>{bodies.push(init.body);throw Error('lost');});
  assert.equal(submission.state.phase,'unknown');
  await submission.recover(true,async(url,init)=>{assert.equal(url,'/auth/release-chain-revocation-receipt');bodies.push(init.body);return Response.json(f.receipt(c));});
  assert.equal(submission.state.phase,'confirmed');assert.equal(new Set(bodies).size,1);
});
test('an uncertain outcome blocks a second submit and only recovery may run',async()=>{
  // Regression: the first send that loses its response must lock the exact request so a
  // second send can never POST the business proxy again (transport contract, not UI guard).
  const c=f.command('DISTRIBUTION'),submission=new Submission(confirm(c,true));let posts=0,recovers=0;
  await submission.send(true,async()=>{posts++;throw Error('lost');});
  assert.equal(submission.state.phase,'unknown');assert.equal(posts,1);
  // A second submit, even with the switch enabled, must not reach the proxy.
  await submission.send(true,async()=>{posts++;return Response.json(f.receipt(c));});
  assert.equal(posts,1);assert.equal(submission.state.phase,'unknown');
  // Only an explicit audit-only recovery may query.
  await submission.recover(true,async(url)=>{assert.equal(url,'/auth/release-chain-revocation-receipt');recovers++;return Response.json(f.receipt(c));});
  assert.equal(recovers,1);assert.equal(submission.state.phase,'confirmed');
});
test('disabled and rejected attempts cannot erase an uncertain original outcome',async()=>{
  const submission=new Submission(confirm(f.command('RELEASE'),true));await submission.send(true,async()=>{throw Error('lost');});
  await submission.send(false);assert.equal(submission.state.phase,'unknown');
  // A rejected denial after the outcome became uncertain must not downgrade it to rejected.
  const rejected=new Submission(confirm(f.command('RELEASE'),true));let first=true;
  for(const[status,error]of [[403,'submission_forbidden'],[409,'submission_conflict'],[503,'release_chain_revocation_disabled']]){
    await rejected.send(true,async()=>{if(first){first=false;throw Error('lost');}return Response.json({error},{status});});
    assert.equal(rejected.state.phase,'unknown');
  }
});
