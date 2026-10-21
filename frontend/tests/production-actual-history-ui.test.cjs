const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');const zh=require('../lib/i18n/zh.json');
function page(api,language='en'){
 const file=path.resolve('app/deployments/[id]/page.tsx');const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};new Function('require','module','exports',code)(name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/production'))return {};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,language==='zh'&&typeof children==='string'?(zh[children]??children):children),LocalizedAttributes:({children})=>children};
  return require(name);
 },m,m.exports);return m.exports.default;
}
const correction=index=>({id:'correction-'+index,revision:10001-index,actual:{release_id:'release',version:'3.8.'+index,snapshot_id:'snapshot',snapshot_no:'SNAP-'+index},correction_reason:'Original reason '+index,actor_name:'Original actor '+index,deployed_at:'2026-10-20T10:'+String(index).padStart(2,'0')+':00Z',recorded_at:'2026-10-20T11:'+String(index).padStart(2,'0')+':00Z',audit_event_no:'EVT-CORR-'+index});
const fixture={id:'dep-id',deployment_no:'DEP / 1',status:'MATCH',actual_version:10001,authorization:{id:'auth',authorization_no:'AUTH-1',status:'APPROVED'},customer:null,project:{id:'project',code:'P',name:'Original project'},site:{id:'site',site_code:'S',name:'Original site'},line:{id:'line',line_code:'L',name:'Original line'},expected:{release_id:'release',version:'3.8',snapshot_id:'snapshot',snapshot_no:'SNAP-BASE'},actual:{release_id:'release',version:'3.8.1',snapshot_id:'snapshot',snapshot_no:'SNAP-1'},deployed_at:'2026-10-20T10:00:00Z',software_observation:'MATCH',history_counts:{changeovers:2,batches:3},notice:'Original notice',provenance:{authorization:{authorization_no:'AUTH-1',status:'APPROVED'},distribution:{distribution_no:'DIST-1',status:'SENT'},delivery:{package_no:'DP-1',revision:1,status:'RELEASED',release_id:'release',snapshot_id:'snapshot'}},actual_history:{history_state:'CORRECTED',recorded_baseline:{source:'FIRST_REPORT',recorded_actual_version:1,actual:{release_id:'release',version:'3.8',snapshot_id:'snapshot',snapshot_no:'SNAP-BASE'},recorded_status:'MATCH',deployed_at:'2026-10-19T08:00:00Z',recorded_at:'2026-10-19T08:01:00Z'},correction_count:10000,corrections:Array.from({length:55},(_,i)=>correction(i+1))}};
async function render(profile=fixture,language='en'){const calls=[];const Page=page(async url=>{calls.push(url);return profile},language);return {calls,html:renderToStaticMarkup(await Page({params:Promise.resolve({id:'DEP / 1'})}))};}
test('actual history is bounded, latest-first, auditable and read-only',async()=>{
 const {calls,html}=await render();assert.deepEqual(calls,['/api/v1/deployments/DEP%20%2F%201/profile']);
 for(const value of ['Actual software history','Read-only append-only history','10000','Showing latest ','50','Revision ','10000','Original reason 1','Original actor 1','2026-10-20T10:01:00Z','2026-10-20T11:01:00Z','/activity/EVT-CORR-1','FIRST_REPORT','2026-10-19T08:00:00Z','2026-10-19T08:01:00Z'])assert.ok(html.includes(value),value);
 assert.ok(!html.includes('Original reason 51'));assert.ok(html.indexOf('Original reason 1')<html.indexOf('Original reason 50'));
 assert.ok(!html.includes('<form'));assert.ok(!html.includes('Send actual'));assert.ok(!html.includes('Correct actual'));
});
test('Chinese labels translate without changing ledger evidence',async()=>{
 const {html}=await render(fixture,'zh');
 for(const value of [zh['Actual software history'],zh['Occurrence time'],zh['Ledger recorded time'],zh['Correction reason'],'Original reason 1','Original actor 1','EVT-CORR-1'])assert.ok(html.includes(value),value);
});
test('missing history remains explicitly unknown and never invents a baseline',async()=>{
 const {html}=await render({...fixture,actual_history:undefined});
 assert.ok(html.includes('Actual history unavailable. No substitute history is shown.'));
 assert.ok(!html.includes('FIRST_REPORT'));assert.ok(!html.includes('EVT-CORR-1'));
});
