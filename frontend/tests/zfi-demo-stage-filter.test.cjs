'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const translation={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(
 n=>n.endsWith('zh.json')?require('../lib/i18n/zh.json'):require('../lib/i18n/templates.json'),translation,translation.exports);
const routes={STANDARD:['电子工程师','电子经理','系统工程师','研发总监'],APPLICATION:['应用工程师','应用经理','系统工程师','项目经理']};
function row(index=0,type='STANDARD',stage=1){return {
 source_ref:'REF-'+index,release_id:'release-'+index,version:'same-version',release_type:type,product:'Original Product',
 customer:type==='STANDARD'?null:'KUBO',project_code:type==='STANDARD'?null:'PROJECT-'+index,record_status:'DRAFT',
 approval_no:'APR-'+index,approval_status:'PENDING',source_release_date:null,supplied_artifacts:0,supplied_test_evidence:0,
 approval_progress:{approved_steps:stage-1,total_steps:4,current_step_order:stage,current_role:routes[type][stage-1],closed:false}
};}
const fixtureItems=[...routes.STANDARD.map((_,i)=>row(i,'STANDARD',i+1)),...routes.APPLICATION.map((_,i)=>row(i+4,'APPLICATION',i+1)),
 {...row(8),approval_status:'APPROVED',approval_progress:{approved_steps:4,total_steps:4,current_step_order:null,current_role:null,closed:true}},
 {...row(9),approval_progress:null}];
const receipt={sample_only:true,initialized:true,import_event_no:'EVT-STAGE',approval_routes:routes,items:fixtureItems};
function load(data=receipt,locale='en'){
 const m={exports:{}},calls=[];
 const code=ts.transpileModule(fs.readFileSync('app/demo/zfi/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const translate=c=>typeof c==='string'?translation.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 new Function('require','module','exports',code+'\nmodule.exports.stageHelpers = {parseRecordedStage, recordedApprovalStage, recordedRoutesMatch};')(n=>n==='next/link'?({href,children,...props})=>React.createElement('a',{href,...props},children):
  n.endsWith('/lib/api')?{apiGet:async (path,options)=>{calls.push({path,options});return data;}}:
  n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n),m,m.exports);
 return {...m.exports,calls};
}
async function render(query={},data=receipt,locale='en'){
 const m=load(data,locale);return {html:renderToStaticMarkup(await m.default({searchParams:Promise.resolve(query)})),calls:m.calls};
}
const helpers=()=>load().stageHelpers;
function rows(html){return [...html.matchAll(/href="\/releases\/(?:standard|application)\/(release-\d+)"/g)].map(m=>m[1]);}
function links(html){return [...html.matchAll(/<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/g)].map(m=>({href:m[1].replaceAll('&amp;','&'),label:m[2],params:new URL(m[1].replaceAll('&amp;','&'),'https://example.test').searchParams}));}
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
freeze(receipt);

