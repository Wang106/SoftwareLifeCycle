const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const ts=require('typescript');const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const zh=require('../lib/i18n/zh.json');
function loader(api,language='en') {
 const cache={};
 function load(file) {
  if(cache[file])return cache[file].exports;
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const m={exports:{}};cache[file]=m;
  new Function('require','module','exports',code)(name=>{
   if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
   if(name.endsWith('/api'))return {apiGet:api};
   if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,language==='zh'&&typeof children==='string'?(zh[children]??children):children)};
   if(name.startsWith('.'))return load(path.resolve(path.dirname(file),name)+(name.endsWith('organization-views')?'.ts':'.tsx'));
   return require(name);
  },m,m.exports);return m.exports;
 }
 return file=>load(path.resolve(file)).default;
}
function row(kind){return {kind,id:'org-uuid',code:'CODE / A',name:'Original business name',status:'ACTIVE',country:'CN',region:'APAC',description:'Business introduction',website:'https://example.org',software_count:121,project_count:121,released_project_count:19,site_count:121,customer_id:'customer-uuid',customer_code:'C / A',customer_name:'Customer name',vehicle_platform:'Platform',release_id:'asr-uuid',release_version:'1.2',release_status:'DRAFT'};}
const child={id:'child-uuid',code:'CH / A',name:'Original child',status:'ACTIVE',type:'BMS',release_id:'release-uuid',release_version:'3.2',release_status:'DRAFT'};
for(const kind of ['suppliers','customers','projects']) {
 test(kind+' bounded catalog full counts exact links retained filters',async()=>{
  const calls=[];const Page=loader(async url=>{calls.push(url);return {kind,total:205,limit:1,offset:200,next_offset:201,items:[row(kind)]};})('components/organization-catalog.tsx');
  const html=renderToStaticMarkup(await Page({kind,search:{q:'_%',status:'ACTIVE',country:'CN',region:'APAC',customer_id:'customer-uuid',limit:'1',offset:'200'}}));
  assert.equal(calls.length,1);assert.ok(calls[0].startsWith('/api/v1/organization-views/'+kind));
  assert.ok(html.includes('205')&&html.includes('121')&&html.includes('Original business name'));
  assert.ok(html.includes('/'+kind+'/'+encodeURIComponent(kind==='projects'?'org-uuid':'CODE / A')));
  assert.ok(html.includes('offset=201')&&html.includes('q=_%')&&html.includes('status=ACTIVE'));
  if(kind==='projects')assert.ok(html.includes('/releases/application/asr-uuid'));
 });
 test(kind+' unavailable and beyond-end catalog distinguish counts',async()=>{
  for(const response of [null,{kind,total:205,limit:1,offset:100000,next_offset:null,items:[]}]){
   const Page=loader(async()=>response)('components/organization-catalog.tsx');
   const html=renderToStaticMarkup(await Page({kind,search:{}}));
   assert.ok(html.includes(response?'205':'Organization catalog unavailable'));assert.ok(!html.includes('Next page'));
  }
 });
 test(kind+' exact owned profile counts metadata and child navigation',async()=>{
  const calls=[];const Page=loader(async url=>{calls.push(url);return url.includes('/summary')?row(kind):{kind,organization_id:'org-uuid',total:121,limit:1,offset:0,next_offset:1,items:[child]};})('components/organization-profile.tsx');
  const html=renderToStaticMarkup(await Page({kind,identifier:'CODE / A',search:{limit:'1'}}));
  assert.equal(calls.length,2);assert.match(calls[1],/organization_id=org-uuid/);assert.ok(html.includes('121')&&html.includes('Original child')&&html.includes('entity_id=org-uuid'));
  assert.ok(html.includes('offset=1')&&html.includes('limit=1'));
  assert.ok(html.includes(kind==='suppliers'?'/releases/standard/release-uuid':kind==='customers'?'/projects/child-uuid':'/manufacturing/sites/'+encodeURIComponent(child.code)));
  if(kind==='suppliers')assert.ok(html.includes('Business introduction'));
 });
 test(kind+' failed foreign and beyond-end child page preserves parent',async()=>{
  for(const response of [null,{kind,organization_id:'foreign',items:[child]},{kind,organization_id:'org-uuid',total:121,next_offset:null,items:[]}]){
   const calls=[];const Page=loader(async url=>{calls.push(url);return url.includes('/summary')?row(kind):response;})('components/organization-profile.tsx');
   const html=renderToStaticMarkup(await Page({kind,identifier:'CODE / A',search:{offset:['1','2']}}));
   assert.match(calls[1],/offset=invalid/);assert.ok(html.includes('121'));
   assert.ok(html.includes(response?.organization_id==='org-uuid'?'No records on this page.':'Organization collection unavailable'));
   assert.ok(!html.includes('Original child'));
  }
 });
 test(kind+' invalid parent stops child reads',async()=>{
  for(const response of [null,{...row(kind),kind:'wrong'},{...row(kind),id:'other',code:'other'}]){
   const calls=[];const Page=loader(async url=>{calls.push(url);return response;})('components/organization-profile.tsx');
   const html=renderToStaticMarkup(await Page({kind,identifier:'CODE / A',search:{}}));
   assert.equal(calls.length,1);assert.ok(html.includes('unavailable'));assert.ok(!html.includes('121'));
  }
 });
}
test('bilingual organization views preserve business text',async()=>{
 for(const kind of ['suppliers','customers','projects']){
  const api=async url=>url.includes('/summary')?row(kind):{kind,organization_id:'org-uuid',total:121,next_offset:null,items:[child]};
  const load=loader(api,'zh');
  const profile=renderToStaticMarkup(await load('components/organization-profile.tsx')({kind,identifier:'CODE / A',search:{}}));
  const catalog=renderToStaticMarkup(await load('components/organization-catalog.tsx')({kind,search:{}}));
  assert.ok(catalog.includes('匹配的组织记录')&&profile.includes(zh['Page size'])&&profile.includes('Original business name'));
 }
});

test('project UUID matching is case insensitive and prevents UUID-shaped code substitution',async()=>{
 const id='abcdefab-1234-1234-1234-123456789abc';
 for(const identifier of [id.toUpperCase(),id.replaceAll('-','')]){
  const calls=[];const Page=loader(async url=>{calls.push(url);return url.includes('/summary')?{...row('projects'),id,code:'P'}:{kind:'projects',organization_id:id,total:121,next_offset:null,items:[]};})('components/organization-profile.tsx');
  assert.ok(renderToStaticMarkup(await Page({kind:'projects',identifier,search:{}})).includes('121'));assert.equal(calls.length,2);
 }
 const calls=[];const Page=loader(async url=>{calls.push(url);return {...row('projects'),id:'foreign',code:id};})('components/organization-profile.tsx');
 assert.ok(renderToStaticMarkup(await Page({kind:'projects',identifier:id,search:{}})).includes('Project unavailable'));assert.equal(calls.length,1);
});
