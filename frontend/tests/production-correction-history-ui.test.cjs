const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');const zh=require('../lib/i18n/zh.json');
function load(file,api,language='en',overrides={}){
 const code=ts.transpileModule(fs.readFileSync(path.resolve(file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};new Function('require','module','exports',code)(name=>{
  if(name in overrides)return overrides[name];
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,language==='zh'&&typeof children==='string'?(zh[children]??children):children),LocalizedAttributes:({children})=>children};
  return require(name);
 },m,m.exports);return m.exports.default;
}
const values={release_id:'release-id',version:'Original version',snapshot_id:'snap-id',snapshot_no:'SNAP-1',changeover_id:'co-id',changeover_no:'CO-1',started_at:'2026-10-20T08:00:00Z',ended_at:null,note:'Original note'};
const correction=i=>({id:'correction-'+i,revision:101-i,predecessor_id:'correction-'+(i+1),correction_reason:'Original reason '+i,recorded_at:'2026-10-21T09:00:00Z',audit_event_no:'EVT / '+i,values:{...values,note:'Corrected note '+i}});
const fixture={kind:'batch',record_no:'BATCH / 1',deployment_no:'DEP / 1',stored_status:'ACTIVE',history_state:'LEGACY_CORRECTED',recorded_baseline:{source:'LEGACY_CURRENT',recorded_at:'2026-10-20T09:00:00Z',baseline_event_no:'EVT-BASE',values},effective:{revision:100,head_id:'correction-1',values:{...values,note:'Effective note'}},correction_count:100,limit:50,truncated:true,corrections:Array.from({length:55},(_,i)=>correction(i+1))};
async function render(data=fixture,language='en',kind='batch'){
 const calls=[];const Page=load('components/production-correction-history.tsx',async url=>{calls.push(url);return data},language);
 return {calls,html:renderToStaticMarkup(await Page({kind,deploymentNo:'DEP / 1',recordNo:'BATCH / 1'}))};
}
for(const language of ['en','zh'])test(`${language}: original and effective batch facts remain distinct, bounded and read-only`,async()=>{
 const {calls,html}=await render(fixture,language);
 assert.deepEqual(calls,['/api/v1/deployments/DEP%20%2F%201/batches/BATCH%20%2F%201/history']);
 for(const text of ['Original note','Effective note','Corrected note 1','Original reason 1','correction-1','correction-2','2026-10-20T08:00:00Z','2026-10-21T09:00:00Z','/activity/EVT%20%2F%201','/activity/EVT-BASE','/deployments/DEP%20%2F%201','100'])assert.ok(html.includes(text),text);
 for(const label of ['LEGACY_CURRENT','LEGACY_CORRECTED','Recorded baseline','Effective recorded facts','Current revision','Append-only corrections','This bounded view shows at most 50 corrections; older records are not deleted.'])assert.ok(html.includes(language==='zh'?zh[label]:label),label);
 assert.ok(html.includes('Original reason 50'));assert.ok(!html.includes('Original reason 51'));assert.ok(html.indexOf('Original reason 1')<html.indexOf('Original reason 50'));
 assert.ok(!/<form|<button|name="request_id"/.test(html));
});
test('changeover facts and endpoint are distinct from batch software',async()=>{
 const co={from_release_id:'from-id',from_version:'from-v',to_release_id:'to-id',to_version:'to-v',changed_at:'2026-10-20T07:00:00Z',note:'Original co note'};
 const data={...fixture,kind:'changeover',recorded_baseline:{...fixture.recorded_baseline,values:co},effective:{...fixture.effective,values:{...co,note:'Effective co note'}},corrections:[{...correction(1),values:co}]};
 const {calls,html}=await render(data,'en','changeover');assert.match(calls[0],/\/changeovers\//);
 for(const text of ['Changeover correction history','from-id','from-v','to-id','to-v','Original co note','Effective co note','2026-10-20T07:00:00Z'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('SNAP-1'));
});
test('missing baseline and empty ledger do not invent historical evidence',async()=>{
 const {html}=await render({...fixture,history_state:'NOT_RECORDED',recorded_baseline:null,correction_count:0,truncated:false,corrections:[],effective:{revision:0,head_id:null,values}});
 assert.ok(html.includes('No baseline recorded. Current stored values are not a reconstructed history.'));
 assert.ok(html.includes('No correction records returned.'));assert.ok(!html.includes('LEGACY_CURRENT'));assert.ok(!html.includes('/activity/'));assert.ok(!html.includes('older records'));
});
for(const mismatch of [null,{...fixture,deployment_no:'FOREIGN-DEP'},{...fixture,record_no:'FOREIGN-CHILD'},{...fixture,kind:'changeover'}])test(`unavailable or mismatched route never substitutes foreign facts: ${mismatch?.deployment_no}/${mismatch?.record_no}/${mismatch?.kind}`,async()=>{
 const {html}=await render(mismatch);assert.ok(html.includes('Correction history unavailable'));assert.ok(!html.includes('Original note'));assert.ok(!html.includes('FOREIGN'));assert.ok(!html.includes('/activity/'));
});
test('raw evidence is escaped and never translated even when it matches a known label',async()=>{
 const {html}=await render({...fixture,effective:{...fixture.effective,values:{...values,note:'Note'}},corrections:[{...correction(1),correction_reason:'<script>alert("x")</script>'}]},'zh');
 assert.ok(html.includes('>Note<'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
});
for(const [kind,plural,param] of [['batch','batches','batchNo'],['changeover','changeovers','changeoverNo']])test(`${kind} nested route passes exact parent and child`,async()=>{
 let seen;const Component=props=>{seen=props;return React.createElement('p',null,'history')};
 const Page=load(`app/deployments/[id]/${plural}/[${param}]/history/page.tsx`,null,'en',{'../../../../../../components/production-correction-history':Component});
 renderToStaticMarkup(await Page({params:Promise.resolve({id:'DEP / 1',[param]:'CHILD / 1'})}));assert.deepEqual(seen,{kind,deploymentNo:'DEP / 1',recordNo:'CHILD / 1'});
});
for(const kind of ['batches','changeovers'])test(`${kind} catalog exposes encoded parent-child history link`,async()=>{
 const row={id:'id',record_no:'CHILD / 1',status:'ACTIVE',context_consistent:true,binding_flags:[],deployment:{id:'dep',deployment_no:'DEP / 1',status:'MATCH'},recorded_at:null};
 const Page=load('components/production-catalog.tsx',async()=>({total:1,status_counts:{},items:[row],next_offset:null,notice:'notice'}));
 const html=renderToStaticMarkup(await Page({kind,filters:{}}));assert.ok(html.includes(`/deployments/DEP%20%2F%201/${kind}/CHILD%20%2F%201/history`));
});
test('batch detail links to history only with a resolved parent',async()=>{
 const data={id:'id',batch_no:'BATCH / 1',status:'ACTIVE',started_at:null,ended_at:null,note:null,software:{},deployment:{deployment_no:'DEP / 1',status:'MATCH',actual:null},authorization:null,changeover:null,matches:{}};
 const file='app/production/batches/[batchNo]/page.tsx';const Page=load(file,async()=>data);
 const html=renderToStaticMarkup(await Page({params:Promise.resolve({batchNo:'BATCH / 1'})}));assert.ok(html.includes('/deployments/DEP%20%2F%201/batches/BATCH%20%2F%201/history'));
 const Missing=load(file,async()=>({...data,deployment:null}));assert.ok(!renderToStaticMarkup(await Missing({params:Promise.resolve({batchNo:'BATCH / 1'})})).includes('/history'));
});
for (const malformed of [
 {...fixture,effective:null}, {...fixture,effective:{...fixture.effective,values:null}},
 {...fixture,recorded_baseline:{...fixture.recorded_baseline,values:null}},
 {...fixture,corrections:[null]}, {...fixture,effective:{...fixture.effective,values:{...values,note:{bad:'object'}}}}, {...fixture,corrections:[{...correction(1),correction_reason:{bad:'object'}}]}, {...fixture,corrections:[{...correction(1),values:null}]},
]) test('incomplete history projection fails closed instead of crashing SSR',async()=>{
 const {html}=await render(malformed);assert.ok(html.includes('Correction history unavailable'));assert.ok(!html.includes('Original note'));
});