test('only canonical single stage values are accepted; missing or empty means all',()=>{
 const {parseRecordedStage}=helpers();
 for(const stage of ['1','2','3','4','UNKNOWN'])assert.deepEqual(parseRecordedStage(stage),{stage,invalid:false});
 for(const value of [undefined,''])assert.deepEqual(parseRecordedStage(value),{stage:'',invalid:false});
 for(const value of ['0','5','01','1.0',' 1','1 ','unknown','CLOSED','PENDING','<script>',[],['1'],['1','2'],['UNKNOWN','UNKNOWN']])assert.deepEqual(parseRecordedStage(value),{stage:'',invalid:true},JSON.stringify(value));
});
for(const type of Object.keys(routes))test(type+' exact recorded role and ordinal map all four stages',()=>{
 const {recordedApprovalStage}=helpers();
 for(let stage=1;stage<=4;stage++)assert.equal(recordedApprovalStage(row(stage,type,stage)),String(stage));
});
test('recorded route contract requires both exact ordered SSR and ASR role lists',()=>{
 const {recordedRoutesMatch}=helpers();
 assert.equal(recordedRoutesMatch(routes),true);
 for(const value of [null,undefined,{},[],{STANDARD:routes.STANDARD},{APPLICATION:routes.APPLICATION},
  {...routes,STANDARD:[...routes.STANDARD].reverse()},
  {...routes,APPLICATION:[...routes.APPLICATION,'额外角色']},
  {...routes,STANDARD:[...routes.STANDARD.slice(0,3),'研发经理']},
  {...routes,APPLICATION:'应用工程师,应用经理,系统工程师,项目经理'}]){
  assert.equal(recordedRoutesMatch(value),false,JSON.stringify(value));
 }
});
test('route drift makes pending stages UNKNOWN without changing a consistent closed record',()=>{
 const {recordedApprovalStage}=helpers();
 assert.equal(recordedApprovalStage(row(0,'STANDARD',2),false),'UNKNOWN');
 assert.equal(recordedApprovalStage(row(1,'APPLICATION',4),false),'UNKNOWN');
 const closed={...row(2),approval_status:'APPROVED',approval_progress:{approved_steps:4,total_steps:4,current_step_order:null,current_role:null,closed:true}};
 assert.equal(recordedApprovalStage(closed,false),'CLOSED');
});
test('shared Systems Engineer stays stage 3 while stage 2 and 4 roles cannot cross release types',()=>{
 const {recordedApprovalStage}=helpers();
 for(const type of Object.keys(routes))for(const stage of [2,4]){
  const original=row(0,type,stage),other=type==='STANDARD'?'APPLICATION':'STANDARD';
  assert.equal(recordedApprovalStage({...original,approval_progress:{...original.approval_progress,current_role:routes[other][stage-1]}}),'UNKNOWN');
 }
 for(const type of Object.keys(routes))assert.equal(recordedApprovalStage(row(0,type,3)),'3');
});
test('missing, malformed, unsupported and ambiguous record evidence is UNKNOWN',()=>{
 const {recordedApprovalStage}=helpers(),base=row();
 for(const value of [null,undefined,{},[],0,'record',{...base,release_type:'OTHER'},{...base,approval_no:null},{...base,approval_no:''},
  {...base,approval_status:null},{...base,approval_status:'WAITING'},{...base,approval_status:'foreign'},{...base,approval_status:'pending'},
  {...base,approval_progress:null},{...base,approval_progress:undefined},{...base,approval_progress:[]},
  {...base,approval_progress:{}}])assert.equal(recordedApprovalStage(value),'UNKNOWN',JSON.stringify(value));
});
test('recorded stage fields reject noninteger, nonnumeric, out-of-range and nonboolean evidence',()=>{
 const {recordedApprovalStage}=helpers(),base=row();
 for(const [key,values] of Object.entries({approved_steps:[-1,5,0.5,'0',null,NaN,Infinity,true],total_steps:[0,3,5,'4',null,4.5],
  current_step_order:[null,0,5,1.5,'1',NaN,Infinity],current_role:[null,'','Electronics Engineer','电子经理',1],closed:[true,null,undefined,0,'false']})){
  for(const value of values)assert.equal(recordedApprovalStage({...base,approval_progress:{...base.approval_progress,[key]:value}}),'UNKNOWN',key+'='+value);
 }
});
test('closed records are excluded from both ordinal and UNKNOWN when consistent',()=>{
 const {recordedApprovalStage}=helpers(),base=row();
 for(const approval_status of ['APPROVED','RETURNED','REJECTED','CANCELLED']){
  const closed={...base,approval_status,approval_progress:{approved_steps:2,total_steps:4,current_step_order:null,current_role:null,closed:true}};
  assert.equal(recordedApprovalStage(closed),'CLOSED');
  for(const patch of [{closed:false},{current_step_order:1},{current_role:'电子工程师'},{total_steps:3},{approved_steps:-1}]){
   assert.equal(recordedApprovalStage({...closed,approval_progress:{...closed.approval_progress,...patch}}),'UNKNOWN');
  }
 }
});
test('approval counts, release status and versions never derive an unstated pending stage',()=>{
 const {recordedApprovalStage}=helpers(),base=row();
 for(const approved_steps of [0,1,2,3,4])for(const record_status of ['DRAFT','READY','RELEASED']){
  assert.equal(recordedApprovalStage({...base,record_status,approval_progress:{...base.approval_progress,approved_steps,current_step_order:null,current_role:null}}),'UNKNOWN');
 }
 // The projection cannot validate earlier step histories: use the explicit role and ordinal, not approved_steps + 1.
 for(const approved_steps of [0,1,2,3,4])assert.equal(recordedApprovalStage({...base,approval_progress:{...base.approval_progress,approved_steps}}),'1');
});
for(const stage of ['1','2','3','4'])test('actual page intersects recorded node across SSR and ASR: '+stage,async()=>{
 const {html,calls}=await render({stage});assert.deepEqual(rows(html),['release-'+(Number(stage)-1),'release-'+(Number(stage)+3)]);
 assert.ok(html.includes('SSR: 6')&&html.includes('ASR: 4')&&html.includes('APPROVED: 1')&&html.includes('PENDING: 9'));
 assert.deepEqual(calls,[{path:'/api/v1/demo/zfi-import',options:{timeoutMs:15000}}]);
 for(const id of rows(html))assert.ok(html.includes('/approvals/APR-'+id.replace('release-','')));
});
test('UNKNOWN includes unconfirmable records but not correctly closed approvals',async()=>{
 const {html}=await render({stage:'UNKNOWN'});assert.deepEqual(rows(html),['release-9']);
 assert.deepEqual(rows((await render({stage:'1',status:'APPROVED'})).html),[]);
 assert.deepEqual(rows((await render({status:'APPROVED'})).html),['release-8']);
});
test('node intersects type, customer, approval status and multiword literal search',async()=>{
 const {html}=await render({stage:'2',type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version PROJECT-5'});
 assert.deepEqual(rows(html),['release-5']);assert.ok(html.includes('Matched records: 1'));
 for(const patch of [{customer:'VOL'},{type:'STANDARD'},{status:'REJECTED'},{q:'PROJECT-7'}]){
  const {html}=await render({stage:'2',type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version PROJECT-5',...patch});
  assert.deepEqual(rows(html),[]);assert.ok(html.includes('No imported records match these filters.'));
 }
});
test('stage filtering precedes 10-row pagination and preserves original identity order',async()=>{
 const items=Array.from({length:36},(_,i)=>row(i,'APPLICATION',i%3===0?1:2)),data=freeze({...receipt,items});
 const expected=items.filter(r=>r.approval_progress.current_step_order===2).map(r=>r.release_id);
 const first=await render({stage:'2',type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version'},data);
 assert.deepEqual(rows(first.html),expected.slice(0,10));assert.ok(first.html.includes('Matched records: 24'));
 const next=links(first.html).find(a=>a.label==='Next page');assert.ok(next);
 assert.equal(next.params.get('stage'),'2');assert.equal(next.params.get('page'),'2');
 for(const [key,value] of Object.entries({type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version'}))assert.equal(next.params.get(key),value);
 const second=await render(Object.fromEntries(next.params),data);assert.deepEqual(rows(second.html),expected.slice(10,20));
 const last=await render({stage:'2',page:'999'},data);assert.deepEqual(rows(last.html),expected.slice(20));
 assert.ok(!links(last.html).some(a=>a.label==='Next page'));
});
test('filter links and GET search keep canonical node; changes and clear reset pagination',async()=>{
 const {html}=await render({stage:'2',type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version',page:'9'});
 const form=html.match(/<form\b[\s\S]*?<\/form>/)[0];assert.match(form,/method="get"/);
 assert.ok(form.includes('name="stage" value="2"'));assert.ok(!form.includes('name="page"'));
 for(const label of ['All release types','All customers','All approval statuses']){
  const link=links(html).find(a=>a.label===label);assert.ok(link,label);assert.equal(link.params.get('stage'),'2');assert.equal(link.params.has('page'),false);
 }
 const stage3=links(html).find(a=>a.params.get('stage')==='3');assert.ok(stage3);
 for(const [key,value] of Object.entries({type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version'}))assert.equal(stage3.params.get(key),value);
 assert.equal(stage3.params.has('page'),false);
 assert.ok(links(html).some(a=>a.label==='Clear filters'&&a.href==='/demo/zfi'));
});
test('invalid or duplicate stage preserves other filters, does not apply a stage, and never propagates invalid input',async()=>{
 const query={type:'APPLICATION',customer:'KUBO',status:'PENDING',q:'same-version'};
 const baseline=rows((await render(query)).html);
 for(const stage of ['invalid','0','5','01','<script>alert(1)</script>',['1','2'],['2']]){
  const {html,calls}=await render({...query,stage});assert.deepEqual(rows(html),baseline);
  assert.deepEqual(calls,[{path:'/api/v1/demo/zfi-import',options:{timeoutMs:15000}}]);
  assert.ok(!html.includes('<script>')&&!html.includes('alert(1)'));
  assert.ok(!html.match(/<input[^>]*name="stage"/));
  for(const link of links(html))if(link.params.has('stage'))assert.ok(['1','2','3','4','UNKNOWN'].includes(link.params.get('stage')));
 }
});
test('query and customer text remain escaped with stage and cannot introduce navigation parameters',async()=>{
 const product='A&B / 東京 <script>',data={...receipt,items:[{...row(0,'APPLICATION',2),customer:product,product}]};
 const {html}=await render({stage:'2',q:product,customer:product},data);assert.deepEqual(rows(html),['release-0']);
 assert.ok(html.includes('A&amp;B / 東京 &lt;script&gt;')&&!html.includes('<script>'));
 const stage3=links(html).find(a=>a.params.get('stage')==='3');assert.ok(stage3);
 assert.equal(stage3.params.get('q'),product);assert.equal(stage3.params.get('customer'),product);
 assert.deepEqual([...stage3.params.keys()].sort(),['customer','q','stage']);
});
for(const locale of ['en','zh'])test('unavailable and incomplete data remain distinct from empty filtered result: '+locale,async()=>{
 for(const [data,label] of [[null,'Excel import API unavailable'],[{...receipt,sample_only:false},'Excel import API unavailable'],
  [{...receipt,items:null},'Excel import API unavailable'],[{...receipt,initialized:false},'Excel sample family incomplete or not installed']]){
  const {html,calls}=await render({stage:'1'},data,locale);assert.ok(html.includes(translation.exports.translateText(label,locale)));
  assert.deepEqual(rows(html),[]);assert.ok(!html.includes('id="zfi-filters"'));
  assert.ok(!html.includes(translation.exports.translateText('Matched records',locale)));
  assert.deepEqual(calls,[{path:'/api/v1/demo/zfi-import',options:{timeoutMs:15000}}]);
 }
});
for(const locale of ['en','zh'])test('node labels, role distinctions and invalid-parameter warning render accessibly in '+locale,async()=>{
 const labels=['Recorded pending stage','All recorded stages','Stage cannot be confirmed',
  'Recorded sample stages do not establish current frozen Snapshot binding, authorized tasks or formal release.'];
 const {html}=await render({stage:'2'},receipt,locale);
 for(const label of labels){const text=translation.exports.translateText(label,locale);assert.ok(html.includes(text),label);if(locale==='zh')assert.notEqual(text,label);}
 assert.match(html,/<h3 id="zfi-stage">/);
 assert.match(html,/<div[^>]*role="group"[^>]*aria-labelledby="zfi-stage"[^>]*aria-describedby="zfi-stage-help"/);
 const group=html.match(/<div[^>]*aria-labelledby="zfi-stage"[\s\S]*?<\/div>/)[0];
 assert.equal((group.match(/<a\b/g)||[]).length,6);assert.equal((group.match(/aria-current="true"/g)||[]).length,1);
 assert.match(group,/<a[^>]*href="[^"]*stage=2"[^>]*aria-current="true"/);
 for(const role of ['Electronics Manager','Application Manager','R&D Director','Project Manager']){
  const expected=translation.exports.translateText(role,locale).replaceAll('&','&amp;');assert.ok(html.includes(expected),role);
 }
 const warning='Invalid or repeated stage parameter. The stage filter was not applied; other filters remain in effect.';
 const invalid=(await render({stage:['2','3']},receipt,locale)).html;
 assert.ok(invalid.includes(translation.exports.translateText(warning,locale)));assert.match(invalid,/<p role="status">/);
 assert.ok(!html.includes(translation.exports.translateText(warning,locale)));
 assert.ok(!html.includes('method="post"')&&!html.includes('/api/commands')&&!html.includes('operation='));
});
for(const locale of ['en','zh'])test('route drift is visible and prevents false stage confirmation in '+locale,async()=>{
 const drifted={...receipt,approval_routes:{...routes,APPLICATION:['应用工程师','应用经理','系统工程师','研发总监']}};
 const numeric=await render({stage:'2'},drifted,locale);
 assert.deepEqual(rows(numeric.html),[]);
 assert.ok(numeric.html.includes(translation.exports.translateText('Recorded approval routes cannot be confirmed',locale)));
 assert.ok(numeric.html.includes(translation.exports.translateText('Pending records are shown with an unconfirmed stage until both SSR and ASR routes match the recorded sample contract.',locale)));
 assert.ok(!numeric.html.includes('<h2>Approval progress</h2>'));
 const unknown=await render({stage:'UNKNOWN'},drifted,locale);
 assert.deepEqual(rows(unknown.html).sort(),fixtureItems.filter(item=>item.approval_status==='PENDING').map(item=>item.release_id).sort());
 const table=unknown.html.match(/<tbody>[\s\S]*<\/tbody>/)[0];
 assert.ok(table.includes(translation.exports.translateText('Stage cannot be confirmed',locale)));
 for(const label of ['Approved stages','Current stage'])assert.ok(!table.includes(translation.exports.translateText(label,locale)));
});
test('stage controls reuse wrapping and keyboard-focus styles without a new client write or poll path',()=>{
 const css=fs.readFileSync('app/globals.css','utf8');
 assert.match(css,/\.zfi-filter-links\{[^}]*flex-wrap:wrap/);
 assert.match(css,/\.zfi-filter-links a\{[^}]*overflow-wrap:anywhere/);
 assert.match(css,/\.zfi-filter-links a:focus-visible\{/);
 const page=fs.readFileSync('app/demo/zfi/page.tsx','utf8');
 assert.equal((page.match(/await apiGet</g)||[]).length,1);
 assert.ok(!page.includes('setInterval')&&!page.includes('useEffect')&&!page.includes('apiPost')&&!page.includes('force-cache'));
});
test('UNKNOWN rendering tolerates malformed progress objects without showing false current or closed stages',async()=>{
 const base=row(0,'APPLICATION',2);
 for(const patch of [{current_role:{label:'unsafe role'}},{approved_steps:{count:1}},{total_steps:{count:4}},
  {current_step_order:{order:2}},{closed:'true'},{closed:1},{closed:true}]){
  const data={...receipt,items:[{...base,approval_progress:{...base.approval_progress,...patch}}]};
  for(const locale of ['en','zh']){
   const {html}=await render({stage:'UNKNOWN'},data,locale);
   assert.deepEqual(rows(html),['release-0']);
   const table=html.match(/<tbody>[\s\S]*?<\/tbody>/)[0];
   assert.ok(table.includes(translation.exports.translateText('Stage cannot be confirmed',locale)));
   for(const label of ['Approved stages','Current stage','This approval request is closed.'])assert.ok(!table.includes(translation.exports.translateText(label,locale)),label);
   assert.ok(!table.includes('unsafe role'));
  }
 }
});
for(const locale of ['en','zh'])test('unrecognized release type remains visible under UNKNOWN without an invented release route: '+locale,async()=>{
 const data={...receipt,items:[{...row(90),release_type:'OTHER',source_ref:'REF-UNRECOGNIZED',version:'unknown-type-version'}]};
 const {html}=await render({stage:'UNKNOWN'},data,locale);
 assert.ok(html.includes(translation.exports.translateText('Unrecognized release type',locale)));
 const table=html.match(/<tbody>[\s\S]*?<\/tbody>/)[0];
 assert.ok(table.includes('REF-UNRECOGNIZED')&&table.includes('unknown-type-version'));
 assert.ok(table.includes(translation.exports.translateText('Stage cannot be confirmed',locale)));
 assert.ok(!table.includes('/releases/')&&!table.includes('operation='));
 assert.ok(html.includes(translation.exports.translateText('Matched records',locale)+': 1'));
 assert.ok(!html.includes(translation.exports.translateText('No imported records match these filters.',locale)));
});
test('malformed approval reference or status renders UNKNOWN safely and search ignores nonstring evidence',async()=>{
 for(const patch of [{approval_no:{number:'APR-unsafe'}},{approval_status:{status:'PENDING'}},{approval_no:{},approval_status:{}}]){
  const data={...receipt,items:[{...row(0,'APPLICATION',2),...patch}]};
  for(const locale of ['en','zh']){
   const {html}=await render({stage:'UNKNOWN',q:'Original Product'},data,locale);
   assert.deepEqual(rows(html),['release-0']);
   const table=html.match(/<tbody>[\s\S]*?<\/tbody>/)[0];
   assert.ok(table.includes(translation.exports.translateText('Stage cannot be confirmed',locale)));
   assert.ok(table.includes(translation.exports.translateText('Not recorded',locale)));
   assert.ok(!table.includes('[object Object]')&&!table.includes('APR-unsafe'));
   for(const label of ['Approved stages','Current stage','This approval request is closed.'])assert.ok(!table.includes(translation.exports.translateText(label,locale)));
   const absent=(await render({stage:'UNKNOWN',q:'Original missing-term'},data,locale)).html;
   assert.deepEqual(rows(absent),[]);assert.ok(absent.includes(translation.exports.translateText('No imported records match these filters.',locale)));
  }
 }
});
