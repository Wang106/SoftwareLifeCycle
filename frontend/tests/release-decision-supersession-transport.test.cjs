'use strict';
const{test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),cp=require('node:child_process');
const out=fs.mkdtempSync(path.join(os.tmpdir(),'slc-release-decision-supersession-'));
cp.execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/release-decision-supersession-transport.ts','lib/release-decision-supersession-audit.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',out]);
after(()=>fs.rmSync(out,{recursive:true,force:true}));
const transport=require(path.join(out,'release-decision-supersession-transport.js')),
 audit=require(path.join(out,'release-decision-supersession-audit.js')),f=require('./fixtures/release-decision-supersession.cjs');
const{parseReleaseDecisionSupersessionCommand:parse,confirmReleaseDecisionSupersession:confirm,
 ReleaseDecisionSupersessionSubmission:Submission,projectReleaseDecisionSupersessionReceipt:project}=transport;
test('strict replacement binds a new approval to the exact current predecessor and frozen snapshot',()=>{
 const c=f.command();assert.deepEqual(parse(c),c);
 for(const mutate of [d=>d.operation='decision',d=>d.target+=' ',d=>d.body.request_id=d.body.request_id.toUpperCase(),
  d=>d.body.supersedes_id=f.approval,d=>d.predecessor.id=f.approval,d=>d.body.request_id=d.predecessor.id,
  d=>d.predecessor.release_id='bad',d=>d.body.correction_reason=' ',d=>d.extra=true]){
   const value=structuredClone(c);mutate(value);assert.equal(parse(value),null);
 }
});
test('receipt and atomic audit prove the original replacement without current-state inference',()=>{
 const c=f.command();assert.deepEqual(project(f.receipt(c),c),f.receipt(c));
 assert.deepEqual(audit.projectReleaseDecisionSupersessionAudit(f.audit(c),c,f.principal),f.receipt(c));
 for(const mutate of [e=>e.action='DECISION_RECORDED',e=>e.actor_principal_id=f.approval,e=>e.payload.snapshot_id=f.release,
  e=>e.payload.request.correction_reason='other',e=>e.payload.approval_no='APR-OTHER']){
   const event=f.audit(c);mutate(event);assert.equal(audit.projectReleaseDecisionSupersessionAudit(event,c,f.principal),null);
 }
});
test('lost response locks the original bytes and recovery only queries its audit',async()=>{
 const c=f.command(),submission=new Submission(confirm(c,true)),bodies=[];
 await submission.send(true,async(_url,init)=>{bodies.push(init.body);throw Error('lost');});
 assert.equal(submission.state.phase,'unknown');
 await submission.recover(true,async(url,init)=>{assert.equal(url,'/auth/release-decision-supersession-receipt');bodies.push(init.body);return Response.json(f.receipt(c));});
 assert.equal(submission.state.phase,'confirmed');assert.equal(new Set(bodies).size,1);
});
test('disabled and rejected attempts cannot erase an uncertain original outcome',async()=>{
 const submission=new Submission(confirm(f.command(),true));await submission.send(true,async()=>{throw Error('lost');});
 await submission.send(false);assert.equal(submission.state.phase,'unknown');
 for(const[status,error]of [[403,'submission_forbidden'],[409,'submission_conflict'],[503,'release_decision_supersession_disabled']]){
  await submission.send(true,async()=>Response.json({error},{status}));assert.equal(submission.state.phase,'unknown');
 }
});
