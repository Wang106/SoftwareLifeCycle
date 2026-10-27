const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),zh=require('../lib/i18n/zh.json');
function load(file,api,locale='en',links=[]){
 const code=ts.transpileModule(fs.readFileSync(path.resolve(file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}};new Function('require','module','exports',code)(name=>{
  if(name==='next/link')return props=>{links.push(props);return React.createElement('a',{href:props.href},props.children);};
  if(name.endsWith('/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,locale==='zh'&&typeof children==='string'?(zh[children]??children):children)};
  if(name.endsWith('/production-correction-history-loading'))return {__esModule:true,default:load('components/production-correction-history-loading.tsx',api,locale,links)};
  return require(name);
 },m,m.exports);return m.exports.default;
}
for(const [kind,plural,param] of [['batch','batches','batchNo'],['changeover','changeovers','changeoverNo']]){
 for(const locale of ['zh','en'])test(`${kind}/${locale}: streamed loading is accessible and does not fabricate evidence or requests`,()=>{
  let calls=0;const Page=load(`app/deployments/[id]/${plural}/[${param}]/history/loading.tsx`,()=>{calls++;},locale);
  const html=renderToStaticMarkup(React.createElement(Page));assert.equal(calls,0);
  for(const label of ['Loading correction history','Waiting for read-only history. No recorded facts have been confirmed yet.'])assert.ok(html.includes(locale==='zh'?zh[label]:label));
  assert.match(html,/role="status"/);assert.match(html,/aria-busy="true"/);assert.match(html,/aria-live="polite"/);
  assert.ok(!/<form|<button|<a |<script|request_id|Current revision|Recorded baseline/.test(html));
 });
 for(const locale of ['zh','en'])test(`${kind}/${locale}: unavailable read has bounded deadline and explicit encoded same-history retry only`,async()=>{
  const calls=[],links=[],deploymentNo='DEP / ?#原始',recordNo='CHILD / ?#原始';
  const Page=load('components/production-correction-history.tsx',async(...args)=>{calls.push(args);return null;},locale,links);
  const html=renderToStaticMarkup(await Page({kind,deploymentNo,recordNo}));
  assert.deepEqual(calls,[[`/api/v1/deployments/${encodeURIComponent(deploymentNo)}/${plural}/${encodeURIComponent(recordNo)}/history`,{timeoutMs:15000}]]);
  const href=`/deployments/${encodeURIComponent(deploymentNo)}/${plural}/${encodeURIComponent(recordNo)}/history`,retry=links.find(link=>link.href===href);
  assert.equal(retry,undefined);assert.ok(html.includes(`<a href="${href}">`));assert.ok(html.includes(locale==='zh'?zh['Read this history again']:'Read this history again'));
  assert.ok(!/<form|<button|<script|request_id|\/correct|Recorded baseline|Current revision/.test(html));assert.equal(calls.length,1);
 });
 test(`${kind}: foreign evidence remains unavailable and retry never follows foreign target`,async()=>{
  const links=[];const Page=load('components/production-correction-history.tsx',async()=>({kind,deployment_no:'FOREIGN',record_no:'SECRET'}),'en',links);
  const html=renderToStaticMarkup(await Page({kind,deploymentNo:'OWN',recordNo:'CHILD'}));
  assert.ok(!/FOREIGN|SECRET/.test(html));assert.ok(html.includes(`<a href="/deployments/OWN/${plural}/CHILD/history">`));assert.ok(!links.some(link=>link.href===`/deployments/OWN/${plural}/CHILD/history`));
 });
}
