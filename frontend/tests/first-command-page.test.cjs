'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync('app/commands/page.tsx','utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
async function page({configured=true,governanceConfigured=false,distributionConfigured=false,productionConfigured=false,evidenceConfigured=false,resourceConfigured=false,identity={read_only_mode:false},cookies=[{value:'opaque'}],query={}}={}){
 let cookieReads=0,sessionReads=0;const Workbench=()=>null,exports={};
 vm.runInNewContext(compiled,{exports,process:{env:{}},require:name=>name==='next/headers'?{cookies:async()=>{cookieReads++;return{getAll:()=>cookies};}}:
  name==='../../lib/browser-auth'?{authConfig:async()=>({session:{}}),firstSubmissionConfigured:()=>configured,governanceSubmissionConfigured:()=>governanceConfigured,distributionSubmissionConfigured:()=>distributionConfigured,productionSubmissionConfigured:()=>productionConfigured,evidenceSubmissionConfigured:()=>evidenceConfigured,resourceSubmissionConfigured:()=>resourceConfigured}:
  name==='../../lib/browser-session'?{SESSION_COOKIE:'__Host-slc_session',resolveSession:async()=>{sessionReads++;return identity;}}:
  name==='../../components/command-workbench'?{__esModule:true,default:Workbench}:
  name==='../../components/localized'?{Localized:({children})=>children}:
  name==='../../lib/command-draft'?{resourceTypes:['RELEASE']}:require(name)});
 const tree=await exports.default({searchParams:Promise.resolve(query)});
 function nodes(n){return Array.isArray(n)?n.flatMap(nodes):n&&typeof n==='object'?[n,...nodes(n.props?.children)]:[];}
 return {component:nodes(tree).find(n=>n.type===Workbench),cookieReads,sessionReads};
}
test('server gate defaults closed without a session or approved first-command configuration',async()=>{
 const disabled=await page({configured:false});assert.equal(disabled.cookieReads,0);assert.equal(disabled.sessionReads,0);
 assert.equal(disabled.component.props.submissionEnabled,false);assert.equal(disabled.component.props.recoveryEnabled,false);
 const missing=await page({identity:null});assert.equal(missing.component.props.submissionEnabled,false);assert.equal(missing.component.props.recoveryEnabled,false);
});
test('server current session read-only projection independently gates submit and recovery',async()=>{
 for(const read_only_mode of [false,true,undefined]){const r=await page({identity:{read_only_mode,token:'private',principal:{id:'private'}}});
  assert.equal(r.component.props.submissionEnabled,read_only_mode===false);assert.equal(r.component.props.recoveryEnabled,true);
  assert.equal(r.sessionReads,1);assert.ok(!JSON.stringify(r.component.props).includes('private'));}
});
test('missing or duplicate session cookies never resolve a submission capability',async()=>{
 for(const cookies of [[],[{value:'one'},{value:'two'}]]){const r=await page({cookies});assert.equal(r.sessionReads,0);assert.equal(r.component.props.submissionEnabled,false);assert.equal(r.component.props.recoveryEnabled,false);}
});
test('query updates do not force remount and bounded initial context carries no submission authorization',async()=>{
 const r=await page({configured:false,query:{operation:'batch',target:'DEP-原始',release:'x'.repeat(37),snapshot:['invalid'],line:'line',submissionEnabled:'true'}});
 assert.equal(r.component.key,null);assert.equal(r.component.props.initialOperation,'batch');assert.equal(r.component.props.initialTarget,'DEP-原始');
 assert.equal(r.component.props.initialContext.release,'');assert.equal(r.component.props.initialContext.snapshot,'');assert.equal(r.component.props.submissionEnabled,false);
});

test('first and governance capabilities use independent approved gates and one private session projection',async()=>{
 for(const configured of [false,true])for(const governanceConfigured of [false,true])for(const read_only_mode of [false,true,undefined]){
  const r=await page({configured,governanceConfigured,identity:{read_only_mode,token:'private'}});
  assert.equal(r.cookieReads,configured||governanceConfigured?1:0);assert.equal(r.sessionReads,configured||governanceConfigured?1:0);
  assert.equal(r.component.props.submissionEnabled,configured&&read_only_mode===false);
  assert.equal(r.component.props.governanceSubmissionEnabled,governanceConfigured&&read_only_mode===false);
  assert.equal(r.component.props.recoveryEnabled,configured);assert.equal(r.component.props.governanceRecoveryEnabled,governanceConfigured);
  assert.ok(!JSON.stringify(r.component.props).includes('private'));
 }
});
test('governance missing identity and duplicate cookies cannot enable submit or recovery',async()=>{
 for(const options of [{identity:null},{cookies:[]},{cookies:[{value:'one'},{value:'two'}]}]){
  const r=await page({configured:false,governanceConfigured:true,...options});
  assert.equal(r.component.props.governanceSubmissionEnabled,false);assert.equal(r.component.props.governanceRecoveryEnabled,false);
 }
});

