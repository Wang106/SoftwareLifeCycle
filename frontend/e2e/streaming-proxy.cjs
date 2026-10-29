'use strict';
// Test transport only: fixed loopback upstream, no redirects and no buffering.
const http=require('node:http');
const {once}=require('node:events');
const publicPaths=new Set(['/', '/changes', '/issues', '/projects']);
function allowedPath(raw){if(typeof raw!=='string'||!raw.startsWith('/')||raw.startsWith('//'))return false;const url=new URL(raw,'http://127.0.0.1');return url.pathname==='/favicon.ico'||url.pathname.startsWith('/_next/static/')||(publicPaths.has(url.pathname)&&[...url.searchParams.keys()].every(key=>key==='_rsc'));}
async function startStreamingProxy(upstream){
 const target=new URL(upstream);if(target.protocol!=='http:'||target.hostname!=='127.0.0.1'||target.origin!==upstream)throw Error('loopback_upstream_required');
 const violations=[];
 const server=http.createServer((req,res)=>{
  if(!['GET','HEAD'].includes(req.method)||!allowedPath(req.url)||req.headers.authorization){violations.push('rejected_request');res.writeHead(400);res.end('rejected');return;}
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
module.exports={allowedPath,startStreamingProxy};
