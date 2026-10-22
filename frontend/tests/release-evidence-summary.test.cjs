'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const translated={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(n=>n.endsWith('zh.json')?dict:templates,translated,translated.exports);

const evidence={
  release:{id:'rel-uuid',version:'v1.0',release_type:'STANDARD',record_status:'DRAFT'},
  snapshot:{id:'snap-uuid',snapshot_no:'SNAP-1',status:'FROZEN',content_hash:'a'.repeat(64)},
  readiness:{overall:'READY',approval_eligible:true,
    coverage:{required_dvp_total:3,current_snapshot_executed:3,current_snapshot_passed:3,snapshot_match:true},
    rules:[{group:'Verification',rule:'Required DVP executed on current snapshot',evidence:'3 / 3',effective:'PASS'}]},
  approval:{approval_no:'APR-1',status:'APPROVED',current_snapshot_bound:true},
  decision:{decision_no:'RD-1',decision:'RELEASE',readiness_status:'READY',snapshot_id:'snap-uuid',current_evidence_bound:true},
  current_release_confirmed:true,
};

async function render(data,releaseId='rel-uuid',locale='en'){
 const compiled=ts.transpileModule(fs.readFileSync('components/release-evidence-summary.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}},calls=[];
 const translate=c=>typeof c==='string'?translated.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);return data;}}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
 new Function('require','module','exports',compiled)(req,m,m.exports);
 const html=renderToStaticMarkup(await m.exports.ReleaseEvidenceSummary({releaseId}));
 return {html,calls};
}

test('renders the snapshot-readiness-approval-decision chain in english',async()=>{
 const {html,calls}=await render(evidence);
 assert.deepEqual(calls,['/api/v1/releases/rel-uuid/evidence-summary']);
 assert.ok(html.includes('Release evidence summary'));
 assert.ok(html.includes('SNAP-1')&&html.includes('FROZEN'));
 assert.ok(html.includes('/snapshots/SNAP-1'));
 assert.ok(html.includes('/approvals/APR-1')&&html.includes('/release-decisions/RD-1'));
 assert.ok(html.includes('Current snapshot bound')&&html.includes('Current evidence bound'));
 assert.ok(html.includes('Formal release evidence matches the current snapshot.'));
 assert.ok(html.includes('PASS'));
 assert.ok(html.includes('READY'));
});

test('renders the chain in chinese',async()=>{
 const {html}=await render(evidence,'rel-uuid','zh');
 assert.ok(html.includes('发布证据摘要'));
 assert.ok(html.includes('绑定当前快照'));
});

test('renders unknown placeholders when evidence is missing',async()=>{
 const {html,calls}=await render({
  release:{id:'rel-uuid',version:'v2',release_type:'APPLICATION',record_status:'DRAFT'},
  snapshot:null,approval:null,decision:null,
  readiness:{overall:'NOT_READY',approval_eligible:false,coverage:{required_dvp_total:0,current_snapshot_executed:0,current_snapshot_passed:0,snapshot_match:false},rules:[]},
  current_release_confirmed:false,
 });
 assert.ok(html.includes('Current evidence does not confirm a formal release.'));
 assert.ok(!html.includes('/snapshots/')&&!html.includes('/approvals/')&&!html.includes('/release-decisions/'));
});

test('does not present a summary when the API is unavailable',async()=>{
 const {html}=await render(null);
 assert.ok(html.includes('Evidence summary unavailable.'));
 assert.ok(!html.includes('Formal release evidence matches'));
});

test('is read-only and never links to a command form',async()=>{
 const {html}=await render(evidence);
 assert.ok(!html.includes('<form')&&!html.includes('method="post"')&&!html.includes('/commands'));
});
