'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function contract(){return JSON.parse(fs.readFileSync('lib/demo-family-identities.json','utf8'));}
function load(){
 const m={exports:{}};
 const source=ts.transpileModule(fs.readFileSync('lib/demo-status.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,esModuleInterop:true,resolveJsonModule:true}}).outputText;
 new Function('require','module','exports',source)(n=>n.endsWith('demo-family-identities.json')?contract():require(n),m,m.exports);
 return m.exports.inspectDemoStatus;
}
function fixtures(){
 const expected=contract();
 return {
  health:{status:'ready',version:expected.api_version,database_revision:expected.database_revision},
  excel:{sample_only:true,initialized:true,synthetic_approvals:true,import_event_no:'EVT-ZFI-IMPORT-V1',
   items:Object.entries(expected.excel).map(([ref,id])=>({source_ref:ref,release_id:id,release_type:ref.startsWith('SSR')?'STANDARD':'APPLICATION',approval_no:'APR-ZFI-'+ref}))},
  evidence:{sample_only:true,initialized:true,items:Object.entries(expected.evidence).map(([version,release_id])=>({version,release_id,release_type:version.includes('-SSR-')?'STANDARD':'APPLICATION'}))}
 };
}
function freeze(x){if(x&&typeof x==='object'){Object.values(x).forEach(freeze);Object.freeze(x);}return x;}
test('three exact fixed families confirm data only and preserve every input',()=>{
 const data=freeze(fixtures()),before=JSON.stringify(data),result=load()(data.health,data.excel,data.evidence);
 assert.equal(result.allConfirmed,true);assert.equal(result.api.state,'confirmed');assert.equal(result.excel.state,'confirmed');assert.equal(result.evidence.state,'confirmed');
 assert.equal(result.excel.records,20);assert.equal(result.excel.standard,4);assert.equal(result.excel.application,16);assert.equal(result.evidence.records,3);
 assert.equal(JSON.stringify(data),before);assert.equal(Object.hasOwn(result,'formallyReleased'),false);
});
test('expected health contract matches actual backend declarations',()=>{
 const expected=contract();
 assert.equal(fs.readFileSync('../backend/app/main.py','utf8').match(/APP_VERSION = "([^"]+)"/)[1],expected.api_version);
 assert.equal(fs.readFileSync('../backend/app/core/config.py','utf8').match(/required_db_revision: str = "([^"]+)"/)[1],expected.database_revision);
});
test('fixed identities match the backend UUID namespaces and sample versions',()=>{
 const expected=contract(),crypto=require('node:crypto');
 const namespace=Buffer.from('6ba7b8119dad11d180b400c04fd430c8','hex');
 function id(name){
  const bytes=crypto.createHash('sha1').update(namespace).update(name).digest().subarray(0,16);
  bytes[6]=(bytes[6]&15)|80;bytes[8]=(bytes[8]&63)|128;
  const hex=bytes.toString('hex');return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
 }
 const excel=fs.readFileSync('../backend/app/seed_zfi_demo.py','utf8'),evidence=fs.readFileSync('../backend/app/seed_release_evidence.py','utf8');
 assert.ok(excel.includes("'softwarelifecycle/zfi-excel-demo/v1/' + name"));
 assert.ok(evidence.includes("'softwarelifecycle/release-evidence/v1/' + name"));
 for(const [ref,value] of Object.entries(expected.excel))assert.equal(value,id('softwarelifecycle/zfi-excel-demo/v1/'+ref));
 for(const [version,value] of Object.entries(expected.evidence)){
  assert.equal(value,id('softwarelifecycle/release-evidence/v1/'+version));
  assert.ok(evidence.match(/^VERSIONS = .+$/m)[0].includes("'"+version+"'"));
 }
});
for(const [name,override,state] of [
 ['old API',{version:'0.18.42'},'mismatch'],['old schema',{database_revision:'0023_impact_withdrawal_history'},'mismatch'],
 ['not ready',{status:'not_ready'},'incomplete'],['missing version',{version:undefined},'invalid'],
 ['missing schema',{database_revision:undefined},'invalid'],['unexpected status',{status:'ok'},'invalid'],
 ['array status',{status:['ready']},'invalid'],['object status',{status:{toString:null}},'invalid'],
 ['oversized version',{version:'1'.repeat(100)+'.2.3'},'invalid'],['nested schema',{database_revision:{value:'0024_release_customer_scope'}},'invalid']
])test('health refuses '+name,()=>{
 const d=fixtures(),r=load()({...d.health,...override},d.excel,d.evidence);
 assert.equal(r.api.state,state);assert.equal(r.allConfirmed,false);assert.equal(r.excel.state,'confirmed');
});
test('null, primitive and array responses do not establish health or sample success',()=>{
 const inspect=load();
 for(const value of [null,undefined,false,'ready',[],123]){
  const r=inspect(value,value,value);assert.equal(r.allConfirmed,false);
  const state=value==null?'unavailable':'invalid';
  for(const key of ['api','excel','evidence'])assert.equal(r[key].state,state);
 }
});
test('partial and absent valid sample families stay incomplete even with healthy API',()=>{
 const d=fixtures(),r=load()(d.health,{...d.excel,initialized:false,items:d.excel.items.slice(0,4)},{...d.evidence,initialized:false,items:[]});
 assert.equal(r.allConfirmed,false);assert.equal(r.excel.state,'incomplete');assert.equal(r.excel.records,4);assert.equal(r.evidence.state,'incomplete');
 const absent=load()(d.health,{sample_only:true,initialized:false,items:[]},{sample_only:true,initialized:false,items:[]});
 assert.equal(absent.excel.state,'incomplete');assert.equal(absent.evidence.state,'incomplete');
});
for(const [name,mutate] of [
 ['foreign flag',d=>d.excel.sample_only=false],
 ['incomplete count marked initialized',d=>d.excel.items.pop()],
 ['duplicate exact identity',d=>d.excel.items[1]={...d.excel.items[0]}],
 ['foreign UUID with original reference',d=>d.excel.items[0].release_id='00000000-0000-0000-0000-000000000000'],
 ['wrong release type',d=>d.excel.items[0].release_type='APPLICATION'],
 ['wrong approval reference',d=>d.excel.items[0].approval_no='APR-OTHER'],
 ['missing synthetic marker',d=>delete d.excel.synthetic_approvals],
 ['wrong import marker',d=>d.excel.import_event_no='EVT-OTHER'],
 ['oversized family',d=>d.excel.items.push(d.excel.items[0])],
 ['missing initialized flag',d=>delete d.excel.initialized],
 ['malformed items',d=>d.excel.items={length:20}]
])test('Excel confirmation refuses '+name,()=>{
 const d=fixtures();mutate(d);const r=load()(d.health,d.excel,d.evidence);
 assert.equal(r.excel.state,'invalid');assert.equal(r.excel.records,null);assert.equal(r.allConfirmed,false);
});
for(const [name,mutate] of [
 ['foreign flag',d=>d.evidence.sample_only=false],
 ['missing exact member',d=>d.evidence.items.pop()],
 ['duplicate member',d=>d.evidence.items[1]={...d.evidence.items[0]}],
 ['foreign exact UUID',d=>d.evidence.items[0].release_id='00000000-0000-0000-0000-000000000000'],
 ['wrong stored version',d=>d.evidence.items[0].version='foreign'],
 ['wrong release type',d=>d.evidence.items[0].release_type='APPLICATION']
])test('independent synthetic evidence family refuses '+name,()=>{
 const d=fixtures();mutate(d);const r=load()(d.health,d.excel,d.evidence);
 assert.equal(r.evidence.state,'invalid');assert.equal(r.evidence.records,null);assert.equal(r.allConfirmed,false);
});
test('each endpoint state is independent and Excel data never substitutes for synthetic evidence',()=>{
 const d=fixtures(),r=load()(null,d.excel,d.excel);
 assert.equal(r.api.state,'unavailable');assert.equal(r.excel.state,'confirmed');assert.equal(r.evidence.state,'invalid');assert.equal(r.allConfirmed,false);
});
async function render(data,locale='en'){
 const translation={exports:{}};
 new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(
  n=>n.endsWith('zh.json')?require('../lib/i18n/zh.json'):require('../lib/i18n/templates.json'),translation,translation.exports);
 const m={exports:{}},calls=[],paths=['/health/ready','/api/v1/demo/zfi-import','/api/v1/demo/release-evidence'],values=[data.health,data.excel,data.evidence];
 const code=ts.transpileModule(fs.readFileSync('app/demo/status/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const translate=c=>typeof c==='string'?translation.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 new Function('require','module','exports',code)(n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):
  n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);assert.ok(paths.includes(p));return values[paths.indexOf(p)];}}:
  n.endsWith('/lib/demo-status')?{inspectDemoStatus:load()}:
  n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n),m,m.exports);
 const html=renderToStaticMarkup(await m.exports.default());
 return {html,calls,translation:translation.exports,dynamic:m.exports.dynamic};
}
for(const locale of ['zh','en'])test('status page uses only three fixed reads and labels data confirmation separately from browser/release acceptance: '+locale,async()=>{
 const {html,calls,translation,dynamic}=await render(fixtures(),locale);
 assert.deepEqual(calls,['/health/ready','/api/v1/demo/zfi-import','/api/v1/demo/release-evidence']);assert.equal(dynamic,'force-dynamic');
 for(const label of ['Demonstration status','Demonstration data checks confirmed','These data checks do not establish real browser acceptance, real personnel approval or a formal release.','API readiness is not release readiness.','Read again','Observed at (UTC)']){
  assert.ok(html.includes(translation.translateText(label,locale)),label);
  if(locale==='zh')assert.notEqual(translation.translateText(label,locale),label);
 }
 assert.ok(html.includes('0.18.44')&&html.includes('0025_release_decision_supersession'));
 assert.ok(html.includes('SSR: 4')&&html.includes('ASR: 16'));
 assert.match(html,/<time dateTime="\d{4}-\d{2}-\d{2}T[^"]+Z">/);
 assert.ok(html.includes('/demo/zfi')&&html.includes('/demo/releases')&&html.includes('href="/demo/status"'));
 assert.ok(!html.includes('<form')&&!html.includes('/auth/')&&!html.includes('operation=')&&!html.includes('API_BASE_URL'));
});
test('status page remains honest about independent failures and never fabricates a successful family',async()=>{
 const d=fixtures();d.health=null;d.excel={sample_only:true,initialized:false,items:[]};d.evidence.sample_only=false;
 const {html}=await render(d);
 assert.ok(html.includes('Demonstration data checks not confirmed')&&!html.includes('Demonstration data checks confirmed'));
 assert.ok(html.includes('Not confirmed: endpoint unavailable')&&html.includes('Not confirmed: not ready or incomplete')&&html.includes('Not confirmed: unexpected response'));
 assert.ok(!html.includes('SSR: 4')&&!html.includes('ASR: 16'));
});
