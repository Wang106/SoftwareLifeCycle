'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const id='11111111-1111-4111-8111-111111111111';
function load(file,api){
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,module={exports:{}};
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:api}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,children),LocalizedAttributes:({children})=>children}:n.endsWith('/dvp-relations')?{DvpRelations:()=>React.createElement('div',null,'paged relations')}:require(n);
 new Function('require','module','exports',code)(req,module,module.exports);return module.exports;
}
async function render(search={},changes={}){
 const calls=[];const api=async path=>{calls.push(path);const url=new URL(path,'https://test.invalid'),kind=url.pathname.split('/').at(-1);return kind in changes?changes[kind]:{item_id:id,kind,total:123,limit:Number(url.searchParams.get('limit')||50),offset:Number(url.searchParams.get('offset')||0),next_offset:2,items:[{id:kind,number:kind,text:'Raw '+kind}]};};
 const Component=load('components/dvp-relations.tsx',api).DvpRelations;
 return {html:renderToStaticMarkup(await Component({item:{id,relation_counts:{criteria:123,points:456,issues:789}},search})),calls};
}
test('independent pages and links preserve all cursors, exact item and historical filters',async()=>{
 const {html,calls}=await render({relation_limit:'2',criteria_offset:'3',points_offset:'4',issues_offset:'5',release_id:'release',snapshot_no:'OLD',before_number:'7'});
 assert.equal(calls.length,3);calls.forEach((url,n)=>{const q=new URL(url,'https://test.invalid').searchParams;assert.equal(q.get('dvp_item_id'),id);assert.equal(q.get('offset'),String(n+3));assert.equal(q.get('limit'),'2');});
 const links=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&')).filter(u=>u.startsWith('/testing/'));
 assert.equal(links.length,6);for(const link of links){const q=new URL(link,'https://test.invalid').searchParams;assert.equal(q.get('snapshot_no'),'OLD');assert.equal(q.get('before_number'),'7');assert.equal(q.get('relation_item_id'),id);assert.ok(q.has('criteria_offset')&&q.has('points_offset')&&q.has('issues_offset'));}
 assert.ok(html.includes('123')&&html.includes('456')&&html.includes('789')&&html.includes('/issues/issues'));
});
for(const field of ['item_id','kind','limit','offset'])test('foreign/mismatched '+field+' fails only its own relation page',async()=>{
 const {html,calls}=await render({}, {criteria:{item_id:id,kind:'criteria',limit:50,offset:0,total:1,items:[{id:'bad',number:'bad',text:'FOREIGN DATA'}],next_offset:null,[field]:'foreign'}});
 assert.ok(html.includes('Linked records unavailable.')&&!html.includes('FOREIGN DATA')&&html.includes('Raw issues'));assert.equal(calls.length,3);
});
test('invalid repeated pagination reaches strict API validation; empty page retains counts',async()=>{
 const invalid=await render({relation_limit:['1','2'],points_offset:['0','1']},{criteria:null,points:null,issues:null});assert.ok(invalid.calls.every(u=>u.includes('limit=invalid'))&&invalid.calls[1].includes('offset=invalid'));
 const empty=await render({}, {issues:{item_id:id,kind:'issues',total:789,limit:50,offset:0,next_offset:null,items:[]}});assert.ok(empty.html.includes('789')&&empty.html.includes('No linked records on this page.'));
});
async function parent(extra={},search={}){
 const calls=[],api=async u=>{calls.push(u);return u.includes('/profile')?{id,item_no:'DVP',title:'Item',scope:'SOFTWARE_TEST',status:'OPEN',plan:null,release_options:[],release_options_truncated:false,relation_counts:{criteria:0,points:0,issues:0},...extra}:null;};
 const Page=load('app/testing/dvp/[itemId]/page.tsx',api).default;return {html:renderToStaticMarkup(await Page({params:Promise.resolve({itemId:id}),searchParams:Promise.resolve(search)})),calls};
}
test('parent rejects foreign profile or stale item pin and offers no substitute',async()=>{
 for(const [extra,search] of [[{id:'foreign'},{}],[{}, {relation_item_id:'foreign'}]]){const r=await parent(extra,search);assert.ok(r.html.includes('DVP item unavailable')&&!r.html.includes('paged relations'));}
});
test('profile consumes counts with no old arrays; history failure retains independent relations',async()=>{
 const r=await parent();assert.ok(r.html.includes('paged relations')&&r.html.includes('History unavailable'));assert.ok(r.calls.every(u=>u.includes('/profile')||u.includes('/executions?')));
});
