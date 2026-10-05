'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-session-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'lib/browser-session.ts','--target','ES2021','--module','commonjs','--strict','--skipLibCheck','--outDir',output]);
// Next supplies the server-only bundling guard; this isolated server runtime stubs only that marker.
const exportsObject={};vm.runInNewContext(fs.readFileSync(path.join(output,'browser-session.js'),'utf8'),{exports:exportsObject,require:name=>{assert.equal(name,'server-only');return {};},crypto:globalThis.crypto,TextEncoder,TextDecoder,Uint8Array,btoa,atob,AbortSignal,fetch,URL});
const {sessionConfig,establishSession,resolveSession,clearSessionCookie}=exportsObject;
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const env={BROWSER_SESSION_MODE:'encrypted',BROWSER_SESSION_KEY:Buffer.alloc(32,7).toString('base64url'),BROWSER_SESSION_ORIGIN:'https://app.example.test',API_BASE_URL:'https://api.example.test'};
const id='12345678-1234-1234-1234-123456789abc',token='signed-access-token';
const identity={principal:{id,principal_type:'HUMAN',display_name:'Operator'},read_only_mode:true,active_grant_counts:{GLOBAL:0,PROJECT:3,SOFTWARE:2}};
function backend(data=identity,status=200){return async(url,options)=>{assert.equal(url,'https://api.example.test/api/v1/security/me');assert.equal(options.headers.Authorization,`Bearer ${token}`);assert.equal(options.cache,'no-store');assert.equal(options.redirect,'error');assert.ok(options.signal);return Response.json(data,{status});};}
async function issued(fetcher=backend(),expires=5000){return establishSession(await sessionConfig(env),token,expires,fetcher,1000);}
test('disabled by default; malformed enabled config fails closed',async()=>{
 assert.equal(await sessionConfig({}),null);assert.equal(await sessionConfig({BROWSER_SESSION_MODE:'disabled'}),null);
 for(const patch of [{BROWSER_SESSION_MODE:'on'},{BROWSER_SESSION_KEY:''},{BROWSER_SESSION_KEY:Buffer.alloc(31).toString('base64url')},{API_BASE_URL:undefined,NEXT_PUBLIC_API_BASE_URL:env.API_BASE_URL},{API_BASE_URL:'http://api.test'},{API_BASE_URL:'https://user:password@api.test'},{API_BASE_URL:'https://api.test/?q=x'},{BROWSER_SESSION_ORIGIN:'https://app.test/path'},{BROWSER_SESSION_ORIGIN:'https://app.test/#fragment'}]) await assert.rejects(sessionConfig({...env,...patch}));
});
test('encrypted randomized host-only cookie hides token and uses secure attributes',async()=>{
 const a=await issued(),b=await issued();assert.ok(a);assert.notEqual(a.cookie.value,b.cookie.value);
 assert.equal(a.cookie.name,'__Host-slc_session');assert.equal(a.cookie.httpOnly,true);assert.equal(a.cookie.secure,true);assert.equal(a.cookie.sameSite,'lax');assert.equal(a.cookie.path,'/');assert.equal(a.cookie.maxAge,900);assert.equal(a.cookie.domain,undefined);assert.ok(!a.cookie.value.includes(token));
 assert.equal((await resolveSession(await sessionConfig(env),a.cookie.value,backend(),1001)).principal.id,id);
});
test('expiration caps token lifetime; reads never renew the cookie',async()=>{
 const a=await issued(backend(),1100),config=await sessionConfig(env);assert.equal(a.cookie.maxAge,100);let calls=0;const fetcher=async()=>{calls++;return Response.json(identity);};
 assert.equal(await resolveSession(config,a.cookie.value,fetcher,1100),null);assert.equal(calls,0);assert.ok(await resolveSession(config,a.cookie.value,fetcher,1099));assert.equal(calls,1);
});
test('invalid tokens and expiration never reach backend',async()=>{
 let calls=0;const fetcher=async()=>{calls++;return Response.json(identity);},config=await sessionConfig(env);
 for(const bad of ['',token+'\r\nX: y','a'.repeat(2401),{},null]) assert.equal(await establishSession(config,bad,2000,fetcher,1000),null);
 for(const expiry of [1000,999,Infinity,1000.1]) assert.equal(await establishSession(config,token,expiry,fetcher,1000),null);assert.equal(calls,0);
});
test('tampered, truncated, malformed and oversized cookies fail before fetch',async()=>{
 const a=await issued(),config=await sessionConfig(env);let calls=0;const fetcher=async()=>{calls++;return Response.json(identity);};const [v,iv,body]=a.cookie.value.split('.');
 for(const value of [undefined,'',a.cookie.value.slice(0,-8),`v2.${iv}.${body}`,`${v}.${iv}.${body[0]==='A'?'B':'A'}${body.slice(1)}`,`${v}.${iv}=.${body}`,'a'.repeat(3801),'v1.a.b']) assert.equal(await resolveSession(config,value,fetcher,1001),null);assert.equal(calls,0);
});
test('key rotation, origin/API changes and future issuance invalidate before fetch',async()=>{
 const a=await issued();let calls=0;const never=async()=>{calls++;throw new Error('unexpected fetch');};
 for(const patch of [{BROWSER_SESSION_KEY:Buffer.alloc(32,8).toString('base64url')},{BROWSER_SESSION_ORIGIN:'https://other.test'},{API_BASE_URL:'https://other-api.test'}]) assert.equal(await resolveSession(await sessionConfig({...env,...patch}),a.cookie.value,never,1001),null);
 assert.equal(await resolveSession(await sessionConfig(env),a.cookie.value,never,999),null);assert.equal(calls,0);
});
test('each resolution rechecks active principal and changed grant counts',async()=>{
 const a=await issued(),config=await sessionConfig(env);let calls=0;const fetcher=async()=>{calls++;return Response.json({...identity,active_grant_counts:{GLOBAL:0,PROJECT:0,SOFTWARE:0}});};
 for(let i=0;i<2;i++) assert.equal((await resolveSession(config,a.cookie.value,fetcher,1001)).active_grant_counts.PROJECT,0);assert.equal(calls,2);
 assert.equal(await resolveSession(config,a.cookie.value,backend({detail:'inactive_principal'},401),1001),null);
});
test('service identities and backend principal mismatch are rejected',async()=>{
 const service={...identity,principal:{...identity.principal,principal_type:'SERVICE'}};assert.equal(await issued(backend(service)),null);
 const a=await issued(),config=await sessionConfig(env);assert.equal(await resolveSession(config,a.cookie.value,backend(service),1001),null);
 assert.equal(await resolveSession(config,a.cookie.value,backend({...identity,principal:{...identity.principal,id:'23456789-1234-1234-1234-123456789abc'}}),1001),null);
});
test('malformed responses and network errors fail closed',async()=>{
 for(const data of [null,{}, {...identity,read_only_mode:'false'},{...identity,active_grant_counts:{GLOBAL:-1,PROJECT:0,SOFTWARE:0}},{...identity,principal:{...identity.principal,id:'untrusted'}}]) assert.equal(await issued(backend(data)),null);
 for(const fetcher of [async()=>{throw new Error('secret');},async()=>new Response('<html>'),async()=>new Response('{',{headers:{'content-type':'application/json'}}),backend({},503)]) assert.equal(await issued(fetcher),null);
});
test('declared and streamed oversized response bodies are cancelled',async()=>{
 for(const headers of [{'content-type':'application/json','content-length':'20000'},{'content-type':'application/json'}]){let cancelled=false;const fetcher=async()=>new Response(new ReadableStream({start(c){c.enqueue(new Uint8Array(17000));},cancel(){cancelled=true;}}),{headers});assert.equal(await issued(fetcher),null);assert.equal(cancelled,true);}
});
test('identity projection excludes extra secrets; logout clears the identical cookie path',async()=>{
 const a=await issued(backend({...identity,token,principal:{...identity.principal,email:'private@example.test',token}}));assert.ok(a);assert.ok(!JSON.stringify(a.identity).includes(token));assert.ok(!JSON.stringify(a.identity).includes('email'));
 const clear=clearSessionCookie();assert.equal(clear.name,a.cookie.name);assert.equal(clear.path,a.cookie.path);assert.equal(clear.value,'');assert.equal(clear.maxAge,0);
});
