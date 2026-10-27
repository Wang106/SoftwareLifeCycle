const fs=require('node:fs'),path=require('node:path');
const root=path.resolve('.');
const {test}=require('node:test'),assert=require('node:assert/strict');
const ts=require(root+'/node_modules/typescript'),React=require(root+'/node_modules/react');
const {renderToStaticMarkup}=require(root+'/node_modules/react-dom/server');
const baseFixture={id:'batch-id',batch_no:'BATCH-QA',status:'ACTIVE',started_at:null,ended_at:null,note:'Note',software:{release_id:null,version:null,snapshot_id:null,snapshot_no:null},deployment:null,authorization:null,changeover:null,matches:{authorized_release:null,authorized_snapshot:null,deployed_release:null,deployed_snapshot:null,changeover_deployment:null}};
let fixture, calls;
const cache=new Map();
function load(file){if(cache.has(file))return cache.get(file);const m={exports:{}};const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;new Function('require','module','exports',code)(name=>{if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);if(name.endsWith('/api'))return {apiGet:async url=>{calls.push(url);return fixture}};if(name.startsWith('.')){let p=path.resolve(path.dirname(file),name);if(p.endsWith('.json'))return require(p);if(fs.existsSync(p+'.ts'))p+='.ts';else if(fs.existsSync(p+'.tsx'))p+='.tsx';return load(p);}return require(root+'/node_modules/'+name);},m,m.exports);cache.set(file,m.exports);return m.exports;}

const {LanguageProvider}=load(root+'/components/localized.tsx');
const Page=load(root+'/app/production/batches/[batchNo]/page.tsx').default;
const zh=require('../lib/i18n/zh.json');
async function render(value,locale){fixture=value;calls=[];const html=renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},await Page({params:Promise.resolve({batchNo:'Batch / ? #'})})));assert.deepEqual(calls,['/api/v1/batches/Batch%20%2F%20%3F%20%23']);return html;}
for(const locale of ['zh','en']){
 for(const note of ['Note','ACTIVE','  Note  ','Recorded {0}','<script>alert("x")</script> & evidence'])test(`raw note stays exact and escaped: ${locale} ${note}`,async()=>{
  const html=await render({...baseFixture,note},locale);
  const escaped=renderToStaticMarkup(React.createElement('span',null,note));
  assert.ok(html.includes('<span>'+(locale==='zh'?zh.Note:'Note')+'</span><b>'+escaped+'</b>'));
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<form'));assert.ok(!html.includes('<textarea'));
 });
 test(`identifiers and compound software stay raw; status stays bilingual: ${locale}`,async()=>{
  const value={...baseFixture,batch_no:'ACTIVE',software:{version:'Note',snapshot_no:'Dashboard'},deployment:{deployment_no:'Note / ? #',status:'ACTIVE',actual:{version:'ACTIVE',snapshot_no:'Note'}},authorization:{authorization_no:'Dashboard / ?',status:'APPROVED',batch_limit:0},changeover:{changeover_no:'Note',status:'ACTIVE'}};
  const html=await render(value,locale);
  for(const raw of ['<h1><span>ACTIVE</span></h1>','<b><span>Note</span></b>','<b><span>Dashboard</span></b>','<span>ACTIVE · Note</span>','<span>Note / ? #</span>','<span>Dashboard / ?</span>'])assert.ok(html.includes(raw),raw);
  assert.ok(html.includes('<span class="status pass">'+(locale==='zh'?zh.ACTIVE:'ACTIVE')+'</span>'));
  assert.ok(html.includes('<span>Note</span> · '+(locale==='zh'?zh.ACTIVE:'ACTIVE')));
  assert.ok(html.includes('/deployments/Note%20%2F%20%3F%20%23/batches/ACTIVE/history'));
  assert.ok(html.includes('/distribution/authorizations/Dashboard%20%2F%20%3F'));
  assert.ok(html.includes('<b>0</b>'));
 });
 test(`missing fields retain existing bilingual fallbacks: ${locale}`,async()=>{
  const html=await render({...baseFixture,note:null},locale);
  for(const label of ['Missing deployment','Not reported','Missing authorization','None linked','Not recorded'])assert.ok(html.includes(locale==='zh'?zh[label]:label),label);
  assert.ok(html.includes('<b><span>—</span></b>'));assert.ok(!html.includes('/history'));
 });
 test(`unavailable response does not invent record evidence: ${locale}`,async()=>{
  const html=await render(null,locale);assert.ok(html.includes(locale==='zh'?zh['Batch unavailable']:'Batch unavailable'));assert.ok(html.includes('href="/production/batches"'));assert.ok(!html.includes('BATCH-QA'));
 });
}
