'use strict';
// Optional post-build HTTP check: real Next SSR and timers, synthetic loopback API.
// Not a browser, Cloudflare Worker, public database or production-latency check.
const assert = require('node:assert/strict');
const http = require('node:http');
const {once} = require('node:events');
const {performance} = require('node:perf_hooks');
const {startApp} = require('../e2e/fixture-server.cjs');
const query = 'q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20';
const apiPath = '/api/v1/organization-views/projects?' + query;
async function fixture(phase) {
  const requests = [], violations = []; let ready = false;
  const server = http.createServer((req,res) => {
    requests.push(req.url);
    if (req.method !== 'GET' || req.url !== apiPath || req.headers.authorization || req.headers.cookie) {
      violations.push(req.url); res.writeHead(400); res.end('rejected synthetic request'); return;
    }
    if (!ready) {
      if (phase === 'body') { res.writeHead(200, {'content-type':'application/json'}); res.write('{'); }
      return; // Keep headers/body genuinely unfinished until the client aborts.
    }
    res.writeHead(200, {'content-type':'application/json','cache-control':'no-store'});
    res.end(JSON.stringify({kind:'projects',total:1,limit:10,offset:20,next_offset:null,items:[{id:'synthetic-project',code:'SYNTHETIC',name:'SYNTHETIC_RECOVERED_PROJECT',status:'ACTIVE',site_count:1}]}));
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  return {apiOrigin:`http://127.0.0.1:${server.address().port}`,requests,violations,recover(){ready=true;},
    async close(){if(server.listening)await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});}};
}
async function check(phase) {
  const app = await startApp(() => fixture(phase));
  try {
    const started = performance.now();
    const response = await fetch(app.appOrigin+'/projects?'+query, {redirect:'error',signal:AbortSignal.timeout(25000)});
    assert.equal(response.status,200);
    const reader = response.body.getReader(), decoder = new TextDecoder(); let html='', firstChunkMs, loadingMarkupMs;
    for (;;) {const {value,done}=await reader.read();if(done)break;if(firstChunkMs===undefined)firstChunkMs=performance.now()-started;html+=decoder.decode(value,{stream:true});if(loadingMarkupMs===undefined && /role="status"/.test(html) && /<h2>正在加载页面数据<\/h2>/.test(html))loadingMarkupMs=performance.now()-started;}
    html+=decoder.decode(); const completedMs=performance.now()-started;
    assert.match(html,/组织目录暂不可用/); assert.match(html,/重新读取项目/);
    assert.match(html,/>—<\/b>/); assert.doesNotMatch(html,/SYNTHETIC_RECOVERED_PROJECT|没有匹配的记录/);
    assert.ok(completedMs>=14000,`must exercise the actual 15s wait: ${completedMs}`);
    assert.ok(loadingMarkupMs!==undefined && loadingMarkupMs<14000,'actual loading markup must arrive while the read is still held');
    assert.deepEqual(app.fixture.requests,[apiPath]);
    const href=html.match(/<a href="([^"]+)">重新读取项目<\/a>/)?.[1]?.replaceAll('&amp;','&');
    assert.equal(href,'/projects?'+query);
    app.fixture.recover();
    // Explicit second document GET, equivalent to following the native retry link.
    const recovered = await fetch(app.appOrigin+href,{redirect:'error',signal:AbortSignal.timeout(5000)});
    assert.equal(recovered.status,200); const recoveredHtml=await recovered.text();
    assert.match(recoveredHtml,/SYNTHETIC_RECOVERED_PROJECT/); assert.doesNotMatch(recoveredHtml,/组织目录暂不可用|重新读取项目/);
    assert.deepEqual(app.fixture.requests,[apiPath,apiPath]); assert.deepEqual(app.fixture.violations,[]);
    console.log(JSON.stringify({phase,firstChunkMs:Math.round(firstChunkMs),loadingMarkupMs:Math.round(loadingMarkupMs),completedMs:Math.round(completedMs),requests:2,result:'passed',scope:'synthetic loopback HTTP; not browser/Worker'}));
  } finally {await app.stop();}
}
(async()=>{await check('headers');await check('body');})().catch(error=>{console.error(error);process.exitCode=1;});
