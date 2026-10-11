'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const code=ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
const i18n={exports:{}};new Function('require','module','exports',code)(n=>n.endsWith('zh.json')?dict:templates,i18n,i18n.exports);
const roles=['电子工程师','电子经理','系统工程师','研发总监'];
const summary={id:'approval-id',approval_no:'APR-DEMO',target_type:'RELEASE',target_id:'release-id',status:'PENDING',snapshot:null,release:null,binding_state:'VALID',step_total:4,action_total:1};
async function render({locale='en',status='PENDING',offset=0,total=4,items,next=null,foreign=false}={}){
 const calls=[];
 const steps=items||roles.map((role_name,i)=>({id:'step-'+i,step_order:i+1,role_name,approver_name:i===0?'Raw Reviewer':null,status:i===0?'APPROVED':i===1?'PENDING':'WAITING'}));
 const api=async url=>{calls.push(url);return url.endsWith('/summary')?{...summary,status}:url.includes('/steps?')?{approval_id:foreign?'foreign':summary.id,approval_no:summary.approval_no,limit:50,offset,total,next_offset:next,items:steps}:{approval_id:summary.id,approval_no:summary.approval_no,total:1,state_counts:{APPROVED:1},next_offset:null,items:[{id:'action-raw',actor_name:'Raw Reviewer',action:'APPROVED',comment:'Original evidence unchanged',created_at:'2026-10-11T08:01:00Z',context_consistent:true,step:{role_name:roles[0],step_order:1},step_id:'step-0'}]};};
 const compiled=ts.transpileModule(fs.readFileSync('app/approvals/[id]/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};
 const translate=c=>typeof c==='string'?i18n.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:api}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children)),LocalizedAttributes:({children})=>children}:require(n);
 new Function('require','module','exports',compiled)(req,module,module.exports);
 return {html:renderToStaticMarkup(await module.exports.default({params:Promise.resolve({id:summary.approval_no}),searchParams:Promise.resolve(offset?{step_offset:String(offset)}:{})})),calls};
}
for(const locale of ['en','zh'])test('four-stage approval progress is bilingual and preserves original evidence: '+locale,async()=>{
 const {html,calls}=await render({locale});
 assert.equal(calls.length,3);
 assert.ok(html.includes(locale==='en'?'Electronics Engineer':'电子工程师'));
 assert.ok(html.includes(locale==='en'?'Current stage':'当前节点'));
 assert.ok(html.includes('aria-current="step"')&&html.includes('Raw Reviewer')&&html.includes('Original evidence unchanged')&&html.includes('2026-10-11T08:01:00Z'));
 assert.ok(html.includes(locale==='en'?'All stages approved does not mean formally released':'全部节点通过不等于正式发布'));
});
for(const status of ['APPROVED','RETURNED','REJECTED','CANCELLED'])test('closed '+status+' never has an active stage',async()=>{
 const {html}=await render({status});assert.ok(!html.includes('aria-current="step"'));
 assert.ok(html.includes('This approval request is closed.')&&html.includes('Not reached'));
 assert.ok(!/href="[^"]*operation=approval/.test(html));
});
test('partial window never invents overall progress or active stage',async()=>{
 const {html}=await render({offset:2,total:4,items:[{id:'step-2',step_order:3,role_name:'系统工程师',status:'PENDING'}]});
 assert.ok(html.includes('overall progress and the current stage are unknown'));
 assert.ok(!html.includes('aria-current="step"')&&!html.includes('Approved stages'));
});
test('foreign page never enters progress cards',async()=>{
 const {html}=await render({foreign:true});assert.ok(!html.includes('approval-progress'));
 assert.ok(html.includes('Approval steps unavailable'));
});
test('application stages translate and arbitrary recorded role is preserved',async()=>{
 const items=['应用工程师','应用经理','系统工程师','项目经理'].map((role_name,i)=>({id:'asr-'+i,role_name,step_order:i+1,status:'WAITING'}));
 const {html}=await render({items});for(const r of ['Application Engineer','Application Manager','Systems Engineer','Project Manager'])assert.ok(html.includes(r));
 assert.ok(html.includes('No explicit pending stage is recorded.')&&!html.includes('aria-current="step"'));
 const other=await render({items:[{id:'x',role_name:'Raw custom role',step_order:1,status:'PENDING'}],total:1});assert.ok(other.html.includes('Raw custom role'));
});
test('a waiting predecessor prevents a later pending node being called current',async()=>{
 const items=roles.map((role_name,i)=>({id:'x-'+i,role_name,step_order:i+1,status:i===1?'PENDING':'WAITING'}));
 const {html}=await render({items});assert.ok(!html.includes('aria-current="step"'));
 assert.ok(html.includes('No explicit pending stage is recorded.'));
});
