'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const translation={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(
 n=>n.endsWith('zh.json')?require('../lib/i18n/zh.json'):require('../lib/i18n/templates.json'),translation,translation.exports);
const items=Array.from({length:20},(_,i)=>({
 source_ref:(i<4?'SSR':'ASR')+String(i+1).padStart(2,'0'),release_id:'release-'+i,version:'same-version',
 release_type:i<4?'STANDARD':'APPLICATION',product:'Original Product',customer:i<4?null:i%2?'VOL':'KUBO',
 project_code:i<4?null:String(i),record_status:'DRAFT',approval_no:'APR-'+i,
 approval_status:i<4?'PENDING':i%2?'REJECTED':'APPROVED',source_release_date:i%2?null:'2026-01-01',
 supplied_artifacts:0,supplied_test_evidence:0
}));
const receipt={sample_only:true,initialized:true,import_event_no:'EVT-ORIGINAL',items};
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
freeze(receipt);
async function render(query={},data=receipt,locale='en'){
 const m={exports:{}},calls=[];
 const code=ts.transpileModule(fs.readFileSync('app/demo/zfi/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const translate=c=>typeof c==='string'?translation.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 new Function('require','module','exports',code)(n=>n==='next/link'?({href,children,...props})=>React.createElement('a',{href,...props},children):
  n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);return data;}}:
  n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n),m,m.exports);
 return {html:renderToStaticMarkup(await m.exports.default({searchParams:Promise.resolve(query)})),calls};
}
function rows(html){return [...html.matchAll(/href="\/releases\/(?:standard|application)\/(release-\d+)"/g)].map(m=>m[1]);}
function links(html){return [...html.matchAll(/<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/g)].map(m=>({href:m[1].replaceAll('&amp;','&'),label:m[2]}));}
test('default and followed second page partition the complete family with preserved UUID links',async()=>{
 const first=await render(),next=links(first.html).find(a=>a.label==='Next page');
 assert.ok(next);assert.deepEqual(rows(first.html),items.slice(0,10).map(r=>r.release_id));
 const second=await render(Object.fromEntries(new URL(next.href,'https://example.test').searchParams));
 assert.deepEqual(rows(second.html),items.slice(10).map(r=>r.release_id));
 assert.equal(new Set([...rows(first.html),...rows(second.html)]).size,20);
 assert.ok(!links(second.html).some(a=>a.label==='Next page'));
 assert.ok(links(second.html).some(a=>a.label==='Previous page'&&a.href==='/demo/zfi'));
 assert.deepEqual(first.calls,['/api/v1/demo/zfi-import']);
});
test('type customer and status combine without merging the same-version identities',async()=>{
 const {html}=await render({type:'APPLICATION',customer:'KUBO',status:'APPROVED'});
 assert.deepEqual(rows(html),items.filter(r=>r.customer==='KUBO').map(r=>r.release_id));
 assert.ok(html.includes('Matched records: 8')&&html.includes('SSR: 4')&&html.includes('ASR: 16'));
 assert.ok(html.includes('APPROVED: 8')&&html.includes('REJECTED: 8')&&html.includes('PENDING: 4'));
 assert.ok(!html.includes('/approvals/APR-5')&&html.includes('/approvals/APR-4'));
});
test('filter changes reset the page and keep other filters; clear removes all filters',async()=>{
 const {html}=await render({type:'APPLICATION',customer:'VOL',status:'REJECTED',page:'2'});
 const approved=links(html).find(a=>a.label==='APPROVED');
 assert.equal(approved.href,'/demo/zfi?type=APPLICATION&customer=VOL&status=APPROVED');
 assert.ok(links(html).some(a=>a.label==='Clear filters'&&a.href==='/demo/zfi'));
 assert.match(html,/aria-current="true"[^>]*>VOL<\/a>/);
});
test('page navigation preserves active predicates and stable order',async()=>{
 const {html}=await render({type:'APPLICATION'});
 const next=links(html).find(a=>a.label==='Next page');assert.equal(next.href,'/demo/zfi?type=APPLICATION&page=2');
 const second=await render({type:'APPLICATION',page:'2'});
 assert.deepEqual(rows(second.html),items.slice(14).map(r=>r.release_id));
});
test('empty intersection never falls back to other customers or standard records',async()=>{
 const {html}=await render({type:'STANDARD',customer:'VOL'});
 assert.deepEqual(rows(html),[]);assert.ok(html.includes('No imported records match these filters.'));
 assert.ok(html.includes('Matched records: 0')&&html.includes('SSR: 4')&&!html.includes('Next page'));
 const unknown=await render({customer:'unknown'});assert.deepEqual(rows(unknown.html),[]);
});
test('unrecorded approval is filterable without creating a synthetic approval',async()=>{
 const data={...receipt,items:[{...items[4],approval_no:null,approval_status:null},items[5]]};
 const {html}=await render({status:'UNRECORDED'},data);
 assert.deepEqual(rows(html),['release-4']);assert.ok(html.includes('Not recorded')&&!html.includes('/approvals/APR-'));
});
test('customer query encoding preserves raw evidence and cannot add a second parameter',async()=>{
 const customer='A&B / 東京',data={...receipt,items:[{...items[4],customer}]};
 const {html}=await render({},data),link=links(html).find(a=>a.label===customer.replace('&','&amp;'));
 assert.ok(link);assert.equal(new URL(link.href,'https://example.test').searchParams.get('customer'),customer);
 assert.equal([...new URL(link.href,'https://example.test').searchParams.keys()].length,1);
 const filtered=await render({customer},data);assert.deepEqual(rows(filtered.html),['release-4']);
});
for(const page of ['-1','0','2.5','1e2','999999999999999999999',['2','1']])test('invalid page stays on first page: '+String(page),async()=>{
 assert.deepEqual(rows((await render({page})).html),items.slice(0,10).map(r=>r.release_id));
});
test('out-of-range integer page clamps to the final available page',async()=>{
 assert.deepEqual(rows((await render({page:'999'})).html),items.slice(10).map(r=>r.release_id));
});
test('repeated and unknown type or status values are normalized without forwarding arbitrary query keys',async()=>{
 const {html}=await render({type:['APPLICATION','STANDARD'],status:'foreign',operation:'write'});
 assert.deepEqual(rows(html),items.slice(0,10).map(r=>r.release_id));
 assert.ok(!html.includes('operation=')&&!html.includes('status=foreign'));
});
for(const locale of ['zh','en'])test('filters and empty result labels render bilingually without command forms: '+locale,async()=>{
 const {html}=await render({customer:'unknown'},receipt,locale);
 for(const label of ['Filter imported records','All release types','All customers','All approval statuses','Clear filters','Matched records','Record pages','Summary counts describe the complete imported family; filters apply only to the records below.','No imported records match these filters.']){
  assert.ok(html.includes(translation.exports.translateText(label,locale)),label);
  if(locale==='zh')assert.notEqual(translation.exports.translateText(label,locale),label);
 }
 assert.ok(!html.includes('<form')&&!html.includes('/api/commands')&&!html.includes('operation='));
});
for(const data of [null,{...receipt,sample_only:false},{...receipt,initialized:false},{...receipt,items:null}])test('unavailable foreign incomplete or malformed receipt never exposes filter or pagination controls',async()=>{
 const {html}=await render({page:'2',customer:'VOL'},data);
 assert.deepEqual(rows(html),[]);assert.ok(!html.includes('id="zfi-filters"')&&!html.includes('id="zfi-pages"'));
});
