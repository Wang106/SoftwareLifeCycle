const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file,api){
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};
 new Function('require','module','exports',code)(name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,children)};
  if(name.startsWith('./'))return require(require('node:path').resolve(require('node:path').dirname(file),name));
  return require(name);
 },m,m.exports);return m.exports;
}
const row={id:'exact-id',version:'raw-version',status:'RELEASED',customer:'Customer',project:'Project',base_id:'base-id',base_version:'5',snapshot_no:'SNAP-1',software:{code:'B',name:'BMS'},supplier:{code:'S',name:'Supplier'}};
async function render(kind='application',search={},response={kind,total:205,limit:1,offset:200,next_offset:201,items:[row]}){
 const calls=[];const Page=load('components/release-catalog.tsx',async url=>{calls.push(url);return response;}).default;
 return {calls,html:renderToStaticMarkup(await Page({kind,search}))};
}
for(const kind of ['application','standard'])test(kind+' catalog preserves counts, exact links and filters across navigation',async()=>{
 const {html,calls}=await render(kind,{q:'_%',status:'RELEASED',software_id:'uuid',limit:'1',offset:'200'});
 assert.ok(html.includes('205')&&html.includes('/releases/'+kind+'/exact-id')&&html.includes('raw-version'));
 assert.equal(calls.length,1);assert.ok(calls[0].startsWith('/api/v1/release-catalog/'+kind+'?'));
 const links=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));
 const next=links.find(x=>x.includes('offset=201'));const q=new URL(next,'https://test.invalid').searchParams;
 assert.equal(q.get('q'),'_%');assert.equal(q.get('software_id'),'uuid');assert.equal(q.get('status'),'RELEASED');assert.equal(q.get('limit'),'1');
 assert.ok(links.some(x=>x.startsWith('/releases/'+kind+'?')&&!x.includes('offset=')));
});
test('beyond-end differs from API failure and mismatched catalog',async()=>{
 const empty=await render('application',{}, {kind:'application',total:205,limit:1,offset:999,next_offset:null,items:[]});
 assert.ok(empty.html.includes('205')&&empty.html.includes('No releases on this page.')&&!empty.html.includes('Next page'));
 for(const value of [null,{kind:'standard',items:[],total:0}]){
  const {html}=await render('application',{},value);assert.ok(html.includes('Release catalog unavailable')&&!html.includes('Total releases'));
 }
});
test('repeated pagination is forwarded as invalid, never silently reset',async()=>{
 const {calls}=await render('application',{limit:['1','2'],offset:['0','2']},null);
 assert.ok(calls[0].includes('limit=invalid')&&calls[0].includes('offset=invalid'));
});
test('legacy resolver keeps exact identifiers and suffix, fails closed and bypasses demo',async()=>{
 for(const result of [{state:'unique',release:{id:'exact-id',version:'v'}},{state:'ambiguous',release:null},{state:'missing',release:null},null]){
  const calls=[];const {legacyReleaseTarget}=load('lib/legacy-release.ts',async url=>{calls.push(url);return result;});
  assert.equal(await legacyReleaseTarget('old & version','/passport'),result?.state==='unique'?'/releases/application/exact-id/passport':'/releases/application');
  assert.equal(calls.length,1);assert.equal(new URL(calls[0],'https://test.invalid').searchParams.get('identifier'),'old & version');
  assert.equal(await legacyReleaseTarget('demo'),'/releases/application');assert.equal(calls.length,1);
 }
});
test('release catalog labels have Chinese and English output',()=>{
 const {translateText}=load('lib/i18n.ts',null);
 for(const text of ['Total releases','Releases on this page','No releases on this page.','Release catalog unavailable','Page size']){
  assert.match(translateText(text,'zh'),/[\u4e00-\u9fff]/);assert.equal(translateText(text,'en'),text);
 }
});
test('actual localization renders catalog Chinese by default and English without changing identifiers',async()=>{
 const path=require('node:path');const {execFileSync}=require('node:child_process');
 const tmp=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-catalog-'));
 try {
  execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/localized.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',tmp]);
  fs.symlinkSync(path.resolve('node_modules'),path.join(tmp,'node_modules'),'dir');
  const localized=require(path.join(tmp,'components/localized.js'));
  const code=ts.transpileModule(fs.readFileSync('components/release-catalog.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const m={exports:{}};
  new Function('require','module','exports',code)(name=>{
   if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
   if(name.endsWith('/api'))return {apiGet:async()=>({kind:'application',total:205,next_offset:null,items:[row]})};
   if(name.endsWith('/localized'))return localized;
   return require(name);
  },m,m.exports);
  for(const locale of ['zh','en']){
   const element=await m.exports.default({kind:'application',search:{}});
   const html=renderToStaticMarkup(React.createElement(localized.LanguageProvider,{initialLocale:locale},element));
   assert.ok(html.includes(locale==='zh'?'发布总数':'Total releases'));
   assert.ok(html.includes(locale==='zh'?'已发布':'RELEASED'));
   assert.ok(html.includes('/releases/application/exact-id')&&html.includes('raw-version')&&html.includes('205'));
  }
 } finally {fs.rmSync(tmp,{recursive:true,force:true});}
});
