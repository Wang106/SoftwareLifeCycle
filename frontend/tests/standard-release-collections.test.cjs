'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const rid='11111111-1111-4111-8111-111111111111';
function load(file,api,collections){
 const compiled=ts.transpileModule(fs.readFileSync(path.resolve(file),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};
 const requireMock=name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/lib/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,children)};
  if(name.endsWith('/standard-release-collections'))return {StandardReleaseCollections:collections};
  return require(name);
 };
 new Function('require','module','exports',compiled)(requireMock,module,module.exports);return module.exports;
}
function page(items=[],extra={}){return {release_id:rid,total:123,limit:1,offset:0,next_offset:1,items,...extra};}
async function render(search={},responses={}){
 const requests=[];
 const api=async url=>{requests.push(url);return url.includes('/components?')?(responses.components??page([{id:'c',code:null,name:null,version:'v'}])):(responses.applications??page([{id:'a',version:'2.3.4',status:'DRAFT'}]));};
 const {StandardReleaseCollections}=load('components/standard-release-collections.tsx',api);
 const html=renderToStaticMarkup(await StandardReleaseCollections({releaseId:rid,search,componentCount:123,applicationCount:123}));
 return {html,requests};
}
function links(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));}
test('SSR collections show full counts and exact ASR links with independent pagination',async()=>{
 const {html,requests}=await render({release_limit:'1',component_offset:'2',application_offset:'3'});
 assert.ok(html.includes('123')&&html.includes('Unknown component'));
 assert.ok(links(html).includes('/releases/application/a'));
 assert.equal(requests.length,2);assert.ok(requests[0].includes('limit=1&offset=2'));assert.ok(requests[1].includes('limit=1&offset=3'));
 const paging=links(html).filter(url=>url.startsWith('/releases/standard/'));assert.equal(paging.length,4);
 const parameters=paging.map(url=>new URL(url,'https://test.invalid').searchParams);
 assert.ok(parameters.some(q=>q.get('component_offset')==='1'&&q.get('application_offset')==='3'));
 assert.ok(parameters.some(q=>q.get('component_offset')==='2'&&q.get('application_offset')==='1'));
 assert.ok(paging.every(url=>url.startsWith('/releases/standard/'+rid+'?')));
});
test('wrong-parent collection is unavailable without discarding the other table',async()=>{
 const {html,requests}=await render({}, {components:page([], {release_id:'foreign'})});
 assert.ok(html.includes('Component page unavailable.')&&html.includes('2.3.4'));
 assert.equal(requests.length,2);assert.ok(!requests.some(url=>url.endsWith('/'+rid)));
});
test('array pagination is forwarded as invalid, never silently reset',async()=>{
 const {html,requests}=await render({component_offset:['0','2'],application_offset:'4',release_limit:'1'}, {components:page([], {release_id:'unavailable'})});
 assert.ok(requests[0].includes('offset=invalid')&&requests[1].includes('offset=4'));
 assert.ok(html.includes('Component page unavailable.'));
 assert.ok(links(html).some(url=>url.includes('component_offset=invalid')&&url.includes('application_offset=1')));
});
test('beyond-end tables keep full counts and first-page navigation',async()=>{
 const {html}=await render({}, {components:page([], {next_offset:null}),applications:page([], {next_offset:null})});
 assert.ok(html.includes('No components on this page.')&&html.includes('No application releases on this page.')&&html.includes('123'));
 assert.equal(links(html).length,2);assert.ok(!html.includes('Next page'));
});
test('summary failure and mismatched UUID stop child reads and never call legacy profile',async()=>{
 for(const summary of [null,{id:'foreign'}]){
  const calls=[];let children=0;
  const {default:Page}=load('app/releases/standard/[releaseId]/page.tsx',async url=>{calls.push(url);return summary;},()=>{children++;return null;});
  const html=renderToStaticMarkup(await Page({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve({})}));
  assert.ok(html.includes('Standard release unavailable'));
  assert.deepEqual(calls,['/api/v1/releases/standard/id/'+rid+'/summary']);assert.equal(children,0);
 }
});
test('summary metadata retains exact command target and passes both full counts to collections',async()=>{
 const summary={id:rid,version:'5.1.12',status:'RELEASED',release_notes:null,software:null,supplier:null,previous_release:null,source:{commit:'raw-hash'},component_count:123,application_count:45};
 let props;
 const {default:Page}=load('app/releases/standard/[releaseId]/page.tsx',async()=>summary,p=>{props=p;return null;});
 const html=renderToStaticMarkup(await Page({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve({component_offset:'2'})}));
 assert.ok(html.includes('operation=snapshot&amp;target='+rid)&&html.includes('raw-hash'));
 assert.equal(props.releaseId,rid);assert.equal(props.componentCount,123);assert.equal(props.applicationCount,45);assert.equal(props.search.component_offset,'2');
});
