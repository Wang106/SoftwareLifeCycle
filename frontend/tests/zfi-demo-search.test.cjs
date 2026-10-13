'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const translated={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(
 n=>n.endsWith('zh.json')?require('../lib/i18n/zh.json'):require('../lib/i18n/templates.json'),translated,translated.exports);
const items=Array.from({length:20},(_,i)=>Object.freeze({
 source_ref:(i<4?'SSR':'ASR')+String(i+1).padStart(2,'0'),release_id:'release-'+i,version:i<4?'v3.8.1':'v3.8.1.1',
 release_type:i<4?'STANDARD':'APPLICATION',product:'Original Product',customer:i<4?null:i%2?'VOL':'KUBO',
 project_code:i<4?null:'PROJECT-'+i,record_status:'DRAFT',approval_no:'APR-'+i,
 approval_status:i<4?'PENDING':i%2?'REJECTED':'APPROVED',source_release_date:null,
 supplied_artifacts:0,supplied_test_evidence:0
}));
const receipt=Object.freeze({sample_only:true,initialized:true,import_event_no:'EVT-ORIGINAL',items:Object.freeze(items)});
async function render(query={},data=receipt,locale='en'){
 const m={exports:{}},calls=[];
 const code=ts.transpileModule(fs.readFileSync('app/demo/zfi/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const translate=c=>typeof c==='string'?translated.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 new Function('require','module','exports',code)(n=>n==='next/link'?({href,children,...props})=>React.createElement('a',{href,...props},children):
  n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);return data;}}:
  n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n),m,m.exports);
 return {html:renderToStaticMarkup(await m.exports.default({searchParams:Promise.resolve(query)})),calls};
}
function rows(html){return [...html.matchAll(/href="\/releases\/(?:standard|application)\/(release-\d+)"/g)].map(m=>m[1]);}
function links(html){return [...html.matchAll(/<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/g)].map(m=>({href:m[1].replaceAll('&amp;','&'),label:m[2]}));}
for(const [name,q,expected] of [
 ['version','V3.8.1.1',items.slice(4,14)],
 ['Excel reference','asr05',[items[4]]],
 ['project','project-16',[items[16]]],
 ['product','original product',items.slice(0,10)],
 ['customer','kUbO',items.filter(r=>r.customer==='KUBO')],
 ['exact release identity','release-16',[items[16]]],
 ['approval reference','apr-16',[items[16]]],
 ['multiple words across fields','KUBO v3.8.1.1',items.filter(r=>r.customer==='KUBO')]
])test('literal case-insensitive search by '+name,async()=>{
 const {html,calls}=await render({q});assert.deepEqual(rows(html),expected.map(r=>r.release_id));
 assert.deepEqual(calls,['/api/v1/demo/zfi-import']);
 assert.ok(html.includes('SSR: 4')&&html.includes('ASR: 16'));
});
test('search intersects all three filters without changing the evidence or seeded family counts',async()=>{
 const {html}=await render({q:'v3.8.1.1',type:'APPLICATION',customer:'VOL',status:'REJECTED'});
 assert.deepEqual(rows(html),items.filter(r=>r.customer==='VOL').map(r=>r.release_id));
 assert.ok(html.includes('Matched records: 8')&&html.includes('APPROVED: 8')&&html.includes('PENDING: 4'));
 assert.ok(html.includes('Original Product')&&html.includes('/approvals/APR-5'));
});
test('unknown terms and conflicting terms show no matches without substituting another customer',async()=>{
 for(const q of ['absent','KUBO VOL','.*','^v3']){
  const {html}=await render({q});assert.deepEqual(rows(html),[]);
  assert.ok(html.includes('Matched records: 0')&&html.includes('No imported records match these filters.')&&!html.includes('Next page'));
 }
});
test('word order and surrounding whitespace do not change the match set; repeated query is ignored',async()=>{
 assert.deepEqual(rows((await render({q:'  v3.8.1.1   KUBO  '})).html),items.filter(r=>r.customer==='KUBO').map(r=>r.release_id));
 assert.deepEqual(rows((await render({q:['KUBO','VOL']})).html),items.slice(0,10).map(r=>r.release_id));
 assert.deepEqual(rows((await render({q:' \t '})).html),items.slice(0,10).map(r=>r.release_id));
});
test('pagination and filter links retain the original search; the GET search preserves filters and resets the page',async()=>{
 const {html}=await render({q:'v3.8.1.1',type:'APPLICATION'});
 const next=links(html).find(a=>a.label==='Next page');assert.ok(next);
 const params=new URL(next.href,'https://example.test').searchParams;
 assert.equal(params.get('q'),'v3.8.1.1');assert.equal(params.get('type'),'APPLICATION');assert.equal(params.get('page'),'2');
 assert.deepEqual(rows((await render(Object.fromEntries(params))).html),items.slice(14).map(r=>r.release_id));
 const second=(await render({q:'v3.8.1.1',type:'APPLICATION',customer:'VOL',status:'REJECTED',page:'2'})).html;
 const customer=links(second).find(a=>a.label==='KUBO'),target=new URL(customer.href,'https://example.test').searchParams;
 assert.equal(target.get('q'),'v3.8.1.1');assert.equal(target.get('status'),'REJECTED');assert.equal(target.has('page'),false);
 assert.match(second,/<form[^>]*action="\/demo\/zfi"[^>]*method="get"/);
 const form=second.match(/<form\b[\s\S]*?<\/form>/)[0];
 for(const [key,value] of [['type','APPLICATION'],['customer','VOL'],['status','REJECTED']])assert.ok(form.includes('name="'+key+'" value="'+value+'"'));
 assert.ok(!form.includes('name="page"')&&!form.includes('method="post"')&&!form.includes('operation'));
 assert.ok(links(second).some(a=>a.label==='Clear filters'&&a.href==='/demo/zfi'));
});
test('search words with Unicode and URL syntax remain text and cannot inject a navigation target',async()=>{
 const product='A&B / 東京 <script>',data={...receipt,items:[{...items[4],product}]};
 const {html}=await render({q:product},data);assert.deepEqual(rows(html),['release-4']);
 assert.ok(html.includes('A&amp;B / 東京 &lt;script&gt;')&&!html.includes('<script>'));
 const link=links(html).find(a=>a.label==='All customers'),url=new URL(link.href,'https://example.test');
 assert.equal(url.pathname,'/demo/zfi');assert.equal(url.searchParams.get('q'),product);
 assert.deepEqual([...url.searchParams.keys()],['q']);
});
for(const locale of ['zh','en'])test('search has bilingual accessible labeling and a read-only GET action: '+locale,async()=>{
 const {html}=await render({},receipt,locale);
 for(const label of ['Search imported records','Search','Matches all words across version, Excel reference, software, customer, project, release UUID and approval number.']){
  assert.ok(html.includes(translated.exports.translateText(label,locale)),label);
  if(locale==='zh')assert.notEqual(translated.exports.translateText(label,locale),label);
 }
 assert.match(html,/<label for="zfi-search"/);assert.match(html,/<input[^>]*id="zfi-search"[^>]*aria-describedby="zfi-search-help"/);
 assert.ok(!html.includes('method="post"')&&!html.includes('/api/commands')&&!html.includes('operation='));
});
test('unavailable, foreign and incomplete data do not expose search controls',async()=>{
 for(const data of [null,{...receipt,sample_only:false},{...receipt,initialized:false},{...receipt,items:null}]){
  const {html}=await render({q:'KUBO'},data);assert.deepEqual(rows(html),[]);assert.ok(!html.includes('id="zfi-search"'));
 }
});
