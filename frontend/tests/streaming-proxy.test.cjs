'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),{once}=require('node:events');
const {allowedPath,startStreamingProxy,PROJECT_CATALOG_QUERY,PROJECT_CATALOG_FIRST_PAGE_QUERY}=require('../e2e/streaming-proxy.cjs');
test('streaming test transport rejects every redirect without forwarding Location or following its target',async()=>{let hits=0;const upstream=http.createServer((req,res)=>{hits++;res.writeHead(302,{location:'http://127.0.0.1:1/not-allowed'});res.end();});upstream.listen(0,'127.0.0.1');await once(upstream,'listening');const proxy=await startStreamingProxy(`http://127.0.0.1:${upstream.address().port}`);try{const response=await fetch(proxy.origin+'/');assert.equal(response.status,502);assert.equal(response.headers.get('location'),null);assert.equal(hits,1);assert.deepEqual(proxy.violations,['rejected_redirect']);}finally{await proxy.close();upstream.closeAllConnections();await new Promise(r=>upstream.close(r));}});
test('streaming test transport delivers first chunk before upstream completion and rejects nonpublic reads',async()=>{let finish;const upstream=http.createServer((req,res)=>{res.writeHead(200,{'content-type':'text/plain'});res.write('SHELL');finish=()=>res.end('DATA');});upstream.listen(0,'127.0.0.1');await once(upstream,'listening');const proxy=await startStreamingProxy(`http://127.0.0.1:${upstream.address().port}`);try{const response=await fetch(proxy.origin+'/');const reader=response.body.getReader();assert.equal(new TextDecoder().decode((await reader.read()).value),'SHELL');finish();assert.equal(new TextDecoder().decode((await reader.read()).value),'DATA');assert.equal((await reader.read()).done,true);assert.equal((await fetch(proxy.origin+'/auth/session')).status,400);assert.equal((await fetch(proxy.origin+'/',{method:'POST'})).status,400);}finally{await proxy.close();upstream.closeAllConnections();await new Promise(r=>upstream.close(r));}});
test('streaming target must be fixed loopback and query allowlist cannot expand to private targets',async()=>{for(const target of ['https://example.com','http://localhost:1234','http://127.0.0.1:1234/path'])await assert.rejects(startStreamingProxy(target));for(const path of ['/account','/auth/login','/projects?q=private','/api/v1/private'])assert.equal(allowedPath(path),false);assert.equal(allowedPath('/issues?_rsc=fixture'),true);assert.equal(allowedPath('/favicon.ico'),true);assert.equal(allowedPath('https://example.com/'),false);});

const projectOptions=Object.freeze({projectCatalogQuery:PROJECT_CATALOG_QUERY});
const projectPage='/projects?'+PROJECT_CATALOG_QUERY;
const firstProjectPage='/projects?'+PROJECT_CATALOG_FIRST_PAGE_QUERY;

test('project query opt-in adds only the fixed target and first page, leaving default paths unchanged',()=>{
 assert.equal(PROJECT_CATALOG_QUERY,'q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20');
 assert.equal(PROJECT_CATALOG_FIRST_PAGE_QUERY,'q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10');
 for(const path of [projectPage,firstProjectPage,projectPage+'&_rsc=fixture_1-X',firstProjectPage+'&_rsc=fixture']){
  assert.equal(allowedPath(path),false,path+' must require opt-in');
  assert.equal(allowedPath(path,projectOptions),true,path);
 }
 for(const path of ['/','/changes','/issues?_rsc=fixture','/projects','/projects?_rsc=fixture','/_next/static/chunks/app.js','/favicon.ico']){
  assert.equal(allowedPath(path),true,path);
  assert.equal(allowedPath(path,projectOptions),true,path);
 }
 for(const path of [
  projectPage.replace('A+%26+B','private'),projectPage.replace('A+%26+B','A%20%26%20B'),
  projectPage.replace('status=ACTIVE','status=INACTIVE'),projectPage.replace('customer-one','customer-two'),
  projectPage.replace('limit=10','limit=20'),projectPage.replace('offset=20','offset=0'),
  projectPage.replace('status=ACTIVE&',''),projectPage+'&q=A+%26+B',projectPage+'&offset=20',
  projectPage+'&extra=1',projectPage+'&_rsc=one&_rsc=two',projectPage+'&_rsc=',
  '/projects?_rsc=first&'+PROJECT_CATALOG_QUERY,
  '/projects?status=ACTIVE&q=A+%26+B&customer_id=customer-one&limit=10&offset=20',
  projectPage+'#fragment',projectPage+'&_rsc=token#fragment',firstProjectPage+'&offset=',
  '/issues?'+PROJECT_CATALOG_QUERY,'/account?'+PROJECT_CATALOG_QUERY,
  '/auth/session?'+PROJECT_CATALOG_QUERY,'/api/v1/organization-views/projects?'+PROJECT_CATALOG_QUERY,
  '/other/../projects?'+PROJECT_CATALOG_QUERY,'https://example.com'+projectPage,
  '//example.com'+projectPage,'/\\example.com'+projectPage,
  '/projects?q=private',undefined,null
 ]){
  assert.equal(allowedPath(path),false,String(path));
  assert.equal(allowedPath(path,projectOptions),false,String(path));
 }
});

