'use strict';
// Test transport only: fixed loopback upstream, no redirects and no buffering.
const http=require('node:http');
const {once}=require('node:events');
const publicPaths=new Set(['/', '/changes', '/issues', '/projects']);
const PROJECT_CATALOG_QUERY='q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20';
const PROJECT_CATALOG_FIRST_PAGE_QUERY='q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10';
const CHANGE_CATALOG_QUERY='q=A+%26+B&status=IN_VERIFICATION&scope=STANDARD&limit=10&offset=20&source=INTERNAL&change_type=ENHANCEMENT&software_id=software-one&customer_id=customer-one&project_id=project-one';
const ISSUE_CATALOG_QUERY='q=A+%26+B&status=OPEN&scope=STANDARD&limit=10&offset=20&severity=HIGH';
function catalogPolicy(options){
 if(options===undefined)return [];
 if(options!==null&&typeof options==='object'&&Object.hasOwn(options,'changeIssueCatalogQuery')){
  if(Array.isArray(options)||Reflect.ownKeys(options).length!==1||![CHANGE_CATALOG_QUERY,ISSUE_CATALOG_QUERY].includes(options.changeIssueCatalogQuery))throw Error('fixed_change_issue_catalog_query_required');
  const query=options.changeIssueCatalogQuery,path=query===CHANGE_CATALOG_QUERY?'/changes?':'/issues?';
  const first=path+query.replace('&offset=20','');
  return [path+query,first,first+'&offset=20'];
 }
 if(options===null||typeof options!=='object'||Array.isArray(options)||Reflect.ownKeys(options).length!==1||!Object.hasOwn(options,'projectCatalogQuery')||options.projectCatalogQuery!==PROJECT_CATALOG_QUERY)throw Error('fixed_project_catalog_query_required');
 return [PROJECT_CATALOG_QUERY,PROJECT_CATALOG_FIRST_PAGE_QUERY].map(query=>'/projects?'+query);
}
function legacyAllowedPath(raw){if(typeof raw!=='string'||!raw.startsWith('/')||raw.startsWith('//'))return false;const url=new URL(raw,'http://127.0.0.1');return url.pathname==='/favicon.ico'||url.pathname.startsWith('/_next/static/')||(publicPaths.has(url.pathname)&&[...url.searchParams.keys()].every(key=>key==='_rsc'));}
function pathAllowed(raw,catalogPaths){
 if(legacyAllowedPath(raw))return true;
 if(typeof raw!=='string')return false;
 // Exact synthetic serializations only. At most one opaque Next RSC token.
 return catalogPaths.some(path=>raw===path||(raw.startsWith(path+'&_rsc=')&&/^[A-Za-z0-9_-]+$/.test(raw.slice((path+'&_rsc=').length))));
}
function allowedPath(raw,options){return pathAllowed(raw,catalogPolicy(options));}
async function startStreamingProxy(upstream,options){
 const catalogPaths=catalogPolicy(options);
 const target=new URL(upstream);if(target.protocol!=='http:'||target.hostname!=='127.0.0.1'||target.origin!==upstream)throw Error('loopback_upstream_required');
 const violations=[];
 const server=http.createServer((req,res)=>{
  if(!['GET','HEAD'].includes(req.method)||!pathAllowed(req.url,catalogPaths)||req.headers.authorization){violations.push('rejected_request');res.writeHead(400);res.end('rejected');return;}
  const read=http.request({hostname:'127.0.0.1',port:target.port,path:req.url,method:req.method,headers:{...req.headers,host:target.host}},incoming=>{
   // node:http does not follow redirects. Never forward Location or an external
   // redirect response to the browser, even if Next unexpectedly produces one.
   if(incoming.statusCode>=300&&incoming.statusCode<400){violations.push('rejected_redirect');incoming.resume();res.writeHead(502,{'content-type':'text/plain'});res.end('unexpected_redirect');return;}
   const headers={...incoming.headers};delete headers.location;delete headers.refresh;
   incoming.on('error',()=>res.destroy());res.writeHead(incoming.statusCode,headers);incoming.pipe(res);
  });
  read.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end();});
  res.on('close',()=>read.destroy());read.end();
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 return{origin:`http://127.0.0.1:${server.address().port}`,violations,async close(){server.closeAllConnections();await new Promise((resolve,reject)=>server.close(e=>e?reject(e):resolve()));}};
}
module.exports={allowedPath,startStreamingProxy,PROJECT_CATALOG_QUERY,PROJECT_CATALOG_FIRST_PAGE_QUERY,CHANGE_CATALOG_QUERY,ISSUE_CATALOG_QUERY};
