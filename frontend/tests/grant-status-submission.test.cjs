'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-grant-submit-'));
require('node:child_process').execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'),
 'lib/grant-status-submission.ts', 'components/grant-status-result.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop',
 '--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'), path.join(output, 'node_modules'), 'dir');
const { GrantSubmission, submissionMessages } = require(path.join(output,'lib/grant-status-submission.js'));
const { prepareGrantStatus, confirmGrantStatus, exportGrantStatus } = require(path.join(output,'lib/grant-status-draft.js'));
const React = require('react'), { renderToStaticMarkup } = require('react-dom/server');
const Result = require(path.join(output,'components/grant-status-result.js')).default;
const { LanguageProvider } = require(path.join(output,'components/localized.js'));
const dictionary = require('../lib/i18n/zh.json');
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id='12345678-1234-1234-1234-123456789abc', principalId='23456789-1234-1234-1234-123456789abc';
const target={id,principalId,scope:'GLOBAL',role:'PLATFORM_ADMIN',status:'ACTIVE',historyStatus:'ACTIVE'};
function reviewed(change={},key='ADM-ORIGINAL') {
 return confirmGrantStatus(prepareGrantStatus({...target,...change},key,'Controlled test reason'),true);
}
function receipt(review,extra={}) {
 return {grant_id:review.target.id,scope:review.target.scope,audit_event_no:review.request.body.event_no,
  applied_status:review.request.body.status,current_status:review.request.body.status,replayed:false,...extra};
}
const json=(value,options)=>Response.json(value,options);
test('unconfirmed and altered previews never create a transport controller',()=>{
 const review=prepareGrantStatus(target,'ADM-1','Controlled test reason');
 assert.throws(()=>new GrantSubmission(review),/Confirm/);
 assert.throws(()=>new GrantSubmission({...confirmGrantStatus(review,true),request:{...review.request,path:'/evil'}}),/invalid_review/);
});
test('default-disabled sending performs no network call',async()=>{
 const controller=new GrantSubmission(reviewed());let calls=0;
 const state=await controller.send(false,async()=>{calls++;});
 assert.equal(calls,0);assert.equal(state.phase,'rejected');assert.equal(state.error,'grant_submission_disabled');
});
for(const scope of ['GLOBAL','PROJECT','SOFTWARE']) for(const status of ['ACTIVE','SUSPENDED']) {
 test('reviewed command transport and receipt: '+scope+' '+status,async()=>{
  const review=reviewed({scope,status,historyStatus:status}),controller=new GrantSubmission(review);
  const state=await controller.send(true,async(url,init)=>{
   assert.equal(url,'/auth/grant-status');assert.equal(init.method,'POST');
   assert.equal(init.credentials,'same-origin');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');assert.ok(init.signal);
   assert.deepEqual(init.headers,{'Content-Type':'application/json',Accept:'application/json'});
   assert.deepEqual(JSON.parse(init.body),{scope,grant_id:id,...review.request.body});
   return json(receipt(review,{token:'upstream-secret',principal:{secret:true}}));
  });
  assert.equal(state.phase,'confirmed');assert.deepEqual(state.receipt,receipt(review));
  assert.ok(Object.isFrozen(state));assert.ok(Object.isFrozen(state.receipt));
 });
}
test('double clicks and a confirmed receipt never create another POST',async()=>{
 const review=reviewed(),controller=new GrantSubmission(review);let calls=0,finish;
 const fetcher=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
 const first=controller.send(true,fetcher);assert.equal(controller.state.phase,'sending');
 assert.equal((await controller.send(true,fetcher)).phase,'sending');assert.equal(calls,1);
 finish(json(receipt(review)));await first;
 assert.equal((await controller.send(true,fetcher)).phase,'confirmed');assert.equal(calls,1);
});
test('unknown outcome retains immutable exact request and retries only on explicit action',async()=>{
 const review=reviewed(),controller=new GrantSubmission(review),bodies=[];let calls=0;
 const fetcher=async(url,init)=>{
  calls++;bodies.push(init.body);if(calls===1)throw Error('connection lost after commit');
  return json(receipt(review,{replayed:true,current_status:'ACTIVE'}));
 };
 const first=await controller.send(true,fetcher);
 assert.equal(first.phase,'unknown');assert.equal(first.error,'outcome_unknown');assert.equal(calls,1);
 assert.equal(exportGrantStatus(first.review),exportGrantStatus(review));
 const next=await controller.send(true,fetcher);
 assert.equal(next.phase,'confirmed');assert.equal(next.receipt.replayed,true);
 assert.equal(next.receipt.applied_status,'SUSPENDED');assert.equal(next.receipt.current_status,'ACTIVE');
 assert.equal(bodies[0],bodies[1]);assert.equal(calls,2);
});
test('rejection after an uncertain POST never declares the earlier operation failed',async()=>{
 const review=reviewed(),controller=new GrantSubmission(review);let calls=0;
 const fetcher=async()=>{calls++;return calls===1?Response.json({error:'outcome_unknown'},{status:502}):
  Response.json({error:'submission_forbidden'},{status:403});};
 await controller.send(true,fetcher);const state=await controller.send(true,fetcher);
 assert.equal(state.phase,'unknown');assert.equal(state.error,'submission_forbidden');
 assert.equal(state.review.request.body.event_no,'ADM-ORIGINAL');assert.equal(calls,2);
 const disabled=await controller.send(false,fetcher);
 assert.equal(disabled.phase,'unknown');assert.equal(disabled.error,'grant_submission_disabled');assert.equal(calls,2);
 const confirmed=await controller.send(true,async()=>json(receipt(review,{replayed:true})));
 assert.equal(confirmed.phase,'confirmed');
});
test('first authoritative rejection is explicit and does not retry automatically',async()=>{
 for(const [status,error] of [[401,'session_required'],[403,'read_only_mode'],[404,'grant_not_found'],
  [409,'last_active_admin_protected'],[409,'audit_event_conflict'],[422,'invalid_request'],[503,'grant_submission_disabled']]){
  const controller=new GrantSubmission(reviewed());let calls=0;
  const state=await controller.send(true,async()=>{calls++;return Response.json({error},{status});});
  assert.equal(state.phase,'rejected');assert.equal(state.error,error);assert.equal(calls,1);
 }
});
test('invalid or mismatched receipts preserve uncertainty without leaking backend text',async()=>{
 const review=reviewed();
 const responses=[()=>new Response('secret body'),()=>new Response('{',{headers:{'Content-Type':'application/json'}}),
  ()=>json({padding:'x'.repeat(16385)}),()=>json(receipt(review,{grant_id:principalId})),
  ()=>json(receipt(review,{scope:'PROJECT'})),()=>json(receipt(review,{audit_event_no:'OTHER'})),
  ()=>json(receipt(review,{applied_status:'ACTIVE'})),()=>json(receipt(review,{current_status:'INVALID'})),
  ()=>json(receipt(review,{replayed:'true'})),()=>Response.json({error:'secret text'},{status:403}),
  ()=>Response.json({error:'invalid_request'},{status:500}),
  ()=>json(receipt(review),{headers:{'Content-Length':'16385'}})];
 for(const response of responses){
  let calls=0;const controller=new GrantSubmission(review);
  const state=await controller.send(true,async()=>{calls++;return response();});
  assert.equal(state.phase,'unknown');assert.equal(state.error,'outcome_unknown');assert.equal(state.receipt,null);assert.equal(calls,1);
 }
});
test('newly created controller cannot mutate an earlier unknown request',async()=>{
 const old=new GrantSubmission(reviewed());await old.send(true,async()=>{throw Error('lost');});
 const another=new GrantSubmission(reviewed({},'ADM-NEW'));
 assert.equal(old.state.review.request.body.event_no,'ADM-ORIGINAL');assert.equal(another.state.review.request.body.event_no,'ADM-NEW');
 assert.throws(()=>{old.state.review.request.body.reason='replacement';},TypeError);
});
test('result SSR localizes uncertainty, recovery denial, exact receipt and current-status distinction',async()=>{
 const review=reviewed(),controller=new GrantSubmission(review);
 await controller.send(true,async()=>{throw Error('lost');});
 await controller.send(true,async()=>Response.json({error:'session_required'},{status:401}));
 const render=(locale,state)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},
  React.createElement(Result,{state})));
 const unknownZh=render('zh',controller.state),unknownEn=render('en',controller.state);
 assert.ok(unknownZh.includes('结果未知'));assert.ok(unknownZh.includes('此前结果未知的操作可能已经提交'));
 assert.ok(unknownEn.includes('earlier uncertain operation may have committed'));
 assert.ok(unknownZh.includes('/account/grants/GLOBAL/'+id+'?offset=0'));
 const confirmed=await controller.send(true,async()=>json(receipt(review,{current_status:'ACTIVE',replayed:true})));
 const zh=render('zh',confirmed),en=render('en',confirmed);
 assert.ok(zh.includes('本次操作应用的状态'));assert.ok(zh.includes('回执中观察到的状态'));
 assert.ok(en.includes('Applied status for this operation'));assert.ok(en.includes('Status observed in the receipt'));
 assert.ok(zh.includes('ADM-ORIGINAL'));assert.ok(zh.includes('仅在内存中'));
});
test('every public submission error has a Chinese translation and no arbitrary error fallback',()=>{
 for(const message of Object.values(submissionMessages))assert.match(dictionary[message],/[\u4e00-\u9fff]/);
});
