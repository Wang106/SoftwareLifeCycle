'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),http=require('node:http');
const {principal,sid}=require('./storage-api.cjs');
const ORIGIN='https://upload.example.test',API='https://api.example.test';
function loopback(origin,requestPath,method,headers,body){
 const u=new URL(origin);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'||!u.port||u.pathname!=='/'||u.search||u.hash||u.username||u.password)throw Error('non-loopback forbidden');
 return new Promise((resolve,reject)=>{const q=http.request({hostname:'127.0.0.1',port:u.port,path:requestPath,method,headers,agent:false},r=>{const chunks=[];let size=0;r.on('data',b=>{size+=b.length;if(size>1048576){r.destroy();reject(Error('response limit'))}else chunks.push(b)});r.on('error',reject);r.on('end',()=>resolve({status:r.statusCode,headers:r.headers,body:Buffer.concat(chunks)}))});q.setTimeout(5000,()=>q.destroy(Error('loopback timeout')));q.on('error',reject);q.end(body)});
}
async function createRelay(compiled,apiOrigin){
 const modules=new Map(),violations=[];
 function load(file){if(modules.has(file))return modules.get(file);if(!/^[a-z0-9-]+$/.test(file))throw Error('module');const exports={};modules.set(file,exports);vm.runInNewContext(fs.readFileSync(path.join(compiled,'lib',file+'.js'),'utf8'),{exports,require:n=>n==='server-only'?{}:n==='jose'?require('jose'):load(n.replace('./','')),crypto:globalThis.crypto,TextEncoder,TextDecoder,Uint8Array,btoa,atob,AbortSignal,AbortController,fetch:()=>{violations.push('unwired-fetch');throw Error('network forbidden')},URL,Request,Response,Headers,setTimeout,clearTimeout,performance});return exports;}
 const env={BROWSER_OIDC_MODE:'code',BROWSER_SESSION_MODE:'encrypted',BROWSER_SESSION_KEY:Buffer.alloc(32,9).toString('base64url'),BROWSER_SESSION_ORIGIN:ORIGIN,API_BASE_URL:API,OIDC_ISSUER_URL:'https://id.example.test/',OIDC_AUDIENCE:'software-api',OIDC_CLIENT_ID:'software-web',OIDC_AUTHORIZATION_URL:'https://id.example.test/authorize',OIDC_TOKEN_URL:'https://id.example.test/token',OIDC_JWKS_URL:'https://id.example.test/jwks',PRIVATE_UPLOAD_MODE:'enabled',PRIVATE_UPLOAD_APPROVED_API_BASE_URL:API,PRIVATE_UPLOAD_APPROVED_APP_ORIGIN:ORIGIN};
 const config=await load('browser-auth').authConfig(env),session=load('browser-session'),now=Math.floor(Date.now()/1000);
 const cookie=await session.sealCookie(config.session,session.SESSION_COOKIE,{v:2,sid,binding:config.session.binding,issued:now,expires:now+300,principal,token:'synthetic-token'});
 const fetcher=async(url,init)=>{const u=new URL(String(url));const allowed=u.origin===API&&!u.hash&&!u.username&&!u.password&&(/^\/api\/v1\/private-uploads\/(context\?component_id=[a-f0-9-]{36}|reservations|receipts\/[a-f0-9-]{36}|[a-f0-9-]{36}\/content)$/.test(u.pathname+u.search)||u.pathname==='/api/v1/security/me'&&!u.search);if(!allowed){violations.push('upstream-target');throw Error('network forbidden')}
  const r=await loopback(apiOrigin,u.pathname+u.search,init.method||'GET',init.headers,init.body);return new Response(r.body,{status:r.status,headers:{'Content-Type':String(r.headers['content-type']||'')}})};
 const counts={context:0,reserve:0,content:0,receipt:0};
 return {cookie:{name:session.SESSION_COOKIE,value:cookie,url:ORIGIN,secure:true,httpOnly:true,sameSite:'Lax'},violations,counts:()=>({...counts}),async handle(request,mode){counts[mode]++;return load('private-upload-proxy').handlePrivateUpload(request,env,mode,fetcher)}};
}
module.exports={ORIGIN,loopback,createRelay};
