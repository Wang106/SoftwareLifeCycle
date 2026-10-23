const {test, before, after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {execFileSync}=require('node:child_process');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
let tmp, localized;
before(()=>{
  tmp=fs.mkdtempSync(path.join(os.tmpdir(),'slc-catalog-filters-'));
  execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/localized.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',tmp]);
  fs.symlinkSync(path.resolve('node_modules'),path.join(tmp,'node_modules'),'dir');
  localized=require(path.join(tmp,'components/localized.js'));
});
after(()=>{if(tmp)fs.rmSync(tmp,{recursive:true,force:true});});
async function render(kind,search={},locale='en',response){
  const calls=[];
  const standard=kind==='standard';
  const filename=standard?'components/supplier-release-catalog.tsx':'components/release-catalog.tsx';
  const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const m={exports:{}};
  new Function('require','module','exports',code)(name=>{
    if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
    if(name.endsWith('/localized'))return localized;
    if(name.endsWith('/api'))return {apiGet:async url=>{
      calls.push(url);
      if(url.includes('/release-catalog/'))return response===undefined?{kind,total:2,next_offset:1,items:standard?[{id:'s1',version:'v1',status:'DRAFT',supplier:{code:'LIB',name:'LIB'},software:{code:'BMS',name:'BMS'}}]:[]}:response;
      return {release_id:'s1',total:11,next_offset:10,items:[]};
    }};
    return require(name);
  },m,m.exports);
  const page=await m.exports.default(standard?{search}:{kind,search});
  const html=renderToStaticMarkup(React.createElement(localized.LanguageProvider,{initialLocale:locale},page));
  const links=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));
  return {html,links,calls};
}
for(const kind of ['standard','application']){
  test(kind+' suggests translated statuses while preserving arbitrary exact labels and raw search text',async()=>{
    for(const locale of ['zh','en']){
      const {html,calls}=await render(kind,{q:'Search <BMS> & 100%',status:'CUSTOM_LABEL',software_id:'software-uuid'},locale);
      assert.match(html,new RegExp(`name="status"[^>]*list="${kind}-release-statuses"|list="${kind}-release-statuses"[^>]*name="status"`));
      assert.ok(html.includes('value="CUSTOM_LABEL"'));
      for(const [value,zh] of [['DRAFT','草稿'],['READY','就绪'],['RELEASED','已发布'],['SUPERSEDED','已替代']]){
        assert.ok(html.includes(`<option value="${value}">${locale==='zh'?zh:value}</option>`));
      }
      assert.ok(html.includes(locale==='zh'?'当前筛选条件':'Current filters'));
      assert.ok(html.includes('<code>Search &lt;BMS&gt; &amp; 100%</code>'));
      assert.ok(html.includes('<code>CUSTOM_LABEL</code>')&&html.includes('<code>software-uuid</code>'));
      assert.ok(html.includes(locale==='zh'?'不能作为审批或发布证据':'not approval or release evidence'));
      const query=new URL(calls[0],'http://local').searchParams;
      assert.equal(query.get('status'),'CUSTOM_LABEL');assert.equal(query.get('q'),'Search <BMS> & 100%');
      assert.ok(!html.includes('method="post"'));assert.equal(calls.length,kind==='standard'?2:1);
    }
  });
  test(kind+' retains filters on catalog and child pagination, and clearing removes all scope and offsets',async()=>{
    const search={q:'_%',status:'DRAFT',software_id:'exact-uuid',limit:'1',offset:'40',applications_for:'s1',application_offset:'10'};
    const {html,links}=await render(kind,search);
    const next=links.find(link=>new URL(link,'http://local').searchParams.get('offset')==='1');
    assert.ok(next);
    const nextQuery=new URL(next,'http://local').searchParams;
    for(const key of ['q','status','software_id','limit'])assert.equal(nextQuery.get(key),search[key]);
    assert.equal(nextQuery.has('applications_for'),false);assert.equal(nextQuery.has('application_offset'),false);
    assert.ok(html.includes(`href="/releases/${kind}">Clear filters</a>`));
    const form=html.match(/<form[^>]*>[\s\S]*?<\/form>/)[0];
    assert.match(form,/method="get"/);
    assert.ok(!/name="(?:offset|applications_for|application_offset)"/.test(form),'New filter submissions restart pagination');
    assert.ok(form.includes('name="software_id"'));
    if(kind==='standard'){
      const child=links.find(link=>new URL(link,'http://local').searchParams.get('applications_for')==='s1');
      assert.ok(child, 'Child pagination must remain visible and scoped');
      const query=new URL(child,'http://local').searchParams;
      for(const key of ['q','status','software_id','limit','offset'])assert.equal(query.get(key),search[key]);
    }
  });
  test(kind+' keeps unavailable and empty results distinct and never silently drops repeated values',async()=>{
    const failed=await render(kind,{q:['a','b'],status:['READY','DRAFT'],software_id:['x','y']},'en',null);
    const query=new URL(failed.calls[0],'http://local').searchParams;
    for(const key of ['q','status','software_id'])assert.equal(query.get(key),'invalid');
    assert.ok(failed.html.includes('Release catalog unavailable'));
    assert.ok(failed.html.includes('Current filters')&&failed.html.includes('<code>invalid</code>'));
    const empty=await render(kind,{status:'CUSTOM_LABEL'},'en',{kind,total:0,next_offset:null,items:[]});
    assert.ok(empty.html.includes('No releases on this page.'));
    assert.ok(!empty.html.includes('Release catalog unavailable'));
    const initial=await render(kind);
    assert.ok(!initial.html.includes('Current filters'));
    const whitespace=await render(kind,{status:' '});
    assert.equal(new URL(whitespace.calls[0],'http://local').searchParams.get('status'),' ');
    assert.ok(whitespace.html.includes('Current filters'));
  });
}
