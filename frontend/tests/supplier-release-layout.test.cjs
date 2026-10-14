const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function load(file, api){
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};
 new Function('require','module','exports',code)(name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,children)};
  return require(name);
 },m,m.exports);return m.exports;
}
const row=(id,code='S')=>({id,version:'5.0',status:'RELEASED',software:{name:'BMS',code:'B'},supplier:{name:'Same name',code}});
const catalog={kind:'standard',total:105,next_offset:3,items:[row('s1'),row('s2'),row('s3','T')]};
const appPage=id=>({release_id:id,total:30,next_offset:10,items:[{id:'new',version:'2.0',status:'DRAFT'},{id:'old',version:'10.0',status:'RELEASED'}]});
const links=html=>[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));
async function renderCatalog(search={},parent=catalog,child=appPage){
 const calls=[];const Page=load('components/supplier-release-catalog.tsx',async url=>{calls.push(url);return url.includes('/release-catalog/')?parent:child(decodeURIComponent(url.split('/id/')[1].split('/')[0]));}).default;
 return {calls,html:renderToStaticMarkup(await Page({search}))};
}
test('supplier identity grouping, default disclosure and exact release links preserve API version order',async()=>{
 const {html,calls}=await renderCatalog();
 assert.equal((html.match(/class="supplier-release-card"/g)||[]).length,2);
 assert.equal((html.match(/<details open=""[^>]*supplier-release-card/g)||[]).length,2);
 assert.equal((html.match(/<details[^>]*standard-software-card/g)||[]).length,3);
 assert.ok(!/<details[^>]*open=""[^>]*standard-software-card/.test(html));
 for(const id of ['s1','s2','s3'])assert.ok(links(html).includes('/releases/standard/'+id));
 assert.ok(links(html).includes('/releases/application/new'));
 assert.ok(html.indexOf('ASR 2.0')<html.indexOf('ASR 10.0'));
 assert.ok(links(html).includes('/demo/releases')&&links(html).includes('/demo/zfi'));
 assert.equal(calls.length,4);assert.ok(calls.slice(1).every(x=>x.endsWith('limit=10')));
});
test('child pagination retains catalog filters, opens selected card only and never reads arbitrary parent',async()=>{
 const {html,calls}=await renderCatalog({q:'_%',status:'DRAFT',limit:'3',offset:'8',applications_for:'s2',application_offset:'10',ignored:'x'});
 assert.equal(new URL(calls[0],'https://test').searchParams.has('ignored'),false);
 assert.equal(calls.filter(x=>x.includes('offset=10')).length,1);
 assert.ok(/id="standard-software-s2" open=""/.test(html));
 const child=links(html).find(x=>x.includes('application_offset=10')&&x.includes('applications_for=s1'));
 const q=new URL(child,'https://test').searchParams;assert.equal(q.get('q'),'_%');assert.equal(q.get('offset'),'8');
 const foreign=await renderCatalog({applications_for:'foreign',application_offset:'99'});assert.ok(!foreign.calls.some(x=>x.includes('foreign')||x.includes('offset=99')));
});
test('empty, failed and foreign child responses do not invent versions or zero records',async()=>{
 const empty=await renderCatalog({}, {...catalog,items:[]});assert.equal(empty.calls.length,1);assert.ok(empty.html.includes('No releases on this page.'));
 const failed=await renderCatalog({},null);assert.ok(failed.html.includes('Release catalog unavailable'));
 const foreign=await renderCatalog({},catalog,()=>({...appPage('foreign'),items:[]}));assert.ok(foreign.html.includes('Application release page unavailable.'));assert.ok(!foreign.html.includes('Recorded count:'));
});
const approval={id:'apr',approval_no:'APR-1',target_type:'RELEASE',target_id:'s1',status:'APPROVED',submitted_by:'Reviewer',submitted_at:'2026-10-01',step_count:4,action_count:3,release:{id:'s1'},snapshot:{id:'snap-id',snapshot_no:'SN-1'}};
const snapshot={id:'snap-id',release_id:'s1',snapshot_no:'SN-1',is_current_snapshot:true};
async function renderReview(search={},override={},kind='standard'){
 const calls=[];const Review=load('components/release-review-records.tsx',async url=>{
  calls.push(url);let key=url.includes('/governance/')?'approvals':url.includes('/summary')?'summary':url.includes('/artifacts?')?'files':'history';
  if(Object.hasOwn(override,key))return override[key];
  return {approvals:{total:1,next_offset:20,items:[approval]},summary:snapshot,files:{release_id:'s1',snapshot_id:'snap-id',snapshot_no:'SN-1',total:21,next_offset:20,items:[{id:'f1',filename:'firmware.bin',component_code:'B',component_version:'5',artifact_type:'BINARY',sha256:'abc'}]},history:{release:{id:'s1',type:'STANDARD'},total:1,items:[snapshot]}}[key];
 }).ReleaseReviewRecords;
 return {calls,html:renderToStaticMarkup(await Review({releaseId:'s1',search,kind}))};
}
test('detail displays files and approvals with exact snapshot pin and independent paging',async()=>{
 const {html,calls}=await renderReview({component_offset:'4',approval_offset:'20'});
 assert.ok(html.includes('firmware.bin')&&html.includes('Reviewer')&&html.includes('Approval records'));
 assert.ok(links(html).includes('/approvals/APR-1'));assert.ok(calls.some(x=>x.includes('snapshot_id=snap-id&limit=20')));
 const fileLink=links(html).find(x=>x.includes('files_offset=20'));const q=new URL(fileLink,'https://test').searchParams;
 assert.equal(q.get('files_snapshot_id'),'snap-id');assert.equal(q.get('files_snapshot_no'),'SN-1');assert.equal(q.get('approval_offset'),'20');assert.equal(q.get('component_offset'),'4');
 const pinned=await renderReview({files_snapshot_no:'SN-1',files_snapshot_id:'snap-id',files_offset:'20'});assert.equal(pinned.calls.length,3);assert.ok(!pinned.calls.some(x=>x.includes('/snapshots?')));
});
test('foreign files and approval targets fail closed; incomplete pins never select latest',async()=>{
 for(const override of [{summary:{...snapshot,release_id:'foreign'}},{files:{release_id:'s1',snapshot_id:'foreign',items:[]}}]){const {html}=await renderReview({},override);assert.ok(html.includes('Software files unavailable.'));assert.ok(!html.includes('firmware.bin'));}
 const {html}=await renderReview({}, {approvals:{items:[{...approval,target_id:'foreign'}],total:1,next_offset:null}});assert.ok(html.includes('Approval records unavailable.'));assert.ok(!html.includes('APR-1'));
 const invalid=await renderReview({files_snapshot_id:'snap-id'});assert.equal(invalid.calls.length,1);assert.ok(invalid.html.includes('Software files unavailable.'));
});
test('no snapshot and empty approvals remain distinct from unavailable; application reuses existing files',async()=>{
 const {html,calls}=await renderReview({}, {history:{release:{id:'s1',type:'STANDARD'},total:0,items:[]},approvals:{total:0,items:[],next_offset:null}});
 assert.equal(calls.length,2);assert.ok(html.includes('No snapshot is available')&&html.includes('No approval records on this page.'));
 const app=await renderReview({}, {},'application');assert.equal(app.calls.length,1);assert.ok(!app.html.includes('Software files'));assert.ok(app.html.includes('Approval records'));
});
test('child reads are bounded to the visible catalog page with at most four concurrent GETs',async()=>{
 let active=0,max=0,reads=0;
 const Page=load('components/supplier-release-catalog.tsx',async url=>{
  if(url.includes('/release-catalog/'))return {...catalog,items:Array.from({length:9},(_,i)=>row('s'+i))};
  active++;reads++;max=Math.max(max,active);await new Promise(resolve=>setTimeout(resolve,2));active--;
  return appPage(url.split('/id/')[1].split('/')[0]);
 }).default;
 await Page({search:{}});assert.equal(reads,9);assert.equal(max,4);
});
test('new directory and detail labels translate using the actual localization component',async()=>{
 const path=require('node:path'),{execFileSync}=require('node:child_process');
 const tmp=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-supplier-i18n-'));
 try {
  execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/localized.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',tmp]);
  fs.symlinkSync(path.resolve('node_modules'),path.join(tmp,'node_modules'),'dir');
  const localized=require(path.join(tmp,'components/localized.js'));
  function actual(file,api){
   const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,m={exports:{}};
   new Function('require','module','exports',code)(name=>name==='next/link'?({href,children})=>React.createElement('a',{href},children):name.endsWith('/localized')?localized:name.endsWith('/api')?{apiGet:api}:require(name),m,m.exports);return m.exports;
  }
  const directory=await actual('components/supplier-release-catalog.tsx',async url=>url.includes('/release-catalog/')?catalog:appPage(url.split('/id/')[1].split('/')[0])).default({search:{}});
  const review=await actual('components/release-review-records.tsx',async url=>url.includes('/governance/')?{total:1,items:[approval],next_offset:null}:{release:{id:'s1',type:'STANDARD'},total:0,items:[]}).ReleaseReviewRecords({releaseId:'s1',kind:'standard',search:{}});
  for(const locale of ['zh','en']){
   const html=renderToStaticMarkup(React.createElement(localized.LanguageProvider,{initialLocale:locale},directory,review));
   for(const label of locale==='zh'?['展开','收起','软件文件','审批记录','提交人']:['Expand','Collapse','Software files','Approval records','Submitted by'])assert.ok(html.includes(label),label);
   for(const raw of ['BMS','Same name','/releases/standard/s1','/approvals/APR-1','Reviewer'])assert.ok(html.includes(raw),raw);
  }
 } finally {fs.rmSync(tmp,{recursive:true,force:true});}
});
