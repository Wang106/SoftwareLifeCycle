'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {buildHarness,startHarness,PAGE_PATHS,SCRIPT_PATH,API_PATHS}=require('../component-browser/harness.cjs');

function request(origin,resource,options={}){
  return new Promise((resolve,reject)=>{
    const req=http.request(origin+resource,options,response=>{
      const chunks=[];response.on('data',chunk=>chunks.push(chunk));
      response.on('end',()=>resolve({status:response.statusCode,headers:response.headers,body:Buffer.concat(chunks).toString()}));
    });
    req.on('error',reject);req.end();
  });
}
async function fixture(fn){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'slc-b2-server-contract-'));
  const bundlePath=path.join(directory,'component.js');fs.writeFileSync(bundlePath,'/* contract-only static bytes */');
  let server;
  try{server=await startHarness({bundlePath});await fn(server);}finally{await server?.close();fs.rmSync(directory,{recursive:true,force:true});}
}

test('test-only bundle contains actual React, Next Link, workbench, i18n and transport',async()=>{
  const build=await buildHarness();
  try{
    assert.ok(build.directory.startsWith(path.join(os.tmpdir(),'slc-b2-component-')));
    assert.ok(!build.directory.startsWith(path.resolve(__dirname,'..')));
    assert.ok(fs.statSync(build.bundlePath).size>1000);
    const modules=build.modules.join('\n').replaceAll('\\','/');
    for(const name of ['authorization-approval-workbench.js','authorization-approval-transport.js','localized.js','i18n/zh.json','next/dist/client/link.js','react-dom','react/'])assert.ok(modules.includes(name),name);
    assert.ok(!modules.includes('browser-session'));
    assert.ok(!modules.includes('browser-auth'));
    const script=fs.readFileSync(build.bundlePath,'utf8');
    assert.ok(script.includes('AUTH-原始')||script.includes('AUTH-\\u539F\\u59CB'));
    assert.ok(script.includes('Isolated synthetic component fixture'));
  }finally{build.dispose();}
  assert.equal(fs.existsSync(build.directory),false);
});

test('finite page and asset allowlist binds only IPv4 loopback and uses a restrictive CSP',async()=>{
  await fixture(async server=>{
    assert.match(server.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
    for(const resource of [...PAGE_PATHS,SCRIPT_PATH]){
      const response=await request(server.origin,resource);
      assert.equal(response.status,200);assert.equal(response.headers['cache-control'],'no-store');
      assert.equal(response.headers['x-content-type-options'],'nosniff');
      assert.match(response.headers['content-security-policy'],/default-src 'none'/);
      assert.match(response.headers['content-security-policy'],/connect-src 'self'/);
      assert.equal(response.headers.location,undefined);
      if(resource!==SCRIPT_PATH){assert.match(response.body,/id="component-root"/);assert.match(response.body,/src="\/component.js"/);}
    }
    assert.deepEqual(server.violations,[]);
  });
});

test('unknown paths, queries, production routes and all unhandled API requests fail closed',async()=>{
  await fixture(async server=>{
    for(const resource of ['/','/component/approval?mode=enabled','/component.js?x=1','/../package.json','/auth/session','/distribution/authorizations/AUTH/approve',...API_PATHS])assert.equal((await request(server.origin,resource)).status,404);
    for(const method of ['POST','PUT','DELETE','HEAD','OPTIONS'])assert.equal((await request(server.origin,PAGE_PATHS[0],{method})).status,405);
    assert.equal((await request(server.origin,PAGE_PATHS[0],{headers:{Host:'private.example'}})).status,400);
    assert.equal(server.violations.length,15);
    assert.ok(server.violations.every(value=>['unexpected-path','unexpected-method','unexpected-host'].includes(value)));
    assert.ok(!JSON.stringify(server.violations).includes('private.example'));
  });
});

test('websocket upgrade is rejected, never proxied',async()=>{
  await fixture(async server=>{
    await assert.rejects(request(server.origin,PAGE_PATHS[0],{headers:{Connection:'Upgrade',Upgrade:'websocket'}}),/socket hang up/);
    assert.deepEqual(server.violations,['unexpected-upgrade']);
  });
});

test('harness rejects invalid ports and absent artifacts before listening',async()=>{
  for(const port of [-1,65536,'1234',1.5])await assert.rejects(startHarness({port,bundlePath:__filename}),/Invalid loopback port/);
  await assert.rejects(startHarness(),/built bundle/);
  await assert.rejects(startHarness({bundlePath:path.join(os.tmpdir(),'nonexistent-b2-bundle.js')}),/ENOENT/);
  assert.deepEqual(API_PATHS,['/auth/authorization-approval-context','/auth/authorization-approval','/auth/authorization-approval-receipt']);
  assert.ok(Object.isFrozen(PAGE_PATHS));assert.ok(Object.isFrozen(API_PATHS));
});