test('three independent command gates project six booleans through exactly one current session',async()=>{
 for(const configured of [false,true])for(const governanceConfigured of [false,true])for(const distributionConfigured of [false,true])for(const read_only_mode of [false,true,undefined]){
  const r=await page({configured,governanceConfigured,distributionConfigured,identity:{read_only_mode,token:'private',principal:{id:'private'}}});
  const enabled=configured||governanceConfigured||distributionConfigured;
  assert.equal(r.cookieReads,enabled?1:0);assert.equal(r.sessionReads,enabled?1:0);
  for(const [gate,submit,recover] of [[configured,'submissionEnabled','recoveryEnabled'],[governanceConfigured,'governanceSubmissionEnabled','governanceRecoveryEnabled'],[distributionConfigured,'distributionSubmissionEnabled','distributionRecoveryEnabled']]){
   assert.equal(r.component.props[submit],gate&&read_only_mode===false);assert.equal(r.component.props[recover],gate);
  }
  assert.ok(!JSON.stringify(r.component.props).includes('private'));
 }
});
test('distribution missing session or ambiguous cookies fail closed',async()=>{
 for(const options of [{identity:null},{cookies:[]},{cookies:[{value:'one'},{value:'two'}]}]){
  const r=await page({configured:false,distributionConfigured:true,...options});
  assert.equal(r.component.props.distributionSubmissionEnabled,false);assert.equal(r.component.props.distributionRecoveryEnabled,false);
 }
});

test('four independent approved command gates project eight booleans through one current session',async()=>{
 for(const configured of [false,true])for(const governanceConfigured of [false,true])for(const distributionConfigured of [false,true])for(const productionConfigured of [false,true])for(const read_only_mode of [false,true,undefined]){
  const r=await page({configured,governanceConfigured,distributionConfigured,productionConfigured,identity:{read_only_mode,token:'private',principal:{id:'private'}}});
  const enabled=configured||governanceConfigured||distributionConfigured||productionConfigured;
  assert.equal(r.cookieReads,enabled?1:0);assert.equal(r.sessionReads,enabled?1:0);
  for(const [gate,submit,recover] of [[configured,'submissionEnabled','recoveryEnabled'],[governanceConfigured,'governanceSubmissionEnabled','governanceRecoveryEnabled'],[distributionConfigured,'distributionSubmissionEnabled','distributionRecoveryEnabled'],[productionConfigured,'productionSubmissionEnabled','productionRecoveryEnabled']]){
   assert.equal(r.component.props[submit],gate&&read_only_mode===false);assert.equal(r.component.props[recover],gate);
  }
  assert.ok(!JSON.stringify(r.component.props).includes('private'));
 }
});
test('production capabilities fail closed for missing identity and ambiguous cookies',async()=>{
 for(const options of [{identity:null},{cookies:[]},{cookies:[{value:'one'},{value:'two'}]}]){
  const r=await page({configured:false,productionConfigured:true,...options});
  assert.equal(r.component.props.productionSubmissionEnabled,false);assert.equal(r.component.props.productionRecoveryEnabled,false);
 }
});

test('six independent command gates resolve one private session and project twelve booleans',async()=>{
 for(let bits=0;bits<64;bits++)for(const read_only_mode of [false,true,undefined]){
  const names=['configured','governanceConfigured','distributionConfigured','productionConfigured','evidenceConfigured','resourceConfigured'];
  const options=Object.fromEntries(names.map((name,index)=>[name,Boolean(bits&(1<<index))]));
  const r=await page({...options,identity:{read_only_mode,token:'private',principal:{id:'private'}}});
  assert.equal(r.cookieReads,bits?1:0);assert.equal(r.sessionReads,bits?1:0);
  for(const [gate,submit,recover] of [[options.configured,'submissionEnabled','recoveryEnabled'],...['governance','distribution','production','evidence','resource'].map(group=>[options[group+'Configured'],group+'SubmissionEnabled',group+'RecoveryEnabled'])]){
   assert.equal(r.component.props[submit],gate&&read_only_mode===false,submit);assert.equal(r.component.props[recover],gate,recover);
  }
  assert.ok(!JSON.stringify(r.component.props).includes('private'));
 }
});
test('evidence and resource capabilities fail closed for missing session, ambiguous cookies and query claims',async()=>{
 for(const group of ['evidence','resource'])for(const options of [{identity:null},{cookies:[]},{cookies:[{value:'one'},{value:'two'}]}]){
  const r=await page({configured:false,[group+'Configured']:true,query:{operation:group==='evidence'?'impact':'resource',[group+'SubmissionEnabled']:'true'},...options});
  assert.equal(r.component.props[group+'SubmissionEnabled'],false);assert.equal(r.component.props[group+'RecoveryEnabled'],false);
 }
});
