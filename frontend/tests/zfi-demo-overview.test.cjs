'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const translated={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(n=>n.endsWith('zh.json')?dict:templates,translated,translated.exports);
const row={source_ref:'ASR01',release_id:'customer-kubo-uuid',version:'v3.8.1.1',release_type:'APPLICATION',product:'cBMS-24x',customer:'KUBO',project_code:'1',record_status:'DRAFT',approval_no:'APR-ZFI-ASR01',approval_status:'APPROVED',approval_progress:{approved_steps:4,total_steps:4,current_step_order:null,current_role:null,closed:true},source_release_date:null,supplied_artifacts:0,supplied_test_evidence:0};
const receipt={sample_only:true,initialized:true,import_event_no:'EVT-ZFI-IMPORT-V1',synthetic_approvals:true,approval_routes:{STANDARD:['电子工程师','电子经理','系统工程师','研发总监'],APPLICATION:['应用工程师','应用经理','系统工程师','项目经理']},items:[row,{...row,source_ref:'ASR02',release_id:'customer-vol-uuid',customer:'VOL',project_code:'11',approval_no:'APR-ZFI-ASR02',approval_status:'REJECTED',approval_progress:{approved_steps:1,total_steps:4,current_step_order:null,current_role:null,closed:true}},{...row,source_ref:'SSR01',release_id:'standard-uuid',release_type:'STANDARD',version:'v3.8.1',customer:null,project_code:null,source_release_date:'2026-01-01',approval_no:'APR-ZFI-SSR01',approval_status:'PENDING',approval_progress:{approved_steps:1,total_steps:4,current_step_order:2,current_role:'电子经理',closed:false}}]};
async function render(data,locale='en'){
 const compiled=ts.transpileModule(fs.readFileSync('app/demo/zfi/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}},calls=[];
 const translate=c=>typeof c==='string'?translated.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);return data;}}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
 new Function('require','module','exports',compiled)(req,m,m.exports);
 return {html:renderToStaticMarkup(await m.exports.default()),calls};
}
for(const locale of ['en','zh'])test('actual imported identities, dates and read-only disclaimer in '+locale,async()=>{
 const {html,calls}=await render(receipt,locale);
 assert.deepEqual(calls,['/api/v1/demo/zfi-import']);
 assert.ok(html.includes(locale==='en'?'Excel demonstration overview':'Excel 演示总览'));
 assert.ok(html.includes(locale==='en'?'not current release readiness':'不代表当前发布就绪'));
 assert.ok(html.includes(locale==='en'?'Source dates are Excel metadata':'原发布日期为 Excel 元数据'));
 assert.ok(html.includes('/releases/application/customer-kubo-uuid')&&html.includes('/releases/application/customer-vol-uuid'));
 assert.ok(html.includes('/releases/standard/standard-uuid')&&html.includes('/approvals/APR-ZFI-ASR01'));
 assert.equal((html.match(/>v3\.8\.1\.1<\/a>/g)||[]).length,2);
 assert.ok(html.includes('KUBO')&&html.includes('VOL')&&html.includes('2026-01-01')&&html.includes('EVT-ZFI-IMPORT-V1'));
 assert.ok(html.includes(locale==='en'?'SSR / ASR approval routes':'SSR / ASR 审批路线'));
 for(const role of locale==='en'?['Electronics Engineer','Electronics Manager','Systems Engineer','R&amp;D Director','Application Engineer','Application Manager','Project Manager']:['电子工程师','电子经理','系统工程师','研发总监','应用工程师','应用经理','项目经理'])assert.ok(html.includes(role),role);
 assert.ok(html.includes(locale==='en'?'Current stage: 2 · Electronics Manager':'当前节点: 2 · 电子经理'));
 assert.ok(html.includes(locale==='en'?'Closed result: REJECTED':'关闭结果: 已拒绝'));
 assert.ok(html.includes('SSR: 1')&&html.includes('ASR: 2')&&!html.includes('operation=')&&!html.includes('/api/commands'));
 assert.equal((html.match(/<form\b/g)||[]).length,1);
 assert.match(html,/<form(?=[^>]*action="\/demo\/zfi")(?=[^>]*method="get")(?=[^>]*role="search")[^>]*>/);
 assert.ok(!html.includes('method="post"'));
});
for(const [name,data,expected] of [['unavailable',null,'Excel import API unavailable'],['foreign',{...receipt,sample_only:false},'Excel import API unavailable'],['partial',{...receipt,initialized:false},'Excel sample family incomplete or not installed'],['malformed',{...receipt,items:null},'Excel import API unavailable']])test(name+' must not present an imported family',async()=>{
 const {html}=await render(data);assert.ok(html.includes(expected)&&!html.includes('/approvals/APR-ZFI-ASR01')&&!html.includes('SSR: 1'));
});
test('status counts use current API rows without original seeded counts',async()=>{
 const {html}=await render({...receipt,items:[{...row,approval_status:'RETURNED',approval_no:null}]});
 assert.ok(html.includes('APPROVED: 0')&&html.includes('RETURNED: 1')&&!html.includes('/approvals/'));
});
