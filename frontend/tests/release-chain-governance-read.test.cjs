'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'), ts=require('typescript'), React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function compile(file,req){
 const m={exports:{}};
 const js=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 new Function('require','module','exports',js)(req,m,m.exports);return m.exports;
}
const core=compile('lib/release-chain-governance.ts',require);
const i18n=compile('lib/i18n.ts',n=>n.endsWith('zh.json')?require('../lib/i18n/zh.json'):require('../lib/i18n/templates.json'));
const id='11111111-1111-4111-8111-111111111111';
function event(kind,index=1){const key=`22222222-2222-4222-8222-${String(index).padStart(12,'0')}`;return {id:key,revocation_no:'RCR-'+key.replaceAll('-',''),target_kind:kind,reason:'<script>Dashboard</script>\n审批原文',revoked_by:'Dashboard',revoked_at:'2026-10-20T12:00:00Z'};}
function observation(own=null,ancestors=[]){return {recorded_status:'APPROVED',governance_state:own?'REVOKED':ancestors.length?'BLOCKED_BY_ANCESTOR':'ACTIVE',eligible_for_new_work:!own&&!ancestors.length,self_revocation:own,ancestor_revocations:ancestors};}
async function render(kind='release',data=observation(),locale='en',targetId=id){
 const calls=[];
 const translate=c=>typeof c==='string'?i18n.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const page=compile('app/governance/[kind]/[targetId]/page.tsx',n=>{
  if(n==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(n.endsWith('/lib/api'))return {apiGet:async(...args)=>{calls.push(args);return data;}};
  if(n.endsWith('/lib/release-chain-governance'))return core;
  if(n.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,translate(children))};
  return require(n);
 });
 return {html:renderToStaticMarkup(await page.default({params:Promise.resolve({kind,targetId})})),calls};
}
for(const kind of core.governanceKinds)test('exact '+kind+' read uses one bounded GET and no form',async()=>{
 const {html,calls}=await render(kind.toLowerCase());
 assert.deepEqual(calls,[[`/api/v1/governance/${kind}/${id}`,{timeoutMs:10000}]]);
 assert.ok(html.includes('No revocation recorded on this path.')&&html.includes('APPROVED'));
 assert.ok(html.includes('does not establish approval'));
 assert.ok(!/<form|<button|operation=|\/commands|method="post"/.test(html));
});
for(const locale of ['zh','en'])test('own and ancestor records are distinct, bilingual, preserve raw evidence '+locale,async()=>{
 const own=event('AUTHORIZATION',4), ancestors=[event('RELEASE'),event('DELIVERY_PACKAGE',2),event('DISTRIBUTION',3)];
 const {html}=await render('authorization',observation(own,ancestors),locale);
 assert.ok(html.includes(locale==='zh'?'发布链治理':'Release-chain governance'));
 assert.ok(html.includes(locale==='zh'?'生产授权':'AUTHORIZATION'));
 assert.ok(html.includes(locale==='zh'?'对象自身撤销':'Exact target revocation'));
 assert.equal((html.match(/EVT-RCR-/g)||[]).length,4);
 assert.ok(html.includes('/activity/EVT-RCR-'+own.id.replaceAll('-','')));
 assert.ok(html.includes('&lt;script&gt;Dashboard&lt;/script&gt;')&&html.includes('>Dashboard</td>'));
 assert.ok(!html.includes('<script>')&&html.includes('审批原文')&&html.includes('2026-10-20T12:00:00.000Z'));
});
test('ancestor blocker never implies an own revocation',async()=>{
 const {html}=await render('distribution',observation(null,[event('RELEASE')]));
 assert.ok(html.includes('BLOCKED_BY_ANCESTOR')&&html.includes('Ancestor revocation')&&!html.includes('Exact target revocation'));
});
test('unresolved ancestry is distinct from confirmed empty history',async()=>{
 const {html}=await render('authorization',{...observation(),governance_state:'UNRESOLVED',eligible_for_new_work:false});
 assert.ok(html.includes('Authority ancestry is unresolved.')&&!html.includes('No revocation recorded on this path.'));
});
test('invalid kind or UUID performs zero reads',async()=>{
 for(const [kind,target] of [['other',id],['release','../secret'],['authorization',id+'?x=1']]){
  const {html,calls}=await render(kind,observation(),'en',target);
  assert.equal(calls.length,0);assert.ok(html.includes('Governance observation unavailable'));
 }
});
test('unavailable malformed contradictory and oversized responses fail closed',async()=>{
 const original=observation(event('AUTHORIZATION'));
 const bad=[null,[],{}, {...original,eligible_for_new_work:true}, {...original,governance_state:'ACTIVE'},
  {...original,self_revocation:event('RELEASE')}, {...original,ancestor_revocations:[event('AUTHORIZATION',2)]},
  {...original,ancestor_revocations:[event('RELEASE',2),event('RELEASE',3)]},
  {...original,self_revocation:{...original.self_revocation,revocation_no:'foreign'}},
  {...original,self_revocation:{...original.self_revocation,revoked_at:'not-a-date'}},
  {...original,self_revocation:{...original.self_revocation,reason:'x'.repeat(4001)}},
  {...original,ancestor_revocations:Array.from({length:4},(_,n)=>event('RELEASE',n+10))}];
 for(const value of bad){const {html,calls}=await render('authorization',value);assert.equal(calls.length,1);assert.ok(html.includes('Governance observation unavailable')&&!html.includes('/activity/'));}
});
test('UUIDs normalize before fixed-path read and independent same-version entities remain distinct',async()=>{
 const other='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
 const {calls}=await render('RELEASE',observation(),'en',other.toUpperCase());
 assert.equal(calls[0][0],'/api/v1/governance/RELEASE/'+other);
 assert.notEqual(calls[0][0],'/api/v1/governance/RELEASE/'+id);
});
test('five existing detail pages link exact object identities without expanding requests',()=>{
 for(const [file,kind,entity] of [
  ['releases/standard/[releaseId]','release','profile'],['releases/application/[releaseId]','release','profile'],
  ['distribution/deliveries/[packageNo]/[revision]','delivery_package','delivery'],
  ['distribution/distributions/[distributionNo]','distribution','record'],
  ['distribution/authorizations/[authorizationNo]','authorization','authorization']]){
  const source=fs.readFileSync('app/'+file+'/page.tsx','utf8');
  assert.ok(source.includes('href={`/governance/'+kind+'/${'+entity+'.id}`}'));
  assert.ok(source.includes('prefetch={false}'));
 }
});
