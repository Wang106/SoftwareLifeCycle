'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const {validateBrowserReport,readBrowserReport,REQUIRED_TITLES,MAX_REPORT_BYTES}=require('../scripts/check-component-browser-report.cjs');
function fixture(){return {config:{forbidOnly:true,projects:[{id:'chromium',name:'chromium',retries:0,repeatEach:1}]},errors:[],stats:{expected:5,unexpected:0,flaky:0,skipped:0,startTime:'2026-11-03T00:00:00Z',duration:1},suites:[{specs:REQUIRED_TITLES.map(title=>({title,file:'authorization-approval.spec.ts',ok:true,tests:[{projectId:'chromium',projectName:'chromium',expectedStatus:'passed',status:'expected',results:[{status:'passed',retry:0,workerIndex:0,parallelIndex:0,startTime:'2026-11-03T00:00:00Z',duration:1,errors:[],annotations:[{type:'browser-engine',description:'chromium'},{type:'synthetic-component-fixture',description:'verified'},{type:'browser-worker-index',description:'0'},{type:'evidence-layer',description:'component-only-not-authentication'}]}]}]}))}]};}
const result=r=>r.suites[0].specs[0].tests[0].results[0];
test('exact five component-only journeys are independently accepted',()=>assert.deepEqual(validateBrowserReport(fixture()),{tests:5,passed:5,skipped:0,retried:0,project:'chromium'}));
for(const [name,mutate] of [
 ['missing',r=>r.suites[0].specs.pop()],['duplicate',r=>r.suites[0].specs[1].title=REQUIRED_TITLES[0]],
 ['wrong file',r=>r.suites[0].specs[0].file='readonly.spec.ts'],['eight Next results',r=>r.stats.expected=8],
 ['skipped',r=>r.stats.skipped=1],['failed',r=>r.stats.unexpected=1],['flaky',r=>r.stats.flaky=1],
 ['report errors',r=>r.errors=[{}]],['retry',r=>result(r).retry=1],['failure result',r=>result(r).status='failed'],
 ['configured retry',r=>r.config.projects[0].retries=1],['discovery only',r=>r.config.argv=['--list']],
 ['only allowed',r=>r.config.forbidOnly=false],['sharded',r=>r.config.shard={current:1,total:2}],
 ['missing layer',r=>result(r).annotations.pop()],['false real identity claim',r=>result(r).annotations[3].description='real-identity'],
 ['wrong browser',r=>result(r).annotations[0].description='firefox'],['duplicate layer',r=>result(r).annotations.push(result(r).annotations[3])],
 ['unexecuted',r=>r.suites[0].specs[0].tests[0].results=[]],['no duration',r=>result(r).duration=0],
 ['expected fail',r=>r.suites[0].specs[0].tests[0].expectedStatus='failed'],
])test('rejects '+name,()=>{const value=fixture();mutate(value);assert.throws(()=>validateBrowserReport(value));});
test('bounded report CLI fails closed and keeps errors generic',()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'slc-component-report-'));try{const file=path.join(dir,'results.json'),cli=path.resolve(__dirname,'../scripts/check-component-browser-report.cjs');for(const content of ['', '{PRIVATE', 'x'.repeat(MAX_REPORT_BYTES+1)]){fs.writeFileSync(file,content);const out=spawnSync(process.execPath,[cli,file],{encoding:'utf8'});assert.equal(out.status,1);assert.equal(out.stderr.trim(),'Component browser report is missing, invalid or incomplete.');}fs.writeFileSync(file,JSON.stringify(fixture()));assert.equal(readBrowserReport(file).passed,5);assert.equal(spawnSync(process.execPath,[cli,file]).status,0);}finally{fs.rmSync(dir,{recursive:true,force:true});}});
test('separate config retains original candidate sandbox and eight-case suite without overriding security',()=>{const source=fs.readFileSync(path.resolve(__dirname,'../component-browser/playwright.config.cjs'),'utf8');assert.match(source,/require\('\.\.\/e2e\/playwright.config.cjs'\)/);assert.match(source,/\.\.\.original/);for(const key of ['launchOptions:','use:','retries:','forbidOnly:','projects:'])assert.ok(!source.includes(key));const original=fs.readFileSync(path.resolve(__dirname,'../e2e/playwright.config.cjs'),'utf8');assert.match(original,/chromiumSandbox: true/);assert.match(original,/retries: 0/);assert.match(original,/project-catalog.spec.ts/);});