test('project policy rejects unknown options and any unapproved query before listening',async()=>{
 for(const options of [null,[],{},PROJECT_CATALOG_QUERY,
  {projectCatalogQuery:''},{projectCatalogQuery:PROJECT_CATALOG_FIRST_PAGE_QUERY},
  {projectCatalogQuery:PROJECT_CATALOG_QUERY+'&private=1'},
  {projectCatalogQuery:projectPage},{projectCatalogQuery:'https://example.com'+projectPage},
  {projectCatalogQuery:PROJECT_CATALOG_QUERY,extra:true},
  {allowProjectCatalogQuery:true},Object.create(projectOptions)
 ]){
  assert.throws(()=>allowedPath(projectPage,options),/fixed_project_catalog_query_required/);
  await assert.rejects(startStreamingProxy('http://127.0.0.1:1',options),/fixed_project_catalog_query_required/);
 }
 for(const upstream of ['https://example.com','http://localhost:1234','http://127.0.0.1:1234/path','http://127.0.0.1:1234?target=external']){
  await assert.rejects(startStreamingProxy(upstream,projectOptions),/loopback_upstream_required/);
 }
});

async function listen(server){
 server.listen(0,'127.0.0.1');await once(server,'listening');
 return `http://127.0.0.1:${server.address().port}`;
}
async function closeServer(server){
 server.closeAllConnections();await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
}

test('opted-in exact project query streams before completion and never forwards rejected requests',{timeout:10000},async()=>{
 let finish;
 const requests=[];
 const upstream=http.createServer((req,res)=>{
  requests.push({url:req.url,method:req.method});
  res.writeHead(200,{'content-type':'text/plain'});
  if(req.url===projectPage){res.write('PROJECT SHELL');finish=()=>res.end('READY');}
  else res.end('FIRST PAGE');
 });
 const origin=await listen(upstream);
 const proxy=await startStreamingProxy(origin,projectOptions);
 try{
  const response=await fetch(proxy.origin+projectPage,{signal:AbortSignal.timeout(3000)});
  const reader=response.body.getReader();
  assert.equal(new TextDecoder().decode((await reader.read()).value),'PROJECT SHELL');
  finish();
  assert.equal(new TextDecoder().decode((await reader.read()).value),'READY');
  assert.equal((await reader.read()).done,true);
  const first=firstProjectPage+'&_rsc=fixture';
  assert.equal(await (await fetch(proxy.origin+first,{headers:{rsc:'1','next-router-prefetch':'1'},signal:AbortSignal.timeout(3000)})).text(),'FIRST PAGE');
  for(const [path,options] of [
   [projectPage+'&extra=1',{}],[projectPage+'&_rsc=one&_rsc=two',{}],
   ['/auth/session',{}],['/api/v1/organization-views/projects?'+PROJECT_CATALOG_QUERY,{}],
   [projectPage,{method:'POST'}],[projectPage,{headers:{authorization:'synthetic-not-a-credential'}}]
  ]){
   const rejected=await fetch(proxy.origin+path,{...options,signal:AbortSignal.timeout(3000)});
   assert.equal(rejected.status,400,path);await rejected.text();
  }
  assert.deepEqual(requests,[{url:projectPage,method:'GET'},{url:first,method:'GET'}]);
  assert.deepEqual(proxy.violations,Array(6).fill('rejected_request'));
 }finally{
  try{await proxy.close();}finally{await closeServer(upstream);}
 }
});

test('project opt-in preserves redirect denial and strips redirect headers even from successful responses',{timeout:10000},async()=>{
 let destinationHits=0;
 const destination=http.createServer((req,res)=>{destinationHits++;res.end('not allowed');});
 const destinationOrigin=await listen(destination);
 const upstream=http.createServer((req,res)=>{
  res.writeHead(req.url===projectPage?302:200,{location:destinationOrigin+'/outside',refresh:'0; url='+destinationOrigin+'/outside','content-type':'text/plain'});
  res.end('upstream');
 });
 const origin=await listen(upstream);
 const proxy=await startStreamingProxy(origin,projectOptions);
 try{
  const redirected=await fetch(proxy.origin+projectPage,{signal:AbortSignal.timeout(3000)});
  assert.equal(redirected.status,502);
  assert.equal(redirected.headers.get('location'),null);
  assert.equal(redirected.headers.get('refresh'),null);
  assert.equal(await redirected.text(),'unexpected_redirect');
  const success=await fetch(proxy.origin+firstProjectPage,{signal:AbortSignal.timeout(3000)});
  assert.equal(success.status,200);
  assert.equal(success.headers.get('location'),null);
  assert.equal(success.headers.get('refresh'),null);
  assert.equal(await success.text(),'upstream');
  assert.equal(destinationHits,0);
  assert.deepEqual(proxy.violations,['rejected_redirect']);
 }finally{
  try{await proxy.close();}finally{
   try{await closeServer(upstream);}finally{await closeServer(destination);}
  }
 }
});
