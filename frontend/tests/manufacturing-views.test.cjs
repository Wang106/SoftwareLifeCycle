const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');const zh=require('../lib/i18n/zh.json');
function loader(api,language='en'){
 const cache={};function load(file){
  if(cache[file])return cache[file].exports;
  const m={exports:{}};cache[file]=m;
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  new Function('require','module','exports',code)(name=>{
   if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
   if(name.endsWith('/api'))return {apiGet:api};
   if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,language==='zh'&&typeof children==='string'?(zh[children]??children):children)};
   if(name.startsWith('.'))return load(path.resolve(path.dirname(file),name)+(name.endsWith('manufacturing-views')?'.ts':'.tsx'));
   return require(name);
  },m,m.exports);return m.exports;
 }return file=>load(path.resolve(file)).default;
}
const id='abcdefab-1234-1234-1234-123456789abc';const lineId='b1234567-1234-1234-1234-123456789abc';const snapshot='c1234567-1234-1234-1234-123456789abc';
const site={kind:'manufacturing-site',id,site_code:'SITE / A',name:'Original factory',status:'ACTIVE',region:'APAC',customer_id:'customer-uuid',customer_code:'CUS-1',customer_name:'Original customer',project_id:'project-uuid',project_code:'PRJ-1',project_name:'Original project',line_count:121,deployed_line_count:100,matching_line_count:90,attention_line_count:10,approved_authorization_line_count:17,first_deployment_id:'dep-uuid',first_deployment_no:'DEP-1',first_authorization_id:'auth-uuid',first_authorization_no:'AUTH-1',first_authorization_status:'APPROVED',first_expected_release_id:'release-uuid',first_expected_version:'9.2',first_expected_type:'APPLICATION',first_expected_snapshot_id:snapshot,first_expected_snapshot_no:'SNAP-1',first_changeover_id:'changeover-uuid',first_changeover_changeover_no:'CHANGE-1',first_changeover_status:'PLANNED',context_batch_id:'batch-uuid',context_batch_batch_no:'BATCH-1',context_batch_status:'COMPLETED',context_batch_note:'Original historical note'};
const line={id:lineId,line_code:'LINE-1',name:'Original line',status:'ACTIVE',deployment_id:'dep-uuid',deployment_no:'DEP-1',deployment_status:'MATCH',authorization_id:'auth-uuid',authorization_no:'AUTH-1',authorization_status:'APPROVED',expected_release_id:'release-uuid',expected_version:'9.2',expected_type:'APPLICATION',expected_snapshot_id:snapshot,expected_snapshot_no:'SNAP-1',actual_release_id:'release-uuid',actual_release_version:'9.2',actual_type:'STANDARD',actual_snapshot_id:snapshot,actual_snapshot_no:'SNAP-1',actual_version:2,deployed_at:'Original time'};
const page={kind:'manufacturing-lines',site_id:id,site_code:site.site_code,total:121,limit:1,offset:0,next_offset:1,items:[line]};
async function profile(summary=site,child=page,search={},identifier=id,language='en'){
 const calls=[];const Page=loader(async url=>{calls.push(url);return url.endsWith('/summary')?summary:child;},language)('components/manufacturing-profile.tsx');
 return {calls,html:renderToStaticMarkup(await Page({identifier,search}))};
}
test('catalog complete counts and exact sites retain all filters through paging',async()=>{
 const calls=[];const Page=loader(async url=>{calls.push(url);return {kind:'manufacturing-sites',total:205,next_offset:201,items:[site]};})('components/manufacturing-catalog.tsx');
 const html=renderToStaticMarkup(await Page({search:{q:'_%',status:'ACTIVE',region:'APAC',customer_id:'customer-uuid',project_id:'project-uuid',limit:'1',offset:'200'}}));
 assert.equal(calls.length,1);assert.ok(calls[0].startsWith('/api/v1/manufacturing-views/sites?'));
 for(const key of ['205','121','90','10','Original factory','/manufacturing/sites/'+id,'offset=201','customer_id=customer-uuid','project_id=project-uuid'])assert.ok(html.includes(key),key);
 assert.ok(!calls[0].startsWith('/api/v1/manufacturing/sites'));
});
test('beyond-end catalog retains count; failures and wrong response kind remain unknown',async()=>{
 for(const data of [null,{kind:'wrong',total:205,items:[site]},{kind:'manufacturing-sites',total:205,next_offset:null,items:[]}]){
  const Page=loader(async()=>data)('components/manufacturing-catalog.tsx');const html=renderToStaticMarkup(await Page({search:{limit:['0','1']}}));
  assert.ok(html.includes(data?.kind==='manufacturing-sites'?'205':'Manufacturing catalog unavailable'));assert.ok(!html.includes('Next page'));
 }
});
test('profile uses UUID pin and exact routes supported by existing detail contracts',async()=>{
 const {calls,html}=await profile();assert.equal(calls.length,2);assert.match(calls[1],new RegExp('site_id='+id));
 for(const key of ['121','17','Original historical note','COMPLETED','line='+lineId,'operation=deployment','/deployments/DEP-1','/distribution/authorizations/AUTH-1','/production/batches/BATCH-1','/releases/application/release-uuid','/releases/standard/release-uuid','/snapshots/SNAP-1?manifest_snapshot_id='+snapshot,'offset=1'])assert.ok(html.includes(key),key);
 assert.ok(!html.includes('/deployments/dep-uuid'));assert.ok(!html.includes('Production scope approved'));
});
test('profile accepts business code and canonical uppercase or compact UUID identities',async()=>{
 for(const identifier of [site.site_code,id.toUpperCase(),id.replaceAll('-','')]){
  const {calls,html}=await profile(site,page,{},identifier);assert.equal(calls.length,2);assert.ok(html.includes('Original line'));
 }
});
test('missing mismatched or foreign parent stops all line reads',async()=>{
 for(const parent of [null,{...site,kind:'wrong'},{...site,id:'foreign',site_code:'foreign'}]){
  const {calls,html}=await profile(parent);assert.equal(calls.length,1);assert.ok(html.includes('Manufacturing site unavailable'));assert.ok(!html.includes('121'));
 }
});
test('failed foreign site or code lines keep parent counts and historical context',async()=>{
 for(const child of [null,{...page,site_id:'foreign'},{...page,site_code:'foreign'},{...page,kind:'wrong'}]){
  const {html}=await profile(site,child);assert.ok(html.includes('121')&&html.includes('Original historical note')&&html.includes('Manufacturing lines unavailable'));assert.ok(!html.includes('Original line'));
 }
});
test('beyond-end child lines never replace full counts or context with zero',async()=>{
 const {html}=await profile(site,{...page,next_offset:null,items:[]},{offset:'100000'});
 assert.ok(html.includes('121')&&html.includes('No records on this page.')&&html.includes('BATCH-1'));assert.ok(!html.includes('Next page'));
});
test('repeated page values remain invalid; reset and next retain page size',async()=>{
 const {calls,html}=await profile(site,page,{limit:'1',offset:['0','1']});assert.match(calls[1],/offset=invalid/);assert.ok(html.includes('limit=1')&&html.includes('offset=1'));
});
test('empty site does not assert software match or active production batch',async()=>{
 const summary={...site,line_count:0,matching_line_count:0,approved_authorization_line_count:0,first_authorization_no:null,first_authorization_id:null,first_deployment_no:null,first_changeover_changeover_no:null,context_batch_batch_no:null,context_batch_status:null,context_batch_note:null};
 const {html}=await profile(summary,{...page,total:0,next_offset:null,items:[]});assert.ok(html.includes('CHECK')&&html.includes('No records on this page.'));assert.ok(!html.includes('BATCH-1'));
});
test('partial actual report remains not reported; missing release metadata preserves raw stored UUID',async()=>{
 const {html}=await profile(site,{...page,items:[{...line,actual_snapshot_id:null,expected_type:null,expected_version:null,expected_snapshot_no:null}]});
 assert.ok(html.includes('Not reported')&&html.includes('release-uuid')&&html.includes(snapshot));assert.ok(!html.includes('/releases/standard/release-uuid'));
});
test('Chinese and English manufacturing labels preserve business names and request identifiers',async()=>{
 for(const language of ['zh','en']){
  const {html}=await profile(site,page,{},id,language);assert.ok(html.includes(language==='zh'?zh['Line software status']:'Line software status'));
  assert.ok(html.includes('Original factory')&&html.includes(lineId)&&html.includes('Original historical note'));
 }
});
