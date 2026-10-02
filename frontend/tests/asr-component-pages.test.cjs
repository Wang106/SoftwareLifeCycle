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
  if(name.endsWith('/asr-component-pages'))return {AsrComponentPages:collections};
  return require(name);
 };
 new Function('require','module','exports',compiled)(requireMock,module,module.exports);return module.exports;
}
const bid='22222222-2222-4222-8222-222222222222';
function page(items=[],extra={}){return {release_id:rid,base_release_id:bid,total:123,limit:1,offset:0,next_offset:1,items,...extra};}
async function render(search={},responses={}){
 const requests=[];
 const api=async url=>{requests.push(url);return url.includes('/declarations?')?(responses.declarations??page([{id:'raw-uuid',code:null,name:null,asr_version:null,declared_delta_type:'UNCHANGED',base_component_version:null,base_link_status:'VALID'}])):(responses.unlinked??page([{id:'b',code:'BASE',name:null,version:'same'}]));};
 const {AsrComponentPages}=load('components/asr-component-pages.tsx',api);
 const html=renderToStaticMarkup(await AsrComponentPages({releaseId:rid,baseReleaseId:bid,search,componentCount:123,unlinkedCount:45}));
 return {html,requests};
}
function links(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));}
test('ASR tables keep full counts, null-version valid links and independent pagination',async()=>{
 const {html,requests}=await render({component_limit:'1',declaration_offset:'2',unlinked_offset:'3'});
 assert.ok(html.includes('123')&&html.includes('45')&&html.includes('raw-uuid')&&html.includes('Linked to base SSR'));
 assert.equal(requests.length,2);assert.ok(requests[0].includes('limit=1&offset=2'));assert.ok(requests[1].includes('limit=1&offset=3'));
 const paging=links(html);assert.equal(paging.length,4);
 const parameters=paging.map(url=>new URL(url,'https://test.invalid').searchParams);
 assert.ok(parameters.some(q=>q.get('declaration_offset')==='1'&&q.get('unlinked_offset')==='3'));
 assert.ok(parameters.some(q=>q.get('declaration_offset')==='2'&&q.get('unlinked_offset')==='1'));
 assert.ok(paging.every(url=>url.startsWith('/releases/application/'+rid+'/components?')));
});
test('wrong release or changed baseline rejects only affected table',async()=>{
 for(const extra of [{release_id:'foreign'},{base_release_id:'foreign'},{base_release_id:null}]){
  const {html,requests}=await render({}, {declarations:page([],extra)});
  assert.ok(html.includes('ASR declaration page unavailable.')&&html.includes('BASE'));assert.equal(requests.length,2);
 }
 const {html}=await render({}, {unlinked:page([],{base_release_id:'foreign'})});
 assert.ok(html.includes('Unlinked baseline page unavailable.')&&html.includes('Linked to base SSR'));
});
test('array pagination forwarded as invalid while other offset preserved',async()=>{
 const {html,requests}=await render({declaration_offset:['0','2'],unlinked_offset:'4',component_limit:'1'}, {declarations:page([],{release_id:'unavailable'})});
 assert.ok(requests[0].includes('offset=invalid')&&requests[1].includes('offset=4'));
 assert.ok(html.includes('ASR declaration page unavailable.'));
 assert.ok(links(html).some(url=>url.includes('declaration_offset=invalid')&&url.includes('unlinked_offset=1')));
});
test('beyond-end keeps full counts and first-page links',async()=>{
 const {html}=await render({}, {declarations:page([],{next_offset:null}),unlinked:page([],{next_offset:null})});
 assert.ok(html.includes('No ASR declarations on this page.')&&html.includes('No unlinked baseline components on this page.')&&html.includes('123'));
 assert.equal(links(html).length,2);assert.ok(!html.includes('Next page'));
});
test('summary failure or mismatched parent stops child reads with no legacy fallback',async()=>{
 for(const summary of [null,{release_id:'foreign'}]){
  const calls=[];let children=0;
  const {default:Page}=load('app/releases/application/[releaseId]/components/page.tsx',async url=>{calls.push(url);return summary;},()=>{children++;return null;});
  const html=renderToStaticMarkup(await Page({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve({})}));
  assert.ok(html.includes('Components unavailable'));
  assert.deepEqual(calls,['/api/v1/releases/application/id/'+rid+'/components/summary']);assert.equal(children,0);
 }
});
test('summary passes exact recorded baseline and both full counts',async()=>{
 for(const base_release of [{id:bid,version:'same'},null]){
  let props;
  const {default:Page}=load('app/releases/application/[releaseId]/components/page.tsx',async()=>({release_id:rid,version:'same',base_release,component_count:123,unlinked_base_count:45}),p=>{props=p;return null;});
  const html=renderToStaticMarkup(await Page({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve({declaration_offset:'2'})}));
  assert.ok(html.includes('/releases/application/'+rid));assert.equal(props.releaseId,rid);assert.equal(props.baseReleaseId,base_release?.id??null);
  assert.equal(props.componentCount,123);assert.equal(props.unlinkedCount,45);assert.equal(props.search.declaration_offset,'2');
 }
});
