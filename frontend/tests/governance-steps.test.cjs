'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const aid='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222';
const summary={id:aid,approval_no:'APR RAW',target_type:'RELEASE',target_id:aid,status:'PENDING',snapshot:null,release:null,binding_state:'MISMATCH',step_total:205,action_total:3};
async function render(search={},overrides={}){
 const calls=[];const api=async path=>{calls.push(path);if(path.endsWith('/summary'))return 'summary' in overrides?overrides.summary:summary;
 const q=new URL(path,'https://test.invalid').searchParams;
 if(path.includes('/steps?'))return 'steps' in overrides?overrides.steps:{approval_id:aid,approval_no:summary.approval_no,limit:Number(q.get('limit')||50),offset:Number(q.get('offset')||0),total:205,next_offset:202,items:[{id:sid,step_order:201,role_name:'Visible Role',approver_name:null,status:'PENDING'}]};
 return 'history' in overrides?overrides.history:{approval_id:aid,approval_no:summary.approval_no,total:3,state_counts:{APPROVED:3},next_offset:2,items:[]};};
 const code=ts.transpileModule(fs.readFileSync('app/approvals/[id]/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,module={exports:{}};
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:api}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,children),LocalizedAttributes:({children})=>children}:require(n);
 new Function('require','module','exports',code)(req,module,module.exports);
 const html=renderToStaticMarkup(await module.exports.default({params:Promise.resolve({id:summary.approval_no}),searchParams:Promise.resolve(search)}));
 return {html,calls,links:[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'))};
}
test('scalar summary first; owned steps/actions preserve independent cursors and exact command step',async()=>{
 const r=await render({step_limit:'1',step_offset:'201',limit:'1',offset:'1',action:'APPROVED'});
 assert.equal(r.calls.length,3);assert.ok(r.calls[0].endsWith('/summary')&&r.calls[1].includes('approval_id='+aid)&&r.calls[2].includes('approval_id='+aid));
 assert.ok(r.html.includes('205')&&r.html.includes('Visible Role')&&!r.html.includes('Only the first 200'));
 const links=r.links.filter(u=>u.startsWith('/approvals/')).map(u=>new URL(u,'https://test.invalid').searchParams);
 assert.ok(links.some(q=>q.get('step_offset')==='202'&&q.get('offset')==='1'&&q.get('action')==='APPROVED'));
 assert.ok(links.some(q=>q.get('offset')==='2'&&q.get('step_offset')==='201'&&q.get('step_approval_id')===aid));
 assert.ok(r.links.some(u=>u.startsWith('/commands?')&&new URL(u,'https://test.invalid').searchParams.get('step')===sid));
});
for(const field of ['approval_id','approval_no','limit','offset'])test('mismatched step '+field+' fails closed without hiding action history',async()=>{
 const steps={approval_id:aid,approval_no:summary.approval_no,limit:50,offset:0,total:205,next_offset:null,items:[{id:sid,role_name:'FOREIGN',status:'PENDING'}],[field]:'foreign'};
 const r=await render({}, {steps});assert.ok(r.html.includes('Approval steps unavailable')&&!r.html.includes('FOREIGN')&&r.html.includes('3 matching actions'));assert.ok(!r.links.some(u=>u.includes('step='+sid)));
});
test('foreign action parent is unavailable while steps still render',async()=>{
 const r=await render({}, {history:{approval_id:'foreign',approval_no:summary.approval_no}});assert.ok(r.html.includes('Visible Role')&&r.html.includes('Action history API unavailable'));
});
test('invalid duplicate cursors passed as invalid; end window retains total and first-page link',async()=>{
 const r=await render({step_limit:['1','2'],step_offset:['1','2'],offset:['1','2']},{steps:null,history:null});assert.ok(r.calls[1].includes('limit=invalid')&&r.calls[1].includes('offset=invalid')&&r.calls[2].includes('offset=invalid'));
 const empty=await render({}, {steps:{approval_id:aid,approval_no:summary.approval_no,limit:50,offset:0,total:205,next_offset:null,items:[]}});assert.ok(empty.html.includes('205')&&empty.html.includes('No steps recorded.')&&empty.html.includes('First page'));
});
test('wrong summary/stale parent stops child reads; no substitute step',async()=>{
 for(const [extra,search] of [[{summary:{...summary,approval_no:'foreign'}},{}],[{}, {step_approval_id:'foreign'}]]){const r=await render(search,extra);assert.equal(r.calls.length,1);assert.ok(r.html.includes('Approval unavailable'));}
});
