const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file,api,localized){
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};
 new Function('require','module','exports',code)(name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return localized??{Localized:({children})=>React.createElement(React.Fragment,null,children)};
  return require(name);
 },m,m.exports);return m.exports.default;
}
const row={id:'exact-id',request_no:'SCR A/1',issue_no:'ISS A/1',title:'Original customer title',scope:'STANDARD',source:'ISSUE',change_type:'BUG_FIX',severity:'HIGH',status:'IN_TEST'};
async function render(kind,search={},response={kind,total:205,limit:1,offset:200,next_offset:201,in_verification:82,ready_for_release:82,items:[row]}){
 const calls=[];const Page=load('components/change-issue-catalog.tsx',async url=>{calls.push(url);return response;});
 return {calls,html:renderToStaticMarkup(await Page({kind,search}))};
}
for(const kind of ['changes','issues'])test(kind+' complete counts and exact links survive pagination with filters',async()=>{
 const search={q:'_%',scope:'STANDARD',status:'IN_TEST',limit:'1',offset:'200',...(kind==='changes'?{source:'ISSUE',change_type:'BUG_FIX',software_id:'software',customer_id:'customer',project_id:'project'}:{severity:'HIGH'})};
 const {html,calls}=await render(kind,search);
 assert.ok(html.includes('205')&&html.includes('Original customer title'));
 assert.ok(html.includes('/'+kind+'/'+encodeURIComponent(kind==='changes'?row.request_no:row.issue_no)));
 if(kind==='changes')assert.ok(html.includes('82'));
 assert.equal(calls.length,1);assert.ok(calls[0].startsWith('/api/v1/change-catalog/'+(kind==='changes'?'requests':'issues')+'?'));
 const links=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));
 const next=new URL(links.find(x=>x.includes('offset=201')),'https://test.invalid').searchParams;
 for(const [key,value] of Object.entries(search))assert.equal(next.get(key),key==='offset'?'201':value);
 assert.ok(links.some(x=>x.startsWith('/'+kind+'?')&&!x.includes('offset=')));
 assert.ok(!html.includes('name="offset"'));
});
for(const kind of ['changes','issues'])test(kind+' beyond-end retains complete totals; unavailable never fabricates zero',async()=>{
 const {html}=await render(kind,{}, {kind,total:205,items:[],next_offset:null,in_verification:82,ready_for_release:82});
 assert.ok(html.includes('205')&&html.includes('No matching records on this page.')&&!html.includes('Next page'));
 for(const result of [null,{kind:kind==='changes'?'issues':'changes',total:0,items:[]}]){
  const failed=await render(kind,{},result);assert.ok(failed.html.includes('catalog unavailable')&&failed.html.includes('—')&&!failed.html.includes('No matching records'));
 }
});
test('repeated pagination and exact UUID scope are forwarded, without fallback bulk API',async()=>{
 const {calls}=await render('changes',{limit:['1','2'],offset:['0','2'],project_id:['a','b']},null);
 const q=new URL(calls[0],'https://test.invalid').searchParams;
 assert.equal(q.get('limit'),'invalid');assert.equal(q.get('offset'),'invalid');assert.equal(q.get('project_id'),'invalid');
 assert.equal(calls.length,1);
});
test('actual Chinese/English SSR preserves original numbers/titles/links',async()=>{
 const {execFileSync}=require('node:child_process');const tmp=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-change-catalog-'));
 try {
  execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/localized.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',tmp]);
  fs.symlinkSync(path.resolve('node_modules'),path.join(tmp,'node_modules'),'dir');const localized=require(path.join(tmp,'components/localized.js'));
  for(const kind of ['changes','issues'])for(const locale of ['zh','en']){
   const Page=load('components/change-issue-catalog.tsx',async()=>({kind,total:205,next_offset:null,in_verification:82,ready_for_release:82,items:[row]}),localized);
   const element=await Page({kind,search:{}});const html=renderToStaticMarkup(React.createElement(localized.LanguageProvider,{initialLocale:locale},element));
   assert.ok(html.includes(locale==='zh'?(kind==='changes'?'匹配的变更请求':'匹配的问题'):(kind==='changes'?'Matching SCR':'Matching issues')));
   assert.ok(html.includes('205')&&html.includes('Original customer title')&&html.includes('/'+kind+'/'+encodeURIComponent(kind==='changes'?row.request_no:row.issue_no)));
  }
 } finally {fs.rmSync(tmp,{recursive:true,force:true});}
});
