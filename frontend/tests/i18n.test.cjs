'use strict';
const {test, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {tmpdir} = require('node:os');
const {execFileSync} = require('node:child_process');
const ts = require('typescript');
const output = fs.mkdtempSync(path.join(tmpdir(), 'slc-i18n-'));
execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'), 'lib/i18n.ts', 'components/localized.tsx', '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const {translateText, resolveLocale} = require(path.join(output,'lib/i18n.js'));
const {Localized, LocalizedAttributes, LanguageProvider} = require(path.join(output,'components/localized.js'));
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const dictionary = require('../lib/i18n/zh.json');
const templates = require('../lib/i18n/templates.json');
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const element = React.createElement;
function render(locale, child) {return renderToStaticMarkup(element(LanguageProvider,{initialLocale:locale},child));}
test('missing, invalid and untrusted language values default to Chinese',()=>{
 for(const value of [undefined,null,'','ZH','en-US','../en',{},'zh']) assert.equal(resolveLocale(value),'zh');
 assert.equal(resolveLocale('en'),'en');
});
test('SSR renders Chinese by default and exact English on explicit selection',()=>{
 const zh=render('zh',element(Localized,null,'Dashboard'));
 const en=render('en',element(Localized,null,'Dashboard'));
 assert.ok(zh.includes(dictionary.Dashboard)); assert.ok(en.includes('Dashboard'));
 assert.ok(zh.includes('aria-pressed="true"')); assert.ok(en.includes('Interface language'));
});
test('presentation translation preserves whitespace, evidence, identifiers and English byte for byte',()=>{
 for(const raw of ['EVT-SN-123456','/api/v1/releases/abc','https://example.com/a:b','{"request_id":"abc"}','Customer-specific evidence', '12345678-1234-1234-1234-123456789abc']) {
  assert.equal(translateText(raw,'zh'),raw); assert.equal(translateText(raw,'en'),raw);
 }
 assert.equal(translateText('  Dashboard\n','zh'),'  '+dictionary.Dashboard+'\n');
});
test('dynamic validation and compound status labels retain interpolated values',()=>{
 assert.equal(translateText('Release UUID must be a UUID.','zh'),(dictionary['Release UUID']??'Release UUID')+' 必须为 UUID。');
 const raw='ACTIVE · APPROVED · 17';const translated=translateText(raw,'zh');
 assert.equal(translated,[dictionary.ACTIVE,dictionary.APPROVED,'17'].join(' · '));
 assert.equal(translateText(raw,'en'),raw);
});
test('translated attributes never change option values, event handlers, names or identifiers',()=>{
 const child=element(LocalizedAttributes,null,element('input',{placeholder:'Search',value:'APPROVED',name:'status',id:'request_id',readOnly:true}));
 const html=render('zh',child);assert.ok(html.includes('value="APPROVED"'));assert.ok(html.includes('name="status"'));assert.ok(html.includes('id="request_id"'));
 assert.ok(html.includes('placeholder="'+dictionary.Search+'"'));
 const option=render('zh',element('select',null,element('option',{value:'APPROVED'},element(Localized,null,'APPROVED'))));
 assert.ok(option.includes('value="APPROVED"'));assert.ok(option.includes(dictionary.APPROVED));
});
test('templates preserve every interpolation slot and dictionaries contain actual labels',()=>{
 for(const [source,target] of Object.entries(templates)) assert.deepEqual((source.match(/\{\d+\}/g)||[]).sort(),(target.match(/\{\d+\}/g)||[]).sort(),source);
 for(const [source,target] of Object.entries(dictionary)){assert.ok(source.trim());assert.equal(typeof target,'string');assert.ok(target.trim());}
});
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):e.name.endsWith('.tsx')?[path.join(dir,e.name)]:[]);}
function tag(node){return node.tagName?.getText();}
for(const file of [...files('app'),...files('components')].filter(f=>!f.endsWith('localized.tsx'))){
 test('localization coverage and stable form values: '+file,()=>{
  const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  function visit(node,inside=false,raw=false){
   if(ts.isJsxElement(node)){
    const name=tag(node.openingElement);inside ||= name==='Localized';raw ||= ['pre','code','script','style'].includes(name);
    if(name==='option') assert.ok(node.openingElement.attributes.properties.some(a=>a.name?.getText()==='value'),'option needs original explicit value');
   }
   if(ts.isJsxText(node)&&node.getText().trim()&&!raw) assert.ok(inside,'unlocalized visible text: '+node.getText());
   if(ts.isJsxExpression(node)&&node.parent&&ts.isJsxElement(node.parent)&&node.parent.children.includes(node)&&!raw) assert.ok(inside,'unlocalized expression: '+node.getText());
   if(ts.isStringLiteral(node)&&ts.isJsxExpression(node.parent)&&inside&&!raw){
    const value=node.text.replace(/\s+/g,' ').trim();
    if(value&&/[A-Za-z]/.test(value)) assert.ok(Object.hasOwn(dictionary,value),'missing dictionary label: '+value);
   }
   ts.forEachChild(node,child=>visit(child,inside,raw));
  }
  visit(source);
 });
}

test('record-derived UI markers and fallback states translate in Chinese',()=>{
 for(const label of ['CHECK','CONSISTENT','CURRENT','ELIGIBLE','HISTORICAL','INVALID','NOT DEPLOYED','TEST','UNASSIGNED','VALID','differ','pending','unknown',' · CURRENT',' · NOT CURRENT','SCR-142 moved to IN TEST','DVP-032 execution #2 passed','SNAP-008 frozen','APR-0121 approved','RD-0081 released ASR 2.3.4','DIST-0326 acknowledged','PA-0081 approved','DEP-0081 software matched','PB-1005-A started','CONFIDENTIAL','STRICTLY_CONFIDENTIAL','LOCAL_ONLY','MAIN_APPLICATION','CALIBRATION','EUROPE','AMERICAS']) {
  assert.match(translateText(label,'zh'),/[\u4e00-\u9fff]/,label);
  assert.equal(translateText(label,'en'),label);
 }
});


test('dynamic readiness gate names, exception marker and counts translate without changing API values',()=>{
 for(const label of ['Change Control','Issue Control','Verification','Software Integrity','Artifact Control','Distribution Control','Governance','Required changes linked to DVP','Verification-required issues linked to DVP','Required DVP executed on current snapshot','Tested snapshot equals current snapshot','Current snapshot is frozen','SHA-256 complete for formal artifacts','Artifact distribution policy complete','Approved exceptions are bound to current snapshot','EXCEPTION_GRANTED']) {
  assert.match(translateText(label,'zh'),/[\u4e00-\u9fff]/,label);
  assert.equal(translateText(label,'en'),label);
 }
 for(const count of [0,1,123]) {
  const evidence=`${count} current-snapshot exception(s)`;
  assert.equal(translateText(evidence,'zh'),`当前快照批准例外：${count} 个`);
  assert.equal(translateText(evidence,'en'),evidence);
 }
});
