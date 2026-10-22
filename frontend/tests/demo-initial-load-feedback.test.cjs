'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const i18nCode=ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
const i18n={exports:{}};new Function('require','module','exports',i18nCode)(n=>n.endsWith('zh.json')?dict:templates,i18n,i18n.exports);
const translate=c=>typeof c==='string'?i18n.exports.translateText(c,localeForRender):Array.isArray(c)?c.map(translate):c;
let localeForRender='en';

// Render a demo page while capturing the exact apiGet call arguments.
async function renderPage(pageFile, data, locale='en'){
  localeForRender=locale;
  const compiled=ts.transpileModule(fs.readFileSync(pageFile,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const module={exports:{}},calls=[];
  const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children)
    : n.endsWith('/lib/api')?{apiGet:async(...args)=>{calls.push(args);return data;}}
    : n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}
    : require(n);
  new Function('require','module','exports',compiled)(req,module,module.exports);
  return {html:renderToStaticMarkup(await module.exports.default()),calls};
}

test('zfi and releases reads are bounded to 15 seconds',async()=>{
  const zfi=await renderPage('app/demo/zfi/page.tsx',null,'en');
  assert.equal(zfi.calls.length,1);
  assert.equal(zfi.calls[0][0],'/api/v1/demo/zfi-import');
  assert.deepEqual(zfi.calls[0][1],{timeoutMs:15000});
  const rel=await renderPage('app/demo/releases/page.tsx',null,'en');
  assert.equal(rel.calls.length,1);
  assert.equal(rel.calls[0][0],'/api/v1/demo/release-evidence');
  assert.deepEqual(rel.calls[0][1],{timeoutMs:15000});
});

for(const [file,heading] of [['app/demo/zfi/page.tsx','Excel import API unavailable'],['app/demo/releases/page.tsx','Evidence API unavailable']])
for(const locale of ['en','zh'])
test('unavailable '+file.split('/').pop()+' states the bounded read and offers a retry in '+locale,async()=>{
  const {html}=await renderPage(file,null,locale);
  assert.ok(html.includes(i18n.exports.translateText(heading,locale)));
  assert.ok(html.includes(i18n.exports.translateText('The read is bounded and stops waiting when the API does not settle in time.',locale)));
  assert.ok(html.includes(i18n.exports.translateText('Read again',locale)));
  const retryHref=file.includes('zfi')?'/demo/zfi':'/demo/releases';
  assert.ok(html.includes('href="'+retryHref+'"'));
});

for(const locale of ['en','zh'])test('demo loading skeleton is bilingual and never fabricates evidence in '+locale,async()=>{
  localeForRender=locale;
  const compiled=ts.transpileModule(fs.readFileSync('app/demo/loading.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const module={exports:{}};
  const req=n=>n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
  new Function('require','module','exports',compiled)(req,module,module.exports);
  const html=renderToStaticMarkup(React.createElement(module.exports.default));
  assert.ok(html.includes(i18n.exports.translateText('Loading demonstration data',locale)));
  assert.ok(html.includes(i18n.exports.translateText('No sample evidence is fabricated while waiting.',locale)));
  assert.ok(html.includes('aria-busy="true"'));
  assert.ok(html.includes('demo-loading-bar'));
});
