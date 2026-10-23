'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const code=ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
const i18n={exports:{}};new Function('require','module','exports',code)(n=>n.endsWith('zh.json')?dict:templates,i18n,i18n.exports);
const row={release_id:'exact-release',version:'DEMO-EVIDENCE-ASR-B-2.0',release_type:'APPLICATION',record_status:'DRAFT',snapshot:{id:'snapshot-2',snapshot_no:'SNAP-2',content_hash:'a'.repeat(64)},readiness:{overall:'NOT_READY',approval_eligible:false,coverage:{required_dvp_total:3,current_snapshot_executed:0,current_snapshot_passed:0,snapshot_match:false},rules:[{group:'Verification',rule:'Required DVP executed on current snapshot',effective:'FAIL',evidence:'0 / 3'}]},approval:{approval_no:'APR-2',status:'APPROVED',current_snapshot_bound:true},decision:{decision_no:'RD-2',decision:'HOLD',readiness_status:'NOT_READY',snapshot_id:'snapshot-2',current_evidence_bound:true},current_release_confirmed:false,change_request_no:'SCR-DEMO',dvp_items:[{id:'exact-item',item_no:'DVP-SOFTWARE'}]};
async function render(data,locale='en'){
 const compiled=ts.transpileModule(fs.readFileSync('app/demo/releases/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}},calls=[];
 const translate=c=>typeof c==='string'?i18n.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:async path=>{calls.push(path);return data;}}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
 new Function('require','module','exports',compiled)(req,module,module.exports);
 return {html:renderToStaticMarkup(await module.exports.default()),calls};
}
for(const locale of ['en','zh'])test('blocked approval evidence and exact links in '+locale,async()=>{
 const {html,calls}=await render({sample_only:true,initialized:true,items:[row]},locale);
 assert.deepEqual(calls,['/api/v1/demo/release-evidence']);
 assert.ok(html.includes(locale==='en'?'Current evidence does not confirm a formal release.':'当前证据不能确认正式发布。'));
 assert.ok(html.includes(locale==='en'?'Tests on an older snapshot':'旧快照上的测试'));
 assert.ok(html.includes('APR-2')&&html.includes('RD-2')&&html.includes('snapshot-2'));
 assert.ok(html.includes('/testing/dvp/exact-item?release_id=exact-release&amp;snapshot_no=SNAP-2'));
 assert.ok(html.includes('/releases/application/exact-release/passport'));
 assert.ok(!html.includes('<form')&&!html.includes('operation='));
});
test('positive SSR has exact decision and no application-only link',async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[{...row,release_type:'STANDARD',current_release_confirmed:true,decision:{...row.decision,decision:'RELEASE'}}]});
 assert.ok(html.includes('Formal release evidence matches the current snapshot.'));
 assert.ok(html.includes('/releases/standard/exact-release')&&!html.includes('/passport'));
});
for(const locale of ['en','zh'])test('unknown release type stays visible without an invented SSR or ASR route in '+locale,async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[{...row,release_type:'FUTURE'}]},locale);
 assert.ok(html.includes(i18n.exports.translateText('Unrecognized release type',locale)));
 assert.ok(html.includes(i18n.exports.translateText('Unknown values are not mapped to SSR or ASR.',locale)));
 assert.ok(html.includes('<code>FUTURE</code>'));
 assert.ok(!html.includes('/releases/application/exact-release'));
 assert.ok(!html.includes('/releases/standard/exact-release'));
 assert.ok(!html.includes('/releases/application/exact-release/readiness'));
 assert.ok(!html.includes('/releases/application/exact-release/passport'));
});
for(const [name,data,expected] of [['unavailable',null,'Evidence API unavailable'],['not installed',{sample_only:true,initialized:false,items:[row]},'Evidence samples not installed'],['foreign response',{sample_only:false,initialized:true,items:[row]},'Evidence API unavailable']])test(name+' never fabricates proof',async()=>{
 const {html}=await render(data);assert.ok(html.includes(expected)&&!html.includes('APR-2')&&!html.includes('RD-2'));
});
